"""Module for the collection and representation of information on repositories.

"""
import asyncio
import os
import pathlib
import subprocess
import attr
import typing

import aiohttp
import gitlab_sync

_DEV_NULL = open(os.devnull, "r+b")


@attr.s(auto_attribs=True)
class LocalRepository:
    base_path: pathlib.Path
    relative_path: pathlib.Path

    @property
    def absolute_path(self):
        return self.base_path / self.relative_path

    def git(self, *git_args, **run_kwargs):
        """Run a command in git using `subprocess.run` where `check=True` by default."""
        run_kwargs.setdefault("check", True)
        if not gitlab_sync.tee_git:
            run_kwargs.setdefault("stdout", _DEV_NULL)
            run_kwargs.setdefault("stderr", _DEV_NULL)
        command = ["git", "-C", str(self.absolute_path)] + list(git_args)
        return subprocess.run(command, **run_kwargs)

    def _get_gitlab_project_id(self):
        if not hasattr(self, "_gitlab_project_id"):
            result = self.git(
                "config",
                "--local",
                "gitlab-sync.project-id",
                stdout=subprocess.PIPE,
                universal_newlines=True,
                check=False,
            )
            if result.returncode:
                self._gitlab_project_id = None
            else:
                self._gitlab_project_id = int(result.stdout.rstrip())
        return self._gitlab_project_id

    def _set_gitlab_project_id(self, value):
        self.git(
            "config",
            "--local",
            "gitlab-sync.project-id",
            str(value),
        )
        self._gitlab_project_id = value

    def _get_gitlab_path(self):
        if not hasattr(self, "_gitlab_path"):
            result = self.git(
                "config",
                "--local",
                "gitlab-sync.gitlab-path",
                stdout=subprocess.PIPE,
                universal_newlines=True,
                check=False,
            )
            if result.returncode:
                self._gitlab_path = None
            else:
                self._gitlab_path = pathlib.Path(result.stdout.rstrip())
        return self._gitlab_path

    def _set_gitlab_path(self, value):
        self.git(
            "config",
            "--local",
            "gitlab-sync.gitlab-path",
            str(value),
        )
        self._gitlab_path = value

    gitlab_project_id = property(_get_gitlab_project_id, _set_gitlab_project_id)
    gitlab_path = property(_get_gitlab_path, _set_gitlab_path)

    def __str__(self):
        return str(self.gitlab_path)

    def __gt__(self, other):
        return self.absolute_path > other.absolute_path

    @classmethod
    def from_remote(cls, config, remote):
        """Return an instance suitable for cloning into."""
        if config.strip_path:
            relative_path = remote.gitlab_path.relative_to(config.paths[0])
        else:
            relative_path = remote.gitlab_path
        instance = cls(config.base_path, relative_path)
        instance._gitlab_path = remote.gitlab_path
        return instance


@attr.s(auto_attribs=True)
class GitlabRepository:
    gitlab_path: pathlib.Path
    gitlab_project_id: typing.Optional[int] = None

    def __str__(self):
        return str(self.gitlab_path)

    def __gt__(self, other):
        return self.gitlab_path > other.gitlab_path


@attr.s(auto_attribs=True)
class RemoteRepository:
    relative_path: pathlib.Path
    absolute_path: pathlib.Path
    gitlab_project_id: typing.Optional[int] = None


def enumerate_local(base_path):
    """Return all local repositories under a given path."""
    for root, dirs, files in os.walk(base_path):
        if ".git" not in dirs:
            continue
        del dirs[:]
        store_path = pathlib.Path(root).relative_to(base_path)
        repo = LocalRepository(base_path, store_path)
        yield repo


class NotAGroup(Exception):
    pass


class ProjectCollector(object):
    """
    Class to collect Repositories from GitLab using asynchronous HTTP
    requests to speed up traversing tree structures.

    """

    def __init__(self, config):
        self.config = config

    def filter_projects(self, projects):
        """Yield repository objects for projects of interest."""
        for project in projects:
            path = pathlib.Path(project["path_with_namespace"]).parts
            for filter_path in self.config.paths:
                filter_parts = filter_path.parts
                if path[:len(filter_parts)] == filter_parts:
                    yield GitlabRepository(pathlib.Path(project["path_with_namespace"]), project["id"])
                    break
            else:
                gitlab_sync.logger.debug(
                    "Skipping %s as it does not match a filter path",
                    project["path_with_namespace"],
                )

    async def _get_user_projects(self, user):
        projects = []
        async with self.session.get(
            "{}api/v4/users/{}/projects".format(self.config.gitlab_http, user),
            params={"per_page": 100, "page": 1, "simple": 1},
        ) as response:
            projects.extend(await response.json())
            next_page = response.headers.get("X-Next-Page")

        while next_page:
            async with self.session.get(
                "{}api/v4/users/{}/projects".format(self.config.gitlab_http, user),
                params={"per_page": 100, "page": next_page, "simple": 1},
            ) as response:
                projects.extend(await response.json())
                next_page = response.headers.get("X-Next-Page")

        return self.filter_projects(projects)

    async def _get_group_projects(self, group):
        projects = []
        async with self.session.get(
            "{}api/v4/groups/{}/projects".format(self.config.gitlab_http, group),
            params={"per_page": 100, "page": 1, "simple": 1},
        ) as response:
            data = await response.json()
            projects.extend(data)
            next_page = response.headers.get("X-Next-Page")

        while next_page:
            async with self.session.get(
                "{}api/v4/groups/{}/projects".format(self.config.gitlab_http, group),
                params={"per_page": 100, "page": next_page, "simple": 1},
            ) as response:
                projects.extend(await response.json())
                next_page = response.headers.get("X-Next-Page")

        return self.filter_projects(projects)

    async def _get_group_subgroups(self, group):
        """Yields a (sub)group names/ids"""
        groups = []
        async with self.session.get(
            "{}api/v4/groups/{}/subgroups".format(self.config.gitlab_http, group),
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
                "{}api/v4/groups/{}/subgroups".format(self.config.gitlab_http, group),
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
            projects = []
            for projects_future in asyncio.as_completed(
                [
                    asyncio.ensure_future(self._get_group_projects(group)) async
                    for group in self._get_group_subgroups(entity)
                ]
            ):
                projects.extend(await projects_future)
            return projects
        except NotAGroup:
            pass
        return await self._get_user_projects(entity)

    async def _get_paths(self, paths):
        entities = {path.parts[0] for path in paths}
        all_paths = []
        async with aiohttp.ClientSession(
            headers={"Private-Token": self.config.access_token}
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
                all_paths.extend(await paths)
        return all_paths

    def collect_paths(self):
        """
        Return a list of Repository object for projects under the given paths in GitLab.

        """
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self._get_paths(self.config.paths))


def enumerate_remote(config):
    """Return all repositories available to the given access token."""
    # TODO: return a generator which collects from asyncio
    # TODO: think how this can work where users want to clone everything under their user/group
    return ProjectCollector(config).collect_paths()
