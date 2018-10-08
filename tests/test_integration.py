import os
import stat
import subprocess
import tempfile

import requests

import pytest
from grab import Grab


@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig):
    return os.path.join(str(pytestconfig.rootdir), "tests", "docker-compose.yml")


@pytest.fixture(scope="session")
def gitlab(docker_ip, docker_services, tmp_path_factory, pytestconfig):
    http_url = f"http://{docker_ip}:{docker_services.port_for('gitlab', 80)}"
    git_url = f"git+ssh://{docker_ip}:{docker_services.port_for('gitlab', 22)}"
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
    assert response.url == f"{http_url}/users/sign_in"

    # add vagrant insecure ssh key to keychain
    private_key = pytestconfig.rootdir / "tests/key.rsa"
    os.chmod(private_key, stat.S_IREAD)
    subprocess.run(["ssh-add", private_key], check=True)

    class Info:
        """A handle on the GitLab instance"""

        def __init__(self):
            self.http_url = http_url
            self.git_url = git_url
            self.root_session = requests.Session()
            self.root_session.auth = ("root", "password")

            self.username = "test-user"
            public_key = open(pytestconfig.rootdir / "tests/key.rsa.pub").read()
            self.token, self.session = self.make_user(self.username, public_key)

            self.make_user("spam-user")

        def __str__(self):
            return self.http_url

        def make_user(self, username, public_key=None):
            """Make a gitlab user and return a token and API session."""
            # sign/register in page - make new user as root can't log in
            g = Grab()
            g.clear_cookies()
            response = g.go(f"{self.http_url}/users/sign_in")
            assert response.url == f"{http_url}/users/sign_in"
            g.doc.set_input("new_user[name]", "name")
            g.doc.set_input("new_user[username]", username)
            g.doc.set_input("new_user[email]", f"{username}@example.com")
            g.doc.set_input("new_user[email_confirmation]", f"{username}@example.com")
            g.doc.set_input("new_user[password]", "password")
            response = g.submit("commit")
            assert response.url == f"{self.http_url}/dashboard/projects"

            g.go(f"{self.http_url}/profile/personal_access_tokens")
            g.doc.choose_form(id="new_personal_access_token")
            g.doc.set_input("personal_access_token[name]", "access-token")
            # g.doc.set_input("personal_access_token[scopes][]", "api")
            # doc.set_input doesn't work with multi-value checkboxes
            response = g.submit(
                make_request=True,
                submit_name="commit",
                extra_post={"personal_access_token[scopes][]": ["api"]},
            )
            assert response.url == f"{self.http_url}/profile/personal_access_tokens"

            dom = response.build_html_tree()
            element = dom.get_element_by_id("created-personal-access-token")
            token = element.attrib["value"]

            session = requests.Session()
            session.headers.update({"Private-Token": token})
            if public_key:
                response = session.post(
                    f"{self.http_url}/api/v4/user/keys",
                    json={"title": "key", "key": public_key},
                )
                response.raise_for_status()

            return (token, session)

        def delete_user(username):
            raise NotImplemented

        def make_runner(self, extra_config=[]):
            """Return a callable which makes config and executes gitlab-tree."""

            def run(*args):
                with tempfile.NamedTemporaryFile("w") as config:
                    config_lines = [
                        f'gitlab-url = "{self.http_url}"',
                        f'access-token = "{self.token}"',
                        f'paths = ["{self.username}"]',
                        f'base-directory = "{sync_root}"',
                    ] + extra_config
                    config.write("\n".join(config_lines))
                    os.environ["GITLAB_TREE_CONFIG"] = config.name
                    return subprocess.run(
                        ["python", "-m", "gitlab_tree.cli", *args],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )

            return run

    yield Info()

    subprocess.run(
        ["ssh-add", "-d", private_key], check=True
    )


def test_smoke(gitlab):
    print(gitlab.session.get(f"{gitlab.http_url}/api/v4/users").json())
    gitlab_sync = gitlab.make_runner()
    gitlab_sync("tree")
    gitlab_sync("sync")
    gitlab_sync("tree")
