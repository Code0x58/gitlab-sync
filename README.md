[![Build Status](https://travis-ci.org/Code0x58/gitlab-sync.svg?branch=master)](https://travis-ci.org/Code0x58/gitlab-sync)

## gitlab-sync
This provides the gitlab-sync tool which clones GitLab and updates repositories.

### Config
You will need to have [SSH access configured for GitLab](https://docs.gitlab.com/ee/ssh/), and
have created a [personal access token](https://docs.gitlab.com/ee/api/#personal-access-tokens)
with API access.


The config goes in `~/.config/gitlab-sync.toml` or `~/.gitlab-sync.toml`,
which is [TOML](https://github.com/toml-lang/toml).


```toml
["~/gitlab"]
# get the gitlab access token from running a command
access-token = ["pass", "GitLab/api-access-token"]
# access-token = "plaintext token in file"

# paths to clone from GitLab, can include slashes for groups/projects
paths = [ "mintel", "obristow" ]
```

### Usage
```
$ gitlab-sync local-update
```

## To do
 * flesh out integration tests
 * cater for new repositories being made
