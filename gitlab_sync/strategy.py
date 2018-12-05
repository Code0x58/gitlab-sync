"""Module for top level strategies for local copies.

The methods in here direct lower level operations. The idea is to have as
little if/else handling as possible, with lower level methods having 0
knowledge of their use.

"""
import abc
import enum
import shutil

import attr
import gitlab_sync.operations
import gitlab_sync.repository
from gitlab_sync import logger

# there is a filesytem and git level sync
# filesystem level handles things like creates/deletes/moves
# git level sync does merges
# example commands
# gitlab-sync mirror --filesystem-only|--git-only
# gitlab-sync sync --filesystem-only|--git-only


class GitlabSyncException(Exception):
    """Base exception for gitlab-sync exceptions."""


class StateError(GitlabSyncException):
    """Raised when a strategy cannot be applied due to an invalid state."""


@attr.s(auto_attribs=True)
class FilestemSyncState:
    create_local: int
    create_remote: int
    create_conflict: int
    move_local: int
    move_remote: int
    move_conflict: int
    delete_local: int
    delete_remote: int


class GitSyncState(enum.Enum):
    fast_forward_local = enum.auto()
    fast_forward_remote = enum.auto()
    conflict = enum.auto()
    merge_local = enum.auto()
    merge_remote = enum.auto()


def run_for_config(context, config):
    """Method to call from the CLI to apply a config."""
    # TODO: get the repo pairs
    # TODO: put all of these in an object/named-tuple so easier to pass
    filesystem_state = FilestemSyncState()
    if not context.git_only:
        config.strategy.apply_filesystem(filesystem_state)
    git_state = GitSyncState()
    if not context.filesystem_only:
        config.strategy.apply_git(git_state)


class Strategy(abc.ABC):
    """Abstract class for processing states."""

    def __init__(self, config):
        self.config = config

    @abc.abstractmethod
    def apply_filesystem(self, state: FilestemSyncState) -> None:
        pass

    # this only uses enum_local if --git-only, otherwise assumes resolved sync
    @abc.abstractmethod
    def apply_git(self, branch: str, state: GitSyncState) -> None:
        pass


class MirrorStrategy(Strategy):
    """Assume changes only happen remotely."""

    def apply_filesystem(self, state: FilestemSyncState) -> None:
        disallowed_states = (
            state.create_remote +
            state.create_conflict +
            state.move_remote +
            state.move_conflict +
            state.delete_remote
        )
        if disallowed_states:
            # TODO: include list of repos
            raise StateError("Local changes were made which are incompatiable with this strategy.")

    def apply_git(self, state: GitSyncState) -> None:
        disallowed_states = ()


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

    for repo in sorted(update_map.values()):
        logger.info("updating %s", repo)
        gitlab_sync.operations.update_local(repo)
        logger.info("cleaning %s", repo)
        gitlab_sync.operations.clean(repo)

    for remote in sorted(create_map.values()):
        logger.info("copying %s", remote)
        local = gitlab_sync.repository.LocalRepository.from_remote(config, remote)
        gitlab_sync.operations.clone(config, local, remote)
