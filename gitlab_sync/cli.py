#!/usr/bin/env python
import asyncio
import itertools
import os
import shutil
import subprocess
import sys
from pathlib import Path

import click
import requests
import toml
from aiohttp import ClientSession

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
                return "%s(%r, %r)" % (type(self).__name__, {self.repo}, self.name)

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
                    "%s..refs/remotes/%s/%s" % (self.name, REMOTE_NAME, self.name),
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
        click.secho("Syncing " + click.style(str(self.path), bold=True), fg="blue")
        # TODO: work out what to do where the default branch isn't master/PRIMARY_BRANCH, e.g. mintel/presonal-dev/nick-test
        if not self.worktree:
            click.secho("cloning into new repository", fg="green", bold=True)
            self.local_path.mkdir(parents=True, exist_ok=True)
            self(
                "clone",
                "git@gitlab.com:%s.git" % (self.path,),
                ".",
                stdout=None,
                check=True,
            )
        elif self.worktree.branch == PRIMARY_BRANCH or self.worktree.is_empty:
            if not self.worktree.clean:
                click.secho("work tree is dirty", fg="red", bold=True)
                return
            # result = repo("pull", "origin", "master", "--tags", stderr=sys.stderr, stdout=sys.stdout)
            click.echo("Fetching from " + REMOTE_NAME)
            result = self("fetch", "--prune", "--tags", REMOTE_NAME)
            if result.returncode:
                click.secho(
                    "an error ocurred - has the repo been moved? Currently need manaual reconciliation",
                    fg="red",
                    bold=True,
                )
            else:
                if self.worktree.is_empty:
                    click.secho("repository is still empty", fg="green", bold=True)
                    return
                behind, ahead = self.worktree.branch.remote_changes
                if behind:
                    # can't fast foward in the changes as there are non-pushed local changes
                    click.secho(
                        "local {PRIMARY_BRANCH} has {behind} commants that aren't in {REMOTE_NAME}".format(
                            **locals()
                        ),
                        fg="red",
                        bold=True,
                    )
                    pass
                elif ahead:
                    click.secho(
                        "{ahead} new commits, resetting local {PRIMARY_BRANCH} to that of {REMOTE_NAME}".format(
                            **locals()
                        ),
                        fg="green",
                        bold=True,
                    )
                    self(
                        "reset",
                        "refs/remotes/{REMOTE_NAME}/{PRIMARY_BRANCH}".format(
                            **locals()
                        ),
                        "--hard",
                        check=True,
                    )
                else:
                    # up to date
                    click.secho(
                        "local {PRIMARY_BRANCH} is already up to date".format(
                            **locals()
                        ),
                        fg="green",
                        bold=True,
                    )
        else:
            click.secho(
                "local branch is %s instead of %s"
                % (self.worktree.branch, PRIMARY_BRANCH),
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
        return "%s(%r, %r)" % (type(self).__name__, {self.repo}, self.name)


ACCESS_TOKEN = None
BASE_DIRECTORY = None
GITLAB = None
PATHS = None
REMOTE_NAME = "origin"


def _load_config():
    global ACCESS_TOKEN, BASE_DIRECTORY, GITLAB, PATHS, REMOTE_NAME
    path = Path(os.path.expanduser("~"))
    if "GITLAB_TREE_CONFIG" in os.environ:
        # for tests
        locations = [os.environ("GITLAB_TREE_CONFIG")]
    else:
        locations = (path / ".config/gitlab-sync.toml", path / ".gitlab-sync.toml")
    for location in locations:
        if location.is_file():
            break
    else:
        raise ValueError(
            "Config does not exist in one of " + ", ".join(map(str, locations))
        )

    config = toml.load(str(location))
    if isinstance(config.get("access-token-command"), list):
        access_token_command = config["access-token-command"]
        result = subprocess.run(
            access_token_command,
            stdin=sys.stdin,
            stderr=sys.stderr,
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        )
        ACCESS_TOKEN = result.stdout.strip()
    elif isinstance(config.get("access-token"), str):
        ACCESS_TOKEN = config["access-token"]
    else:
        raise ValueError(
            "one of access-token or access-token-command is required and must be a string"
        )

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


class NotAGroup(Exception):
    pass


class ProjectCollector(object):
    """
    Class to collect project {path: id} from GitLab using asynchronous HTTP
    requests to speed up traversing tree structures.

    """

    async def _get_user_projects(self, user):
        projects = []
        async with self.session.get(
            "https://gitlab.com/api/v4/users/{user}/projects".format(**locals()),
            params={"per_page": 100, "page": 1, "simple": 1},
        ) as response:
            projects.extend(await response.json())
            next_page = response.headers.get("X-Next-Page")

        while next_page:
            async with self.session.get(
                "https://gitlab.com/api/v4/users/{user}/projects".format(**locals()),
                params={"per_page": 100, "page": next_page, "simple": 1},
            ) as response:
                projects.extend(await response.json())
                next_page = response.headers.get("X-Next-Page")

        return {
            Path(project["path_with_namespace"]): project["id"] for project in projects
        }

    async def _get_group_projects(self, group):
        projects = []
        async with self.session.get(
            "https://gitlab.com/api/v4/groups/{group}/projects".format(**locals()),
            params={"per_page": 100, "page": 1, "simple": 1},
        ) as response:
            data = await response.json()
            projects.extend(data)
            next_page = response.headers.get("X-Next-Page")

        while next_page:
            async with self.session.get(
                "https://gitlab.com/api/v4/groups/{group}/projects".format(**locals()),
                params={"per_page": 100, "page": next_page, "simple": 1},
            ) as response:
                projects.extend(await response.json())
                next_page = response.headers.get("X-Next-Page")

        return {
            Path(project["path_with_namespace"]): project["id"] for project in projects
        }

    async def _get_group_subgroups(self, group):
        """Yields a (sub)group names/ids"""
        groups = []
        async with self.session.get(
            "https://gitlab.com/api/v4/groups/{group}/subgroups".format(**locals()),
            params={"per_page": 100, "page": 1},
        ) as response:
            data = await response.json()
            if not isinstance(data, list):
                raise NotAGroup()
            groups.extend(data)
            next_page = response.headers.get("X-Next-Page")
        # yield the given group when we know it isn't a user
        yield group

        while next_page:
            async with self.session.get(
                "https://gitlab.com/api/v4/groups/{group}/subgroups".format(**locals()),
                params={"per_page": 100, "page": next_page},
            ) as response:
                data = await response.json()
                groups.extend(data)
                next_page = response.headers.get("X-Next-Page")

        for group_data in groups:
            yield group_data["id"]
            async for subgroup_id in self._get_group_subgroups(group_data["id"]):
                yield subgroup_id

    async def _get_entity_projects(self, entity):
        try:
            projects = {}
            for projects_future in asyncio.as_completed(
                [
                    asyncio.ensure_future(self._get_group_projects(group)) async
                    for group in self._get_group_subgroups(entity)
                ]
            ):
                projects.update(await projects_future)
            return projects
        except NotAGroup:
            pass
        return await self._get_user_projects(entity)

    async def _get_paths(self, paths):
        entities = {path.partition("_")[0] for path in paths}
        all_paths = {}
        async with ClientSession(
            headers={"Private-Token": ACCESS_TOKEN}
        ) as self.session:
            paths_futures = []
            for paths_future in asyncio.as_completed(
                [
                    asyncio.ensure_future(self._get_entity_projects(entity))
                    for entity in entities
                ]
            ):
                paths_futures.append(paths_future)
            for paths in asyncio.as_completed(paths_futures):
                all_paths.update(await paths)
        return all_paths

    def collect_paths(self, paths):
        """
        Return a dictionary of {path: id} for projects under the given paths in GitLab.

        """
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self._get_paths(paths))


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
    remote_paths = ProjectCollector().collect_paths(PATHS)

    COMMON_REPOS = {
        path: id_ for path, id_ in sorted(remote_paths.items()) if path in local_paths
    }
    LOCAL_ONLY_REPOS = {
        path: None for path in sorted(local_paths) if path not in COMMON_REPOS
    }
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
                click.style(str(path), bold=True) + " has not been created in GitLab",
                fg="red",
            )
            continue
        initial_commit = local.worktree.initial_commit
        for remote, remote_id in REMOTE_ONLY_REPOS.items():
            response = GITLAB.get(
                "https://gitlab.com/api/v4/projects/{remote_id}/repository/commits/{initial_commit}".format(
                    **local()
                ),
                params={"stats": False},
            )
            if response.status_code == 200:
                click.secho(
                    "Found "
                    + click.style(str(local), bold=True)
                    + " was moved to "
                    + click.style(str(remote), bold=True),
                    fg="red",
                )
                shutil.move(local.local_path, Repository(remote).local_path)
                del REMOTE_ONLY_REPOS[remote]
                del LOCAL_ONLY_REPOS[path]
                COMMON_REPOS[remote] = remote_id
                break
        else:
            # means the repo has yet to be created
            click.secho(
                click.style(str(path), bold=True) + " has not been created in GitLab",
                fg="red",
            )
    # clone all the new remotes
    for path in REMOTE_ONLY_REPOS:
        # TODO: if debug, alyways let git output get to console (may need to tee)
        click.secho("Cloning " + click.style(str(path), bold=True), fg="yellow")
        repo = Repository(path)
        repo.local_path.mkdir(parents=True, exist_ok=True)
        git_url = "git@gitlab.com:{path}.git".format(**locals())
        result = repo("clone", git_url, ".")
        if result.returncode:
            click.secho("unable to clone " + click.style(git_url, bold=True), fg="red")

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
        click.secho("{icon} {path}".format(**locals()), fg=colour)


if __name__ == "__main__":
    main()
