package gitlabsync

import (
	"fmt"
	"regexp"
	"strings"
	"sync"

	gitlab_client "github.com/xanzy/go-gitlab"
)

type Service interface {
	RemoteRepos() ([]*remoteRepoInfo, error)
	CreateRepo(*remoteRepoInfo) error
	DeleteRepo(*remoteRepoInfo) error
	RenameRepo(*remoteRepoInfo, string) error
}

type Gitlab struct {
	client     *gitlab_client.Client
	userConfig *UserConfig
	pathConfig *PathConfig
}

// TODO(obristow): review. if only have RemoteRepos method, then this can avoid the struct
func NewGitlab(u *UserConfig, c *PathConfig) (*Gitlab, error) {
	client := gitlab_client.NewClient(nil, c.AccessToken)
	err := client.SetBaseURL(c.APIURL)
	if err != nil {
		return nil, err
	}
	return &Gitlab{client, u, c}, nil
}

func (s *Gitlab) RemoteRepos() ([]*remoteRepoInfo, error) {
	WORKERS := 4
	pat := regexp.MustCompile(fmt.Sprintf("%s(?:/|$)", strings.Join(s.pathConfig.RemotePaths, "|")))
	totalPages := 1
	errors := make(chan error)
	var allRepos []*remoteRepoInfo
	updateMutex := sync.Mutex{}
	finished := make(chan *interface{})

	for i := 1; i <= WORKERS; i++ {
		go func(i int) {
			defer func() { finished <- nil }()
			tried := false
			for page := i; !tried || i <= totalPages; i += WORKERS {
				tried = true
				perm := gitlab_client.GuestPermissions
				opt := &gitlab_client.ListProjectsOptions{
					ListOptions: gitlab_client.ListOptions{
						PerPage: 100,
						Page:    page,
					},
					MinAccessLevel: &perm,
				}
				ps, resp, err := s.client.Projects.ListProjects(opt)
				if err != nil {
					errors <- err
					return
				}
				var pageRepos []*remoteRepoInfo
				for _, p := range ps {
					if pat.MatchString(p.PathWithNamespace) {
						pageRepos = append(pageRepos, &remoteRepoInfo{
							AbsolutePath: p.PathWithNamespace,
							Id:           fmt.Sprintf("%d", p.ID),
						})
					}
				}
				updateMutex.Lock()
				allRepos = append(allRepos, pageRepos...)
				totalPages = resp.TotalPages
				updateMutex.Unlock()
			}
		}(i)
	}
	running := WORKERS
	for {
		select {
		case err := <-errors:
			fmt.Print(err)
			if err != nil {
				return nil, err
			}
		case <-finished:
			running -= 1
			if running == 0 {
				return allRepos, nil
			}
		}
	}
}

// TODO(obristow): review. delete (leaving remote as source of repos)
func (s *Gitlab) CreateRepo(l *remoteRepoInfo) error {
	sep := strings.LastIndex(l.AbsolutePath, "/")
	namespace, _, err := s.client.Namespaces.GetNamespace(l.AbsolutePath[:sep])
	if err == nil {
		_, _, err = s.client.Projects.CreateProject(&gitlab_client.CreateProjectOptions{
			Name:        gitlab_client.String(l.AbsolutePath[sep+1:]),
			NamespaceID: gitlab_client.Int(namespace.ID),
		})
	}
	return err
}

// TODO(obristow): review. delete (leaving remote as source of repos)
func (s *Gitlab) DeleteRepo(r *remoteRepoInfo) error {
	_, err := s.client.Projects.DeleteProject(r.AbsolutePath)
	return err
}

// TODO(obristow): review. delete (leaving remote as source of repos)
func (s *Gitlab) RenameRepo(r *remoteRepoInfo, path string) error {
	sep := strings.LastIndex(path, "/")
	namespace, _, err := s.client.Namespaces.GetNamespace(path[:sep])
	name := path[sep+1:]
	if err == nil {
		_, _, err = s.client.Projects.EditProject(r.AbsolutePath, &gitlab_client.EditProjectOptions{
			Name:        gitlab_client.String(name),
			NamespaceID: gitlab_client.Int(namespace.ID),
		})
	}
	r.AbsolutePath = path
	return err
}
