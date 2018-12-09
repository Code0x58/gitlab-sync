import os
import stat
import subprocess
import tempfile
import time

import requests
from grab import Grab

import pytest


@pytest.fixture(autouse=True)
def ssh_command(monkeypatch, pytestconfig):
    key = pytestconfig.rootdir / "tests/key.rsa"
    monkeypatch.setenv(
        "GIT_SSH_COMMAND",
        "ssh -i '%s' -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no" % key,
    )


@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig):
    return os.path.join(str(pytestconfig.rootdir), "tests", "docker-compose.yml")


@pytest.fixture(scope="function")
def gitlab(docker_ip, docker_services, tmp_path_factory, pytestconfig, tmpdir):
    """Manage a GitLab instance and return an object which can interact with it."""
    http_url = "http://%s:%s/" % (docker_ip, docker_services.port_for("gitlab", 80))
    git_url = "git+ssh://git@%s:%s/" % (docker_ip, docker_services.port_for("gitlab", 22))
    sync_root = tmp_path_factory.mktemp("sync-root")

    def is_responsive():
        try:
            response = requests.get(http_url)
            if response.status_code == 200:
                return True
        except requests.ConnectionError:
            return False

    docker_services.wait_until_responsive(
        timeout=5 * 60.0, pause=0.1, check=is_responsive
    )

    # "change" the default root password to get GitLab functional
    g = Grab()
    response = g.go(http_url)
    # change admin password page
    g.doc.set_input("user[password]", "password")
    g.doc.set_input("user[password_confirmation]", "password")
    response = g.submit()
    assert response.url == http_url + "users/sign_in"

    # add vagrant insecure ssh key to keychain
    private_key = str(pytestconfig.rootdir / "tests/key.rsa")
    os.chmod(str(private_key), stat.S_IREAD)

    class Info:
        """A handle on the GitLab instance"""

        def __init__(self):
            self.http_url = http_url
            self.git_url = git_url
            self.root_session = requests.Session()
            self.root_session.auth = ("root", "password")
            self.sync_root = sync_root

            self.username = "test-user"
            public_key = open(str(pytestconfig.rootdir / "tests/key.rsa.pub")).read()
            self.token, self.session = self.make_user(self.username, public_key)

            self.make_user("spam-user")

        def __str__(self):
            return self.http_url

        def make_user(self, username, public_key=None):
            """Make a gitlab user and return a token and API session."""
            # sign/register in page - make new user as root can't log in
            g = Grab()
            g.clear_cookies()
            response = g.go(self.http_url + "users/sign_in")
            assert response.url == http_url + "users/sign_in"
            g.doc.set_input("new_user[name]", "name")
            g.doc.set_input("new_user[username]", username)
            g.doc.set_input("new_user[email]", username + "@example.com")
            g.doc.set_input("new_user[email_confirmation]", username + "@example.com")
            g.doc.set_input("new_user[password]", "password")
            response = g.submit("commit")
            assert response.url == self.http_url + "dashboard/projects"

            g.go(self.http_url + "profile/personal_access_tokens")
            g.doc.choose_form(id="new_personal_access_token")
            g.doc.set_input("personal_access_token[name]", "access-token")
            # g.doc.set_input("personal_access_token[scopes][]", "api")
            # doc.set_input doesn't work with multi-value checkboxes
            response = g.submit(
                make_request=True,
                submit_name="commit",
                extra_post={"personal_access_token[scopes][]": ["api"]},
            )
            assert response.url == self.http_url + "profile/personal_access_tokens"

            dom = response.build_html_tree()
            element = dom.get_element_by_id("created-personal-access-token")
            token = element.attrib["value"]

            session = requests.Session()
            session.headers.update({"Private-Token": token})
            if public_key:
                response = session.post(
                    self.http_url + "api/v4/user/keys",
                    json={"title": "key", "key": public_key},
                )
                response.raise_for_status()

            return (token, session)

        def delete_user(username):
            raise NotImplemented

        def make_runner(self, extra_config=[]):
            """Return a callable which makes config and executes gitlab-sync."""

            def run(*args, **kwargs):
                with tempfile.NamedTemporaryFile("w") as config:
                    config_lines = [
                        '["%s"]' % self.sync_root,
                        'gitlab-http = "%s"' % self.http_url,
                        'gitlab-git = "%s"' % self.git_url,
                        'access-token = "%s"' % self.token,
                        'paths = ["%s"]' % self.username,
                        'strategy = "mirror"',
                    ] + extra_config
                    config.write("\n".join(config_lines))
                    config.flush()
                    env = os.environ.copy()
                    env["GITLAB_SYNC_CONFIG"] = config.name
                    return subprocess.run(
                        ["python", "-m", "gitlab_sync.cli", "-vvv"] + list(args),
                        env=env,
                        **kwargs,
                    )

            return run

        def make_project(self, **kwargs):
            """Make a project and return (id, ssh url)."""
            kwargs.setdefault("visibility", "public")
            response = self.session.post(
                self.http_url + "api/v4/projects",
                json=kwargs,
            )
            response.raise_for_status()
            data = response.json()

            path = data["path_with_namespace"]
            testing_project_path = tmpdir / path
            testing_project_path.ensure(dir=True)

            class TestRepo:
                def __init__(self, path, remote):
                    self.path = path
                    self.remote = remote
                    self.git("init", ".")
                    self.git("remote", "add", "origin", remote)
                    self.git("config", "--local", "user.email", "tester@example.com")
                    self.git("config", "--local", "user.name", "Tester")

                def git(self, *args, **kwargs):
                    kwargs.setdefault("check", True)
                    kwargs.setdefault("universal_newlines", True)
                    return subprocess.run(["git", "-C", str(self.path), *args], **kwargs)

            repo = TestRepo(testing_project_path, self.git_url + data["path_with_namespace"] + ".git")

            return data["id"], repo

        def delete_project(self, project_id):
            """Make a project and return (id, ssh url)."""
            project_url = self.http_url + "api/v4/projects/%s" % project_id
            response = self.session.delete(project_url)
            # the delete is asynchronus so wait for it
            response.raise_for_status()
            for _ in range(5):
                time.sleep(1)
                response = self.session.get(project_url)
                if response.status_code == 404:
                    return
            raise Exception("Project not deleted in time.")

    yield Info()


def test_mirror(gitlab, tmp_path_factory):
    """Check that a sync runs first time."""
    gitlab_sync = gitlab.make_runner()
    project_id, repo = gitlab.make_project(name="lulz")

    # make sure empty repositories work
    gitlab_sync("local-update", check=True)
    project_absolute_path = gitlab.sync_root / gitlab.username / "lulz"
    assert project_absolute_path.is_dir()

    # one file
    repo.git("init", ".")
    (repo.path / "README.md").write_text("Hello", "UTF8")
    repo.git("add", "README.md")
    repo.git("commit", "--message=Initial commit")
    repo.git("push", "--set-upstream", "origin", "master")
    gitlab_sync("local-update", check=True)
    assert (project_absolute_path / "README.md").is_file()

    # remote the file
    repo.git("rm", "README.md")
    repo.git("commit", "--message=Remote README.md")
    repo.git("push")
    gitlab_sync("local-update", check=True)
    assert project_absolute_path.is_dir()
    assert not (project_absolute_path / "README.md").is_file()

    # remote the project
    gitlab.delete_project(project_id)
    gitlab_sync("local-update", check=True)
    assert not project_absolute_path.is_dir()
