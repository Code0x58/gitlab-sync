"""Module containing low level operations on repositories.

These operation don't work out what to do at any point, that logic is left to
the strategy module.

"""
import os
import shutil
import subprocess

from gitlab_sync import logger


def clone(repo):
    """Clone a new repository."""
    os.makedirs(str(repo.local_path))
    repo.git("init", ".")
    repo.git("config", "--local", "--add", "gitlab-sync.project-id", str(repo.id))
    repo.git("remote", "add", "origin", "git@gitlab.com:%s.git" % repo.gitlab_path)
    update_local(repo)


def update_local(repo):
    """Update master from the remote."""
    repo.git("fetch")
    # get refs/remotes/origin/HEAD
    issue = repo.git(
        "remote",
        "set-head",
        "origin",
        "--auto",
        check=False,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    ).stderr.rstrip()
    if not issue:
        # read which branch the remote HEAD points to
        remote_head = repo.git(
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
            stdout=subprocess.PIPE,
            universal_newlines=True,
        ).stdout.rstrip()
        # checkout and track the branch that the remote HEAD points to
        issue = repo.git(
            "checkout",
            "--track",
            remote_head,
            check=False,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        ).stdout
        if issue:
            # if the branch is already tracked, then just check out the tip of it
            if issue.startswith("fatal: a branch"):
                repo.git("checkout", remote_head.rpartition("/")[2])
            else:
                raise Exception(issue.rstrip())
    elif issue == "error: Cannot determine remote HEAD":
        logger.debug("%s is an empty project", repo)
    else:
        raise Exception(issue)


def delete_local(repo):
    logger.debug("removing %s", repo)
    shutil.rmtree(str(repo.local_path))
    prune = repo.local_path.parent
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
