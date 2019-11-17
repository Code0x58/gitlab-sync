package gitlabsync

import (
	"fmt"
	"os"
	"os/exec"
	"path"
	"path/filepath"
)

// TODO: make an interface for
// could use this with an interface like Get and Set
// then again, if this + remote are an interface, then localRepoInfo could be used in the generic methods like "Service.Create(local)" or CreateLocal(remote, config)
type localRepoInfo struct {
	// could be BasePath, e.g. /usr/obristow/code/, or git://git.github.com/
	localPath    string // path in filesystem - don't need more assuming users never move local directories relative to their base?
	Id           string `json:"id"`            // project Id
	AbsolutePath string `json:"absolute-path"` // e.g. org/group/project
	RelativePath string `json:"relative-path"` // e.g. group/project
	// strategy could be inferred from the status of each repo, like "canonical" or "source", "downstream"
	Strategy string `json:"strategy"` // this would imply both can record/report a stragegy; providers chould set the strat, e.g. from local system config
}

func LoadLocalRepo(path string) (l *localRepoInfo, err error) {
	// load a configured repo from the local filesystem
	l.localPath = path
	// TODO: get exceptions
	l.Id = l.config("id")
	l.AbsolutePath = l.config("absolute-path")
	l.RelativePath = l.config("relative-path")
	l.Strategy = l.config("strategy")
	return
}

// Run a git command on the local repository
func (l *localRepoInfo) git(args ...string) *exec.Cmd {
	all_args := make([]string, len(args)+3)
	all_args[0] = "git"
	all_args[1] = "-C"
	all_args[2] = l.localPath
	copy(all_args[3:], args)
	return exec.Command("git", all_args...)
}

// Get a config item from the local repository, or an empty string
func (l *localRepoInfo) config(name string) string {
	item := fmt.Sprintf("git-sync.%s", name)
	out, _ := l.git("config", "--local", item).Output()
	return string(out)
}

func (l *localRepoInfo) setConfig(name string, value string) (err error) {
	item := fmt.Sprintf("git-sync.%s", name)
	_, err = l.git("config", "--local", item, value).Output()
	// TODO(obristow): think about a panic in this situation
	return
}

func (l *localRepoInfo) save() {
	// TODO: return error or panic on failure
	l.setConfig("id", l.Id)
	l.setConfig("absolute-path", l.AbsolutePath) // can infer from base+prefix rules + path
	l.setConfig("relative-path", l.RelativePath) // path - base
	l.setConfig("strategy", l.Strategy)
}

// TODO: think about converting this to an interface so different providers can do it in their own package?
//  probably not much point as have to compile into code
type remoteRepoInfo struct {
	Id           string `json:"id"`
	AbsolutePath string `json:"absolute-path"`
}

func relativePath(path, prefix string) (p string, err error) {
	// return the path relative to the given prefix, or an error if it does not start with the prefix
	failure := fmt.Errorf("No common prefix!")
	for i := range prefix {
		if path[i] != prefix[i] {
			err = failure
		}
	}
	if len(prefix) == len(path) {
		p = ""
	} else if path[len(prefix)] == '/' {
		p = path[len(prefix)+1:]
	} else {
		err = failure
	}
	return
}

func (r *remoteRepoInfo) RelativePath(prefix string) (path string, err error) {
	// return the path relative to the given prefix, or an error if it does not start with the prefix
	return relativePath(r.AbsolutePath, prefix)
}

func NewLocalRepo(base string, r *remoteRepoInfo, strip string) (l *localRepoInfo, err error) {
	// return a local repo
	localRelative, err := relativePath(r.AbsolutePath, strip)
	if err != nil {
		return
	}
	l.localPath = path.Join(base, localRelative)
	l.Id = r.Id
	l.AbsolutePath = r.AbsolutePath
	l.RelativePath = localRelative
	l.Strategy = "mirror"
	err = l.git("init", ".").Run()
	if err != nil {
		err = fmt.Errorf("Unable to create new repository at %s for %s: %s", l.localPath, l.AbsolutePath, err)
		return nil, err
	}
	l.save()
	return
}

func LocalRepos(config *PathConfig) (repos []*localRepoInfo, err error) {
	err = filepath.Walk(config.BasePath, func(path string, info os.FileInfo, err error) error {

		if err != nil {
			return err
		}
		if !info.IsDir() {
			return nil
		}
		git, git_err := os.Lstat(filepath.Join(path, ".git"))
		if git_err != nil {
			return nil
		}
		if git.IsDir() {
			path = filepath.Dir(path)
			repo, _ := LoadLocalRepo(path)
			repos = append(repos, repo)
			return filepath.SkipDir
		}
		return nil
	})
	// TODO: move format up a level?
	if err != nil {
		return nil, fmt.Errorf("Failed finding local git repos for %s: %s", config.BasePath, err)
	}

	return repos, nil
}
