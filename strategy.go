package gitlabsync

import (
	"fmt"
)

type SyncRun struct {
	id         int
	UserConfig *UserConfig
	PathConfig *PathConfig
}

type repoPair struct {
	local  *localRepoInfo
	remote *remoteRepoInfo
}

// really a sync/strat thing, and put it in there rather than on localRepo, really inside a loop once
func branchSyncInfo(l *localRepoInfo, branch string) (ahead uint, behind uint, err error) {
	// could have error like non-common history
	// git rev-list --left-right --count {local}..{remote}
	return
}

// plan for syncing repo metadata + default branch
type metaSyncPlan struct {
	// need pair
	DeleteResolve []repoPair // can't happen as remote deltes not detectable
	DeleteLocal   []*localRepoInfo
	DeleteRemote  []*remoteRepoInfo // Not currently detectable
	// need pair
	RenameResolve []repoPair
	RenameLocal   []repoPair
	RenameRemote  []repoPair
	// need pair
	CreateResolve []repoPair
	CreateRemote  []*localRepoInfo
	CreateLocal   []*remoteRepoInfo
}

// separated out for ease of testing
func newMetaSyncPlan(locals []localRepoInfo, remotes []remoteRepoInfo) (plan metaSyncPlan) {
	pairs := make(map[string]repoPair)
	// work out what has to be created+deleted, and find pairs
	{
		localMap := make(map[string]*localRepoInfo)
		createRemote := make(map[string]*localRepoInfo)
		for _, local := range locals {
			if len(local.Id) != 0 {
				localMap[local.Id] = &local
			} else {
				// FIXME: this is miles off because ...
				createRemote[local.RelativePath] = &local
			}
		}
		for _, remote := range remotes {
			local, exists := localMap[remote.Id]
			if !exists {
				if local, exists = createRemote[remote.AbsolutePath]; exists {
					plan.CreateResolve = append(plan.CreateResolve, repoPair{local, &remote})
					delete(createRemote, remote.AbsolutePath)
				} else {
					plan.CreateLocal = append(plan.CreateLocal, &remote)
				}
				continue
			}
			pairs[remote.Id] = repoPair{local, &remote}
			// TODO: pop from local map, then remaining ones are for DeleteLocal
			delete(localMap, remote.Id)
		}
		// case in these next two loops which should produce CreateResolve? humm, could also be "paired DeleteLocal/CreateRemote"
		for _, local := range localMap {
			plan.DeleteLocal = append(plan.DeleteLocal, local)
		}
		for _, remote := range createRemote {
			plan.CreateRemote = append(plan.CreateRemote, remote)
		}
	}
	// work out renames
	for _, pair := range pairs {
		// FIXME(obristow): slammed the shit out of these branches just to compile
		if pair.local.AbsolutePath != pair.remote.AbsolutePath {
			if pair.local.AbsolutePath == pair.remote.AbsolutePath {
				plan.RenameRemote = append(plan.RenameRemote, pair)
			} else if pair.local.AbsolutePath == pair.local.AbsolutePath {
				plan.RenameLocal = append(plan.RenameLocal, pair)
			} else {
				plan.RenameResolve = append(plan.RenameResolve, pair)
			}
		}
	}

	return
}

// probably want to roll use of SyncRun into plan, e.g. make plan return a struct
// that a strategy can use
func newMetaSyncPlanz(s *SyncRun) {
	service, err := NewGitlab(s.UserConfig, s.PathConfig)
	if err != nil {
		panic(err)
	}
	fmt.Print("About to get repos\n")
	remotes, err := service.RemoteRepos()
	if err != nil {
		panic(err)
	}
	for _, remote := range remotes {
		fmt.Printf("%#v\n", *remote)
	}
	// is there a way to logically enumerate the scenarios and classify them?
	// itertools.product(local_states, remote_states)
	// if (local.stored_path == ...): assert plan.thing
	// DeleteLocal if id in local but not remote
	// DeleteRemote if ... (no way to know without state between runs)
	// DeleteResolve if ... removed locally updated remotely

	// RenameLocal if stored path is same as current, but path in remote is new
	// RenameRemote if stored path is different, but path in remote is stored
	// RenameResolve if stored path is different, and path in remote matches neither
	// what about when both places move? need to update stored path

	// CreateRemote if local repo with no stored remote id
	// CreateLocal if no matching repo id in locals
	// CreateResolve is ones that would have overlapping path in CreateLocal & CreateRemote
}
