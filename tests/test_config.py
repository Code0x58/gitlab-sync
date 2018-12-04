"""Test the functionality of the config module."""

from pathlib import Path

import gitlab_sync.config
from gitlab_sync import ConfigurationError
from voluptuous import Invalid, MultipleInvalid

import pytest


def test_find_config(tmpdir, monkeypatch):
    """Config is loaded in priority order."""
    monkeypatch.setattr(Path, "home", lambda: Path(tmpdir))
    with pytest.raises(ConfigurationError):
        gitlab_sync.config.find_config()

    # home dir config is lowest priority
    user = tmpdir / ".gitlab-sync.toml"
    user.write("")
    assert gitlab_sync.config.find_config() == Path(user)

    # ~/.config is middle priority
    tmpdir.mkdir(".config")
    config = tmpdir / ".config/gitlab-sync.toml"
    config.write("")
    assert gitlab_sync.config.find_config() == Path(config)

    # environ is highest priority and must exist
    environ = tmpdir / "gitlab-sync.toml"
    monkeypatch.setenv("GITLAB_SYNC_CONFIG", str(environ))
    with pytest.raises(ConfigurationError):
        gitlab_sync.config.find_config()

    environ.write("")
    assert gitlab_sync.config.find_config() == Path(environ)


def test_string_or_source_validator():
    """Takes a string or list and returns a string."""
    assert gitlab_sync.config.string_or_source("hello") == "hello"
    assert gitlab_sync.config.string_or_source(["echo", "hello"]) == "hello"


def test_absolute_dir_path_validator(tmpdir):
    """Takes a string and returns a Path if absolute."""
    assert gitlab_sync.config.absolute_dir_path(tmpdir) == Path(tmpdir)
    with pytest.raises(Invalid):
        gitlab_sync.config.absolute_dir_path("relative")
    assert gitlab_sync.config.absolute_dir_path("~") == Path.home()


def test_schema(tmpdir):
    """Must not be empty, and requires both access-token and paths."""
    with pytest.raises(MultipleInvalid):
        gitlab_sync.config.schema({})

    with pytest.raises(MultipleInvalid):
        gitlab_sync.config.schema({
            str(tmpdir): {"access-token": "hello"}
        })

    with pytest.raises(MultipleInvalid):
        gitlab_sync.config.schema({
            str(tmpdir): {"paths": ["parent"]}
        })

    assert gitlab_sync.config.schema({
        str(tmpdir): {
            "access-token": ["echo", "hello"],
            "paths": ["parent"],
            "strategy": "mirror",
        }
    }) == {
        Path(tmpdir): {
            "access_token": "hello",
            "paths": [Path("parent")],
            "strategy": gitlab_sync.strategy.mirror,
        }
    }

    assert gitlab_sync.config.schema({
        str(tmpdir): {
            "access-token": "hello",
            "paths": ["parent"],
            "gitlab-http": "https://example.com/",
            "strategy": "mirror",
        }
    }) == {
        Path(tmpdir): {
            "access_token": "hello",
            "paths": [Path("parent")],
            "gitlab_http": "https://example.com/",
            "strategy": gitlab_sync.strategy.mirror,
        }
    }


def test_find_and_load_config(tmpdir, monkeypatch):
    """Returns a map of paths to RunConfig objects."""
    config_file = tmpdir / "gitlab-sync.toml"
    config_file.write("""
        ["{tmpdir}"]
        access-token = "literal"
        paths = [ "parent1/child", "parent2" ]
        strategy = "mirror"
    """.format(tmpdir=tmpdir))

    monkeypatch.setenv("GITLAB_SYNC_CONFIG", str(config_file))
    config = gitlab_sync.config.find_and_load_config()
    assert config == {
        Path(tmpdir): gitlab_sync.config.RunConfig(
            base_path=Path(tmpdir),
            paths=[Path("parent1/child"), Path("parent2")],
            access_token="literal",
            strategy=gitlab_sync.strategy.mirror,
            strip_path=False,
        ),
    }
