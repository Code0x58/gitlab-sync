"""Module containing low level operations on repositories.

These operation don't work out what to do at any point, that logic is left to
the strategy module.

"""
import os
import shutil
import subprocess

from gitlab_sync import logger


def clone(config, local, remote):
    """Clone a new repository."""
    os.makedirs(str(local.absolute_path))
    local.git("init", ".")
    local.gitlab_project_id = remote.gitlab_project_id
    local.gitlab_path = remote.gitlab_path
    local.git(
        "remote", "add", "origin",
        config.gitlab_git + "%s.git" % remote.gitlab_path,
    )
    update_local(local)


def update_local(local):
    """Update master from the remote."""
    local.git("fetch")
    # get refs/remotes/origin/HEAD
    result = local.git(
        "remote",
        "set-head",
        "origin",
        "--auto",
        check=False,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    issue = result.stderr.rstrip()
    if not result.returncode:
        # read which branch the remote HEAD points to
        remote_head = local.git(
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
            stdout=subprocess.PIPE,
            universal_newlines=True,
        ).stdout.rstrip()
        # checkout and track the branch that the remote HEAD points to
        result = local.git(
            "checkout",
            "--track",
            remote_head,
            check=False,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        if result.returncode:
            issue = result.stderr
            # if the branch is already tracked, then just check out the tip of it
            name = remote_head.rpartition("/")[2]
            if issue.startswith(r"fatal: A branch named '%s' already exists." % name):
                local.git("reset", "--hard", remote_head)
            else:
                raise Exception(issue.rstrip())
        else:
            logger.debug("`git checkout --track %s` worked", remote_head)
    elif issue.endswith("error: Cannot determine remote HEAD"):
        logger.debug("%s is an empty project", local)
    else:
        raise Exception(issue)
    # mirror only logic
    local.git("clean", "-d", "--force")


def delete_local(repo):
    logger.debug("removing %s", repo)
    shutil.rmtree(str(repo.absolute_path))
    prune = repo.absolute_path.parent
    while prune != repo.base_path:
        try:
            os.rmdir(str(prune))
        except OSError:
            # assuming this is because the directory isn't empty
            break
        logger.debug("pruned %s", prune)


def clean(repo):
    logger.debug("cleaning %s", repo)
    repo.git("remote", "prune", "origin")
    repo.git("gc", "--auto")
