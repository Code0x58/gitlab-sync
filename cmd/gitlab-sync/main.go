package main

/*
# use YAML instead of TOML to allow easy provider info reuse
.GitLab: &GitLab
  provider:
	- name: gitlab
	- parameters:
	  access-token: heloo
UserConfig:
  PathConfig:
	- base-path: tracr/
	  local-prefix: /home/obristow/code/
	  strategy: pull
	  <<: *.GitLab
	  provider:
	    - name: gitlab
	      parameters:
			  - access-token: heloo
	   branches:
		 master:
		  strategy: mirror

Each repository found from the sources (including the local provider which uses the local-prefix) is bundled together to config-wide reconciliation:
struct Info {
	Provider *RepoService, // object implementing RepoService interface
	Id str, // id of the repo for the given provider
	LocalBasePath str, // base of repo locally according to config
	LocalRelativePath str, // platform/event-service
	RemotePath str, // tracr/pcs/plafrom/event-service
	RemoteUrl str, // git@github.com:/some/path
	Strategy str, // "pull" (local) + "push" (remote), "reset" (local) + "push" (remote)
}

// Read is implicit for all?
Service.Readable("branch-1") -> True
Service.Writable("master") -> False
join repos on (LocalBasePath, id) - will need to check config to avoid duplicate paths; what about nested paths e.g. groups? - just have to error nicely
anything with no existing local repo gets created?

type RefPolicy int

const (
	RefNull = RefPolicy iota
	RefPull
	RefSync
)

struct RefPolicyInfo {
	Local RefPolicy
	Remote RefPolicy
}

type CommitPolicy int

const (
	CommitNull CommitPolicy = iota
	CommitFastForward
	CommitMerge
	CommitForce
	CommitRebase
)

struct CommitPolicyInfo {
	Local CommitPolicy
	Remote CommitPolicy
}

struct Collection {
	Provider str
	Path str
	Directory str
	Tags RefPolicyInfo
	Branches map[str]RefPolicyInfo
	Commits CommitPolicyInfo
//	Plugins map[str]struct{}
}

struct Config {
	Collections []Collection
	Options [str]struct{}
}

*/
import (
	"fmt"

	gitlabsync "github.com/Code0x58/gitlab-sync"
)

func main() {
	c, err := gitlabsync.LoadConfig()
	if err != nil {
		panic(err)
	}
	fmt.Println(c)

	locals, _ := gitlabsync.LocalRepos(&c.PathConfigs[0])
	fmt.Println(locals)
	gl, err := gitlabsync.NewGitlab(c, &c.PathConfigs[0])
	remotes, err := gl.RemoteRepos()
	if err != nil {
		panic(err)
	}
	for _, r := range remotes {
		fmt.Println(*r)
	}

	/**
	if err != nil {
		panic(fmt.Errorf("Fatal error in config: %s\n", err))
	}

	// run a goroutine worker pool
	syncs := make(chan gitlabsync.SyncRun, c.MaxParallelSyncs)
	var wg sync.WaitGroup
	for i := uint(0); i < c.MaxParallelSyncs; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			sync := <-syncs
			fmt.Printf("%#v\n", sync.PathConfig)
			fmt.Printf("access-token: %s\n", sync.PathConfig.AccessToken)
			// gitlabsync.LocalRepos(&pathConfig)

			service, err := gitlabsync.NewGitlab(sync.UserConfig, sync.PathConfig)
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
			gitlabsync.newMetaSyncPlan(locals, remotes)
		}()
	}
	// feed the worker pool
	for id, pathConfig := range c.PathConfigs {
		syncs <- gitlabsync.SyncRun{id, c, &pathConfig}
	}
	// starve and wait for the pool to finish
	close(syncs)
	wg.Wait()
	**/
}
