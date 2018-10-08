import codecs
import os

from setuptools import setup

here = os.path.abspath(os.path.dirname(__file__))

with codecs.open(os.path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

TEST_REQUIRES = ["pytest>=3.9", "pytest-docker", "grab"]
setup(
    author="Oliver Bristow",
    author_email="github+pypi@oliverbristow.co.uk",
    name="gitlab-tree",
    use_scm_version=True,
    install_requires=["aiohttp", "click", "toml", "requests"],
    long_description=long_description,
    description="synchronise GitLab repositories",
    setup_requires=["setuptools_scm", "wheel", "pytest-runner"],
    tests_require=TEST_REQUIRES,
    extras_require={"test": TEST_REQUIRES},
    entry_points={"console_scripts": ["gitlab-tree = gitlab_tree.cli:main"]},
    packages=["gitlab_tree"],
    python_requires=">=3.7",
)
