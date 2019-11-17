[![PyPI version](https://badge.fury.io/py/gitlab-sync.svg)](https://badge.fury.io/py/gitlab-sync)
[![Build Status](https://travis-ci.org/Code0x58/gitlab-sync.svg?branch=master)](https://travis-ci.org/Code0x58/gitlab-sync)

# gitlab-sync
This provides the gitlab-sync tool which clones GitLab and updates repositories.

## Ideas

~~Providers are to their collections, as a~~ collections are to their repositories, as a repositories are to their branches.

Do not allow multiple ways to do the same thing.




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

```yaml
providers:
	gitlab-tracr:
	  service: gitlab
			api-token: "iujasduniuuhu3489djf"
	dummy:
		# this does not create/delete/move repos from anywhere
		# FIXME: this is really just the null provider + collection config
		service: dummy

collections:
	-	provider: gitlab-tracr
	  path: tracr/pcs/ # path always stripped
		directory: "~/src/gitlab.com/tracr/pcs"
		repositories:
			local: none/pull/sync - (), (copy), (create+delete+move) 
			remote: none/pull/sync - (), (create), (create+delete+move)
		branches:
			some-name-*:
				local: null/pull/sync
				remote: null/pull/sync
		commits:
			local: null/fast-forward/merge/force/rebase
			remote: null/fast-forward/merge/force/rebase
	  tags: # probably leave undefined in first implementation
			local: null/pull/sync
			remote: null/pull/sync
# branch-reconciliation: 
# resolution policy can be per run, e.g. revert, ask, manual, force
# working-tree policy:
# cleaning policy can be per run, e.g. abort, ask, manual, purge, stash
#			# branch level plugin
#			plugins:
#				run-on-commit: false
#		# collection level plugin
#		plugins:
#			run-on-commit: true # install post-commit hook - when to install?
#			poll-interval: "* * * * *" # use https://github.com/robfig/cron
# could have config to apply locally per-repo (e.g. merge/diff strats)

options:
	log:
		file: "/var/log/oof"
		size-limit: 1M
		count-limit: 5
```

### Repository and branch policies

These policies are used to determine what to do when changes are detected to the names/existence in the opposite repositories or branches.

A repository is dirty if it needs action, or it's branches are dirty.

A branch is dirty if it needs action, or it's commits are dirty? A branch is commits...

#### null

This ignores the changes.

#### pull

New repositories or branches will be created, but will fail if they already exist.

#### sync

A branch is considered deleted if one with the same name does not exist. How is a branch considered created? How does this fit with `git fetch --prune`? Sync policy is really to stop a mess of missing branches, but could this be done with some other policy combination with clean policy application on branches?

### Commit policies

The branch policy is defined on a collection, and tells git-sync what to do to branches during a run.

The patterns match the local branch name? What about the remote name? These can differ from the upstream... upstream is used in operations so should be the priority, also lets users change their upstreams for the behaviour. Just use the commit policies to set up local copies? Could have branch "functions"/plugins for complex behaviour.

The commit strategy is a branch reconciliation strategy when both exist. This strategy defines:

- equality (i.e. no work needed)
- reconciliation (what to try doing when work needed

As this has two sides, the operations must be compatible, e.g. dual merge doesn't work as never able to reach equality after diverging. Given two commits, a plan is made by looking at the operations.

Compatability (local, remote):

* none - none -> []
  * none - fast-forward -> [--ff-only]
* fast-toward - fast-forward (any goes first? stop when one succeeds) -> []
* merge - fast-forward -> [FFAFAP(local, remote)]
* merge - merge -> which merge goes first?

#### none

#### fast-foward

#### merge

#### force

#### rebase

| Policy      | Description                                                  | Deletion                                                     | Notes |
| ----------- | ------------------------------------------------------------ | ------------------------------------------------------------ | ----- |
| none        | do not do anything when there are changes on the corresponding local/remote branch | no branches will be created or deleted                       |       |
| fast-foward | fetch changes and attempt to fast-forward them in            | branches will be deleted if they are not present remotely but exist in some branch |       |
| merge       | fetch changes and attempt to merge them in                   |                                                              |       |
| rebase      | fetch changes and rebase onto them                           |                                                              |       |
| force       | fetch changes and use them                                   |                                                              |       |

### Patterns

You can use hidden YAML nodes, anchors, and [merge keys](https://yaml.org/type/merge.html) to reduce repition in your configuration.

```yaml
.my-pattern: &my-pattern
	repositories:
		local: none
collections:
	- provider:
		path:
		directory:
		<<: *my-pattern
```

#### mirroring

If you set the local policy for repositories and 

```yaml
.mirror: &mirror
  repositories:
    local: pull
  branches:
    *:
      local: pull
      commits:
        local: force
```

#### shared repositories

```yaml
.shared: &shared
  repositories:
    local: sync
  branches:
  	# the local master follows the remote
    master:
    	local: pull
    	commits:
    		local: fast-forward
    # branches following the _username-*_ pattern will be forced to match the local copy
    username-wip-*:
    	remote: sync
    	commits:
    		remote: force
    	plugin:
    		# automatically create/update a MR the subect + body set by head commit
    		gitlab-mr:
    			target: master
```

#### local fork

You can change the upstream of a branch? how does that play into the cleaning up?

```yaml
.local-fork: &local-fork
	repositories:
		local: pull
  branches:
  	forked-*:
  		commits:
  			# gets and rebase onto the tracked upstream
  			local: rebase
```



## Usage

```
<targets>=all|tree|subtree|current
$ git-sync [all|tree|current] ...
$ git-sync <targets> pull [--all|--head|--branch=]
$ git-sync <targets> checkout <branch> [--changes=drop|warn|]
$ git-sync <targets> policy --set=mirror
$ # git-sync <targets> log --since= --until= --type=
$ git-sync <targets> directories --null
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

### sync

Options:

* Fast-forward-only
* Rebase-only

## Extra

* nested strategies, e.g. mirror org and sync subgroup(s) - how are subgroup moves tracked? dangerous to squash differences if a branch moves, e.g. from sync (with work on) to a mirror that forces changes
* list git directories


## To do
 * separate out packages so it's clear where things are coming from
 * use Gitlab/Service interface to get remote repos and classify for ops
 * look up reccomended repo structure, maybe move code into pkg/
 * flesh out integration tests
 * cater for new repositories being made locally and pushed remotely
 * document/give example of extending for a new service provider

## Extension

Consider other service providers such as GitHub, gogs, then call just git-sync and propose for git packages?
