[![PyPI version](https://badge.fury.io/py/gitlab-sync.svg)](https://badge.fury.io/py/gitlab-sync)
[![Build Status](https://travis-ci.org/Code0x58/gitlab-sync.svg?branch=master)](https://travis-ci.org/Code0x58/gitlab-sync)

# gitlab-sync
This provides the gitlab-sync tool which clones GitLab and updates repositories.


## Config
You will need to have [SSH access configured for GitLab](https://docs.gitlab.com/ee/ssh/), and
have created a [personal access token](https://docs.gitlab.com/ee/api/#personal-access-tokens)
with API access.


The config goes in `~/.config/gitlab-sync.toml` or `~/.gitlab-sync.toml`,
which is [TOML](https://github.com/toml-lang/toml).


```toml
["~/team-x"]
access-token = "9koXpg98eAheJpvBs5tK"
# you can see the paths of groups from the URL on GitLab
paths = [ "path/to/team-x" ]
# strip the common prefix from the given path
strip-path = true
strategy = "mirror"

["~/gitlab"]
# get the gitlab access token from running a command
access-token = ["pass", "GitLab/api-access-token"]

# paths to clone from GitLab, can include slashes for groups/projects
paths = [ "mintel", "obristow" ]
strategy = "mirror"

```


## Usage
```
$ gitlab-sync local-update
```

### Strategies
You have to define a strategy for each local copy you define in config, the
strategy defines what will happen when gitlab-sync runs over the given copy.

#### mirror
 1. delete repositories which no longer exist remotely
 2. move repositories which have been moved remotely
 3. update local repositories
 4. clean local repositories (prune+gc)
 5. clone new repositories

This is good for having a local copy which you can use to perform searches
in using something like [`ag`](https://github.com/ggreer/the_silver_searcher).

The local copies should not be modified by users.


## To do
 * flesh out integration tests
 * cater for new repositories being made locally and pushed remotely
 * compare (toasted-)marshmallow as a replacement for attr+voluptious - marshmallow uses attr
