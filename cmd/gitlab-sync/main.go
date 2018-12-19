package main

import (
	"fmt"
	//	"github.com/spf13/cobra"
	"github.com/Code0x58/gitlab-sync"
	"sync"
)

func main() {
	var c, err = gitlabsync.LoadConfig()
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
			fmt.Printf("%#v\n", sync.pathConfig)
			fmt.Printf("access-token: %s\n", sync.pathConfig.AccessToken)
			// gitlabsync.LocalRepos(&pathConfig)

			var remoteRepos []*remoteRepo
			{
				service, err := NewGitlab(s.userConfig, s.pathConfig)
				if err != nil {
					panic(err)
				}
				fmt.Print("About to get repos\n")
				remoteRepos, err = service.RemoteRepos()
				if err != nil {
					panic(err)
				}
				for _, remote := range remotes {
					fmt.Printf("%#v\n", *remote)
				}
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
}
