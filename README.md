## gitlab-tree
This provides the gitlab-tree tool which clones GitLab and updates repositories.

### Config
You will need to have [SSH access configured for GitLab](https://docs.gitlab.com/ee/ssh/), and
have created a [personal access token](https://docs.gitlab.com/ee/api/#personal-access-tokens)
with API access.


config goes in `~/.config/gitlab-tree.toml` or `~/.gitlab-tree.toml`
```toml
access-token = "9koXpg98eAheJpvBs5tK"
paths = [ "mintel", "obristow" ]
base-directory = "~/gitlab"
```

### Usage
```
$ gitlab-tree sync
$ gitlab-tree tree
```
