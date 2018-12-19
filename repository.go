package gitlabsync

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

type localRepo struct {
	BasePath            string // base path on local system
	CurrentRelativePath string // current relative path on local system
	storedRelativePath  string // previous relative path on local system
	RemoteId            string // id of project in the remote service
}

type remoteRepo struct {
	Path string // path of the repo in service
	Id   string // id of project in service
}

// Run a git command on the local repository
func (l *localRepo) git(args ...string) *exec.Cmd {
	path := filepath.Join(l.BasePath, l.CurrentRelativePath)
	all_args := make([]string, len(args)+3)
	all_args[0] = "git"
	all_args[1] = "-C"
	all_args[2] = path
	copy(all_args[3:], args)
	return exec.Command("git", all_args...)
}

// Get a config item from the local repository, or an empty string
func (l *localRepo) config(name string) string {
	item := fmt.Sprintf("gitlab-sync.%s", name)
	out, _ := l.git("config", "--local", item).Output()
	return string(out)
}

func (l *localRepo) setConfig(name string, value string) error {
	item := fmt.Sprintf("gitlab-sync.%s", name)
	_, err := l.git("config", "--local", item, value).Output()
	// TODO(obristow): think about a panic in this situation
	return err
}

// Return the relative path that was last seen
func (l *localRepo) StoredRelativePath() string {
	if len(l.storedRelativePath) == 0 {
		l.storedRelativePath = l.config("relative-path")
	}
	return l.storedRelativePath
}

// create the local repository
func (l *localRepo) Create() error {
	_, err := l.git("init", ".").Output()
	if err != nil {
		return err
	}
	l.setConfig("relative-path", l.CurrentRelativePath)
	l.setConfig("remote-id", l.RemoteId)
	return nil
}

// rename the local repository
func (l *localRepo) Rename(relativePath string) error {
	// TODO(obristow): move to the given relative path
	/*
		out, err := l.git("init", ".").Output()
		l.CurrentRelativePath = relativePath
		l.setConfig("relative-path", relativePath)
	*/
	return nil
}

func loadLocalRepo(config *PathConfig, path string) (*localRepo, error) {
	currentRelativePath, _ := filepath.Rel(config.BasePath, path)

	l := &localRepo{
		BasePath:            config.BasePath,
		CurrentRelativePath: currentRelativePath,
	}
	l.StoredRelativePath()
	l.RemoteId = l.config("remote-id")
	return l, nil
}

func LocalRepos(config *PathConfig) (repos []*localRepo, err error) {
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
			repo, _ := loadLocalRepo(config, path)
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

/*
func RemoteRepos(config *PathConfig) []gitlabRepo {

}
*/
