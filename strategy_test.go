package gitlabsync

import (
	"github.com/stretchr/testify/assert"
	"testing"
)

func TestNewMetaSyncPlan(t *testing.T) {
	// could be a whole log of for loops that permutate a field
	paths := []string{"", "a", "b"}
	remoteIds := []string{"", "1", "2"}
	ids := []string{"1", "2"}

	// FIXME: path can legitimately be "", should have a nillable one?

	// enumerate permutations of local repos
	local := localRepo{BasePath: "test-base"}
	for _, currentRelativePath := range paths {
		local.CurrentRelativePath = currentRelativePath
		for _, storedRelativePath := range paths {
			local.storedRelativePath = storedRelativePath
			for _, remoteId := range remoteIds {
				local.RemoteId = remoteId

				// and enumerate permutations of remote repos
				remote := remoteRepo{}
				for _, id := range ids {
					remote.Id = id
					for _, remotePath := range paths {
						remote.Path = remotePath
						plan := newMetaSyncPlan([]localRepo{local}, []remoteRepo{remote})

						if remote.Id == local.RemoteId {
							// we have a matched (local, remote) pair, check for moves
							if remote.Path == local.CurrentRelativePath {
								// no change
								assert.Equal(t, plan, metaSyncPlan{})
							} else if local.storedRelativePath == remote.Path {
								// move remote
								assert.Equal(t, plan, metaSyncPlan{
									RenameRemote: []repoPair{repoPair{&local, &remote}},
								})
							} else if local.CurrentRelativePath == local.storedRelativePath {
								// remote path changed
								assert.Equal(t, plan, metaSyncPlan{
									RenameLocal: []repoPair{repoPair{&local, &remote}},
								})
							} else {
								// rename resolve if CurrentRelativePath != storedRelativePath +
								//	remote.Path != CurrentRelativePath
								assert.Equal(t, plan, metaSyncPlan{
									RenameResolve: []repoPair{repoPair{&local, &remote}},
								})
							}
						} else {
							// creates or deletes are required
							if local.CurrentRelativePath == remote.Path { // storedRelativePath won't exist here
								// conflict
								assert.Equal(t, plan, metaSyncPlan{
									CreateResolve: []repoPair{repoPair{&local, &remote}},
								})
							} else if local.RemoteId == "" {
								// remote needs to be created from local
								assert.Equal(t, plan, metaSyncPlan{
									CreateRemote: []*localRepo{&local},
									CreateLocal:  []*remoteRepo{&remote},
								})
							} else {
								// there was a remote, but not now, so delete local
								assert.Equal(t, plan, metaSyncPlan{
									DeleteLocal: []*localRepo{&local},
									CreateLocal: []*remoteRepo{&remote},
								})
							}
							// there is no way to detect the need for a remote delete due to state being in the deleted
							// repo. It seems reasonable to avoid automatic remote deletes anyway.
						}
					}
				}
			}
		}
	}
}
