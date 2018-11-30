"""Module for top level strategies for local copies.

The methods in here direct lower level operations. The idea is to have as
little if/else handling as possible, with lower level methods having 0
knowledge of their use.

"""
import shutil
import typing

import gitlab_sync.operations
import gitlab_sync.repository
from gitlab_sync import logger
from gitlab_sync.repository import Repository


def _get_repo_maps(config):
    locals_ = list(gitlab_sync.repository.enumerate_local(config.base_path))
    remotes = list(
        gitlab_sync.repository.enumerate_remote(config)
    )
    logger.debug("local repos found: %r", locals_)
    logger.debug("remote repos found: %r", remotes)
    return _classify_repos(locals_, remotes)


def _classify_repos(locals_: typing.List[Repository], remotes: typing.List[Repository]):
    """Return a plan for operations to synchronise remote and local repositories.

    The granularity of the plan lets strategies pick and mix what they do, and
    detect situations that are erronious for the chosen strategy.

    The intention of the generic plan is to make the local and remote repos
    equal in terms of relative location, and git trees.

    update_local + update_remote can result in conflicts that need resolving,
    some strategies (e.g. mirror) do not expect this to happen so raise if an
    issue is found so the user can deal with it. It would be nice if the classification
    happened here following a fetch, then this plan knows everything. The git sync
    makes testing require some mocking.

    """
    local_map = {repo.id: repo for repo in locals_}
    remote_map = {repo.id: repo for repo in remotes}

    move_resolve = []
    for id_, local in local_map.items():
        remote = remote_map[id_]
        if (local.last_gitlab_path and local.last_gitlab_path != local.gitlab_path and
                local.gitlan_path != remote.gitlab_path):
            move_resolve.append((local, remote))

    delete_local = []
    for id_ in local_map.keys() - remote_map.keys():
        repo = local_map.pop(id_)
        delete_local.append((repo,))

    create_local = []
    for id_ in remote_map.keys() - local_map.keys():
        repo = remote_map.pop(id_)
        create_local.append((repo,))

    # FIXME: move operation updates project-path/last_gitlab_path
    # FIXME: clone operation sets project-path/last_gitlab_path
    # when there's a remove move, the remote has to be updated, so
    # can't update a repo that needs to be resolved.
    move_local = []
    for id_, local in local_map.items():
        remote = remote_map[id_]
        # repo hasn't moved locally but has remotely
        if (local.gitlab_path == local.last_gitlab_path and
                remote.gitlab_path != local.gitlab_path):
            move_local.append((repo, remote.gitlab_path))
            # what if both have changed? conflict... separate resolve operation
    # how can you tell a local move from a remote move? store local rel path
    # in local copy, if repo has moved removely then at locally = local rel
    # this really returns a "plan", but the strategies select a subset of it
    # and enforce their own constraints
    # ({operation: [(repo, *args), ...]})
    """
    [
        (create_local,  []),
        (move_local,    []),
        (update_local,  []),
        (delete_local,  []),
        (create_remote, []),
        (move_remote,   []),
        (update_remote, []),
        (delete_remote, []),

        (move_resolve,  []),
    ]
    """
    update_local = [
        (repo, ) for repo in remote_map.values()
    ]

    create_remote = [(repo, ) for repo in locals_ if repo.id is None]

    move_remote = []
    for id_, local in local_map.items():
        remote = remote_map[id_]
        # TODO: guard heavily against moving things around by mistake due to code errors
        # make sure there is good test coverage
        if (local.last_gitlab_path and
                local.last_gitlab_path != local.gitlab_path and
                remote.gitlab_path != local.gitlab_path):
            move_local.append((repo, remote.gitlab_path))

    # TODO: see about modification times
    update_remote = []
    delete_remote = []

    return [
        # maybe update should be a single final operation, but there are levels of update
        ("create_local", create_local),
        ("move_local", move_local),
        ("update_local", update_local),
        ("delete_local", delete_local),
        ("create_remote", create_remote),
        ("move_remote", move_remote),
        ("update_remote", update_remote),
        ("delete_remote", delete_remote),
        ("move_resolve", move_resolve),
    ]


# XXX: it may be good to generate the maps in a helper method
def mirror(config):
    """Perform necissary actions to update a local copy using backup logic."""
    # raise if any create_remote, move_remote, delete_remote (do not run update_remote)


    for repo in sorted(delete_map.values()):
        logger.info("deleting %s", repo)
        gitlab_sync.operations.delete_local(repo)
        # TODO: think about being definsive against errors reading from GitLab
        # maybe GitLab retains projects in the database after they are deleted?
        # tombstones would be nice

    for repo, old_gitlab_path, new_gitlab_path in sorted(move_map.values()):
        logger.info("moving %s to %s", old_gitlab_path, new_gitlab_path)
        shutil.move(str(config.base_path / old_gitlab_path), str(config.base_path / new_gitlab_path))

    for repo in sorted(update_map.values()):
        logger.info("updating %s", repo)
        gitlab_sync.operations.update_local(repo)
        logger.info("cleaning %s", repo)
        gitlab_sync.operations.clean(repo)

    for repo in sorted(create_map.values()):
        logger.info("copying %s", repo)
        gitlab_sync.operations.clone(config, repo)
