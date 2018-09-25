#!/usr/bin/env python
import itertools
import os
import shutil
import subprocess
import sys
from pathlib import Path

import click
import requests
import toml

PRIMARY_BRANCH = "master"


class Repository(object):
    class WorkingTree(object):
        def __init__(self, repo):
            self.repo = repo

        def __bool__(self):
            return self.repo.local_path.is_dir()

        @property
        def branch(self):
            result = self.repo("rev-parse", "--abbrev-ref", "HEAD")
            if result.returncode:
                return None
            else:
                rev = result.stdout.strip()
                return None if rev == "HEAD" else self.Branch(self.repo, rev)

        @property
        def is_empty(self):
            result = self.repo("log", "--all", "--max-count=0", check=False)
            return result.returncode != 0

        @property
        def initial_commit(self):
            result = self.repo(
                "rev-list", "--max-parents=0", PRIMARY_BRANCH, check=True
            )
            commits = result.stdout.strip().split()
            assert len(commits) == 1
            return commits[0]

        @property
        def clean(self):
            result = self.repo("diff", "--quiet", "--head")
            return not result.returncode

        class Branch(object):
            def __init__(self, repo, name):
                self.repo = repo
                self.name = name

            def __repr__(self):
                return f"{type(self).__name__}({self.repo!r}, {self.name!r})"

            def __str__(self):
                return self.name

            def __eq__(self, other):
                if isinstance(other, str):
                    return self.name == other
                raise NotImplementedError()

            @property
            def remote_changes(self):
                result = self.repo(
                    "rev-list",
                    "--left-right",
                    "--count",
                    f"{self.name}..refs/remotes/{REMOTE_NAME}/{self.name}",
                    check=False,
                )
                if result.returncode:
                    # probably no branch on remote
                    return None, None
                # local is (behind, ahead)
                return tuple(int(chunk) for chunk in result.stdout.strip().split())

    # TODO: consider warning if remote URL is not git+ssh - don't want interactive sheet
    def __init__(self, path, id=None):
        self.path = Path(path)
        if self.path.is_absolute():
            self.local_path = self.path
            self.path = self.path.relative_to(BASE_DIRECTORY)
        else:
            self.local_path = BASE_DIRECTORY / self.path
        self.id = id
        self.worktree = self.WorkingTree(self)

    def sync(self):
        click.secho(f"Syncing {click.style(str(self.path), bold=True)}", fg="blue")
        # TODO: work out what to do where the default branch isn't master/PRIMARY_BRANCH, e.g. mintel/presonal-dev/nick-test
        if not self.worktree:
            click.secho("cloning into new repository", fg="green", bold=True)
            self.local_path.mkdir(parents=True, exist_ok=True)
            self(
                "clone", f"git@gitlab.com:{self.path}.git", ".", stdout=None, check=True
            )
        elif self.worktree.branch == PRIMARY_BRANCH or self.worktree.is_empty:
            if not self.worktree.clean:
                click.secho("work tree is dirty", fg="red", bold=True)
                return
            # result = repo("pull", "origin", "master", "--tags", stderr=sys.stderr, stdout=sys.stdout)
            click.echo(f"Fetching from {REMOTE_NAME}")
            result = self("fetch", "--prune", "--tags", REMOTE_NAME)
            if result.returncode:
                click.secho(
                    "an error ocurred - has the repo been moved? Currently need manaual reconciliation",
                    fg="red",
                    bold=True,
                )
            else:
                if self.worktree.is_empty:
                    click.secho(f"repository is still empty", fg="green", bold=True)
                    return
                behind, ahead = self.worktree.branch.remote_changes
                if behind:
                    # can't fast foward in the changes as there are non-pushed local changes
                    click.secho(
                        f"local {PRIMARY_BRANCH} has {behind} commants that aren't in {REMOTE_NAME}",
                        fg="red",
                        bold=True,
                    )
                    pass
                elif ahead:
                    click.secho(
                        f"{ahead} new commits, resetting local {PRIMARY_BRANCH} to that of {REMOTE_NAME}",
                        fg="green",
                        bold=True,
                    )
                    self(
                        "reset",
                        f"refs/remotes/{REMOTE_NAME}/{PRIMARY_BRANCH}",
                        check=True,
                    )
                else:
                    # up to date
                    click.secho(
                        f"local {PRIMARY_BRANCH} is already up to date",
                        fg="green",
                        bold=True,
                    )
        else:
            click.secho(
                f"local branch is {self.worktree.branch} instead of {PRIMARY_BRANCH}",
                fg="red",
                bold=True,
            )

    def __call__(self, *args, **kwargs):
        """
        Return subprocess result from running git with with given commands.

        Passes kwargs to subprocess with defaults for capturing output.

        """
        if "stdout" not in kwargs:
            kwargs.setdefault("text", True)
            kwargs.setdefault("stdin", subprocess.PIPE)
            kwargs.setdefault("stdout", subprocess.PIPE)
            kwargs.setdefault("stderr", subprocess.PIPE)
        return subprocess.run(["git", "-C", str(self.local_path), *args], **kwargs)

    def __repr__(self):
        return f"{type(self).__name__}({str(self.path)!r})"


