[![Build Status](https://travis-ci.org/Code0x58/gitlab-tree.svg?branch=master)](https://travis-ci.org/Code0x58/gitlab-tree)

## gitlab-sync
This provides the gitlab-sync tool which clones GitLab and updates repositories.

### Config
You will need to have [SSH access configured for GitLab](https://docs.gitlab.com/ee/ssh/), and
have created a [personal access token](https://docs.gitlab.com/ee/api/#personal-access-tokens)
with API access.


config goes in `~/.config/gitlab-sync.toml` or `~/.gitlab-sync.toml`
```toml
# use one of the following (the latter takes precident}
access-token = "9koXpg98eAheJpvBs5tK"
access-token-command = ["pass", "GitLab/api-access-token"]

# paths to clone from GitLab, can include slashes for groups/projects
paths = [ "mintel", "obristow" ]

base-directory = "~/gitlab"
```

### Usage
```
$ gitlab-sync sync
$ gitlab-sync tree
```
