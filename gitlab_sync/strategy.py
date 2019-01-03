"""Module for top level strategies for local copies.

The methods in here direct lower level operations. The idea is to have as
little if/else handling as possible, with lower level methods having 0
knowledge of their use.

"""
import shutil

import gitlab_sync.operations
import gitlab_sync.repository
from gitlab_sync import logger


# XXX: it may be good to generate the maps in a helper method
def mirror(config):
    """Perform necissary actions to update a local copy using backup logic."""
    locals_ = list(gitlab_sync.repository.enumerate_local(config.base_path))
    # TODO: update paths to be namespaces in other places
    remotes = list(
        gitlab_sync.repository.enumerate_remote(config)
    )

    remoteless = [repo for repo in locals_ if repo.gitlab_project_id is None]
    if remoteless:
        # TODO: subclass exceptions
        # low chance of being due to a failure between git-init and git-config
        raise Exception("Unexpected directories.")
    local_map = {repo.gitlab_project_id: repo for repo in locals_}
    remote_map = {repo.gitlab_project_id: repo for repo in remotes}
    logger.debug("local repos found: %r", locals_)
    logger.debug("remote repos found: %r", remotes)

    delete_map = {}
    for id_ in local_map.keys() - remote_map.keys():
        repo = local_map.pop(id_)
        delete_map[repo.gitlab_project_id] = repo

    create_map = {}
    for id_ in remote_map.keys() - local_map.keys():
        repo = remote_map.pop(id_)
        create_map[repo.gitlab_project_id] = repo

    move_map = {}
    for id_, local in local_map.items():
        remote = remote_map[id_]
        if local.gitlab_path and remote.gitlab_path != local.gitlab_path:
            move_map[id_] = (remote, local.gitlab_path, remote.gitlab_path)

    update_map = {
        id_: gitlab_sync.repository.LocalRepository.from_remote(config, remote)
        for id_, remote in remote_map.items()
        if id_ not in create_map
    }

    for repo in sorted(delete_map.values()):
        logger.info("deleting %s", repo)
        gitlab_sync.operations.delete_local(repo)
        # TODO: think about being definsive against errors reading from GitLab
        # maybe GitLab retains projects in the database after they are deleted?
        # tombstones would be nice

    for repo, old_gitlab_path, new_gitlab_path in sorted(move_map.values()):
        logger.info("moving %s to %s", old_gitlab_path, new_gitlab_path)
        shutil.move(str(config.base_path / old_gitlab_path), str(config.base_path / new_gitlab_path))

    for remote in sorted(create_map.values()):
        logger.info("copying %s", remote)
        local = gitlab_sync.repository.LocalRepository.from_remote(config, remote)
        gitlab_sync.operations.clone(config, local, remote)

    for repo in sorted(update_map.values()):
        logger.info("updating %s", repo)
        gitlab_sync.operations.update_local(repo)
        logger.info("cleaning %s", repo)
        gitlab_sync.operations.clean(repo)