ACCESS_TOKEN = None
BASE_DIRECTORY = None
GITLAB = None
PATHS = None
REMOTE_NAME = "origin"


def _load_config():
    global ACCESS_TOKEN, BASE_DIRECTORY, GITLAB, PATHS, REMOTE_NAME
    path = Path(os.path.expanduser("~"))
    locations = (path / ".config/gitlab-tree.toml", path / ".gitlab-tree.toml")
    for location in locations:
        if location.is_file():
            break
    else:
        raise ValueError(
            f"Config does not exist in one of {', '.join(map(str, locations))}"
        )

    config = toml.load(str(location))
    if isinstance(config.get("access-token-command"), list):
        access_token_command = config["access-token-command"]
        result = subprocess.run(access_token_command, stdin=sys.stdin, stderr=sys.stderr, stdout=subprocess.PIPE, text=True, check=True)
        ACCESS_TOKEN = result.stdout.strip()
    elif isinstance(config.get("access-token"), str):
        ACCESS_TOKEN = config["access-token"]
    else:
        raise ValueError("one of access-token or access-token-command is required and must be a string")

    GITLAB = requests.Session()
    GITLAB.headers.update({"Private-Token": ACCESS_TOKEN})

    if (
        "paths" not in config
        or not isinstance(config["paths"], list)
        or not config["paths"]
        or not isinstance(config["paths"][0], str)
    ):
        raise ValueError("paths is required and must be a non-empty list")
    PATHS = config["paths"]

    if not isinstance(config.get("base-directory", ""), str):
        raise ValueError("base-directory must be a string")
    BASE_DIRECTORY = Path(os.path.expanduser(config.get("base-directory", "~/gitlab/")))

    if not isinstance(config.get("remote", ""), str):
        raise ValueError("remote must be a string")
    REMOTE_NAME = config.get("remote", REMOTE_NAME)

    return config


ALL_REPOS = None
COMMON_REPOS = None
LOCAL_ONLY_REPOS = None
REMOTE_ONLY_REPOS = None


# TODO: enumerate groups available to user/API token
# TODO: walk pages
def _list_group_projects(group):
    projects = []
    response = GITLAB.get(
        f"https://gitlab.com/api/v4/groups/{group}/projects",
        params={"per_page": 100, "page": 1, "simple": True},
    )
    while response.headers.get("x-next-page"):
        projects.extend(response.json())
        response = GITLAB.get(
            f"https://gitlab.com/api/v4/groups/{group}/projects",
            params={
                "per_page": 100,
                "page": response.headers["X-Next-Page"],
                "simple": True,
            },
        )
    projects.extend(response.json())
    return {Path(project["path_with_namespace"]): project["id"] for project in projects}


def _list_user_projects(user):
    projects = []
    response = GITLAB.get(
        f"https://gitlab.com/api/v4/users/{user}/projects",
        params={"per_page": 100, "page": 1, "simple": True},
    )
    while response.headers.get("x-next-page"):
        projects.extend(response.json())
        response = GITLAB.get(
            f"https://gitlab.com/api/v4/users/{user}/projects",
            params={
                "per_page": 100,
                "page": response.headers["C-Next-Page"],
                "simple": True,
            },
        )
    data = response.json()
    if "message" in data:
        raise ValueError(f"Unable to find group or user for {user}")
    projects.extend(data)
    return {Path(project["path_with_namespace"]): project["id"] for project in projects}


