import codecs
import os

from setuptools import setup

here = os.path.abspath(os.path.dirname(__file__))

with codecs.open(os.path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

TEST_REQUIRES = ["pytest>=3.9", "pytest-docker", "grab", "requests"]
setup(
    author="Oliver Bristow",
    author_email="github+pypi@oliverbristow.co.uk",
    name="gitlab-sync",
    use_scm_version=True,
    install_requires=["aiohttp", "click", "toml", "voluptuous"],
    long_description=long_description,
    long_description_content_type="text/markdown",
    description="synchronise GitLab repositories",
    setup_requires=["setuptools_scm", "wheel", "pytest-runner", "attrs"],
    tests_require=TEST_REQUIRES,
    extras_require={"test": TEST_REQUIRES},
    entry_points={"console_scripts": ["gitlab-sync = gitlab_sync.cli:main"]},
    packages=["gitlab_sync"],
    python_requires=">=3.6",
)