def _get_all_projects(group_or_user):
    groups = []
    projects = {}
    response = GITLAB.get(
        f"https://gitlab.com/api/v4/groups/{group_or_user}/subgroups",
        params={"per_page": 100, "page": 1},
    )
    while response.headers.get("x-next-page"):
        groups.extend(response.json())
        response = GITLAB.get(
            f"https://gitlab.com/api/v4/groups/{group_or_user}/subgroups",
            params={"per_page": 100, "page": response.headers["X-Next-Page"]},
        )
    data = response.json()
    if "message" in data:
        # probably a user rather than group
        projects.update(_list_user_projects(group_or_user))
    else:
        # group_or_user was a group
        groups.extend(data)
        for group in [group_or_user] + [group["id"] for group in groups]:
            projects.update(_list_group_projects(group))
    return projects


def _get_local_paths():
    repositories = []
    for root, dirs, files in os.walk(BASE_DIRECTORY):
        if ".git" not in dirs:
            continue
        del dirs[:]
        repositories.append(Path(root).relative_to(BASE_DIRECTORY))
    return repositories


def _load_repos():
    global ALL_REPOS, LOCAL_ONLY_REPOS, REMOTE_ONLY_REPOS, COMMON_REPOS

    local_paths = _get_local_paths()
    remote_paths = {}
    for group in {path.partition("_")[0] for path in PATHS}:
        remote_paths.update(_get_all_projects(group))

    COMMON_REPOS = {
        path: id_ for path, id_ in sorted(remote_paths.items()) if path in local_paths
    }
    LOCAL_ONLY_REPOS = {path: None for path in sorted(local_paths) if path not in COMMON_REPOS}
    REMOTE_ONLY_REPOS = {
        path: id_ for path, id_ in remote_paths.items() if path not in COMMON_REPOS
    }
    ALL_REPOS = {
        path: remote_paths.get(path)
        for path in sorted(
            itertools.chain(
                COMMON_REPOS.keys(), LOCAL_ONLY_REPOS.keys(), REMOTE_ONLY_REPOS.keys()
            )
        )
    }


@click.group()
@click.pass_context
def main(ctx):
    _load_config()
    _load_repos()


@main.command(short_help="synchronise managed repositories")
@click.pass_context
def sync(ctx):
    # work out if the origin has been moved, or if has yet to be created
    for path in LOCAL_ONLY_REPOS:
        local = Repository(path)
        if local.worktree.is_empty:
            # means the repo has yet to be created
            click.secho(
                f"{click.style(str(path), bold=True)} has not been created in GitLab",
                fg="red",
            )
            continue
        initial_commit = local.worktree.initial_commit
        for remote, remote_id in REMOTE_ONLY_REPOS.items():
            response = GITLAB.get(
                f"https://gitlab.com/api/v4/projects/{remote_id}/repository/commits/{initial_commit}",
                params={"stats": False},
            )
            if response.status_code == 200:
                click.secho(
                    f"Found {click.style(str(local), bold=True)} was moved to {click.style(str(remote), bold=True)}",
                    fg="red",
                )
                shutil.move(local.local_path, Repository(remote).local_path)
                del REMOTE_ONLY_REPOS[local.path]
                local = remote
                COMMON_REPOS[remote.path] = remote.id
                break
        else:
            # means the repo has yet to be created
            click.secho(
                f"{click.style(str(path), bold=True)} has not been created in GitLab",
                fg="red",
            )
    # clone all the new remotes
    for path in REMOTE_ONLY_REPOS:
        # TODO: if debug, alyways let git output get to console (may need to tee)
        click.secho(f"Cloning {click.style(str(path), bold=True)}", fg="yellow")
        repo = Repository(path)
        repo.local_path.mkdir(parents=True, exist_ok=True)
        repo("clone", f"git@gitlab.com:{path}.git", ".", check=True)

    # update the rest
    for path in COMMON_REPOS:
        repo = Repository(path)
        repo.sync()


@main.command(short_help="list managed repositories")
@click.pass_context
def tree(ctx):
    for path in ALL_REPOS:
        colour = "green" if path in COMMON_REPOS else "yellow"
        icon = "↔" if path in COMMON_REPOS else "→" if path in LOCAL_ONLY_REPOS else "←"
        click.secho(f"{icon} {path}", fg=colour)


if __name__ == "__main__":
    main()
