package gitlabsync

import (
	"fmt"
	gitlab_client "github.com/xanzy/go-gitlab"
	"regexp"
	"strings"
	"sync"
)

type Service interface {
	RemoteRepos() ([]*remoteRepo, error)
	CreateRepo(*localRepo) error
	DeleteRepo(*remoteRepo) error
	RenameRepo(*remoteRepo, string) error
}

type Gitlab struct {
	client     *gitlab_client.Client
	userConfig *UserConfig
	pathConfig *PathConfig
}

func NewGitlab(u *UserConfig, c *PathConfig) (*Gitlab, error) {
	client := gitlab_client.NewClient(nil, c.AccessToken)
	err := client.SetBaseURL(c.APIURL)
	if err != nil {
		return nil, err
	}
	return &Gitlab{client, u, c}, nil
}

func (s *Gitlab) RemoteRepos() ([]*remoteRepo, error) {
	WORKERS := 4
	pat := regexp.MustCompile(fmt.Sprintf("%s(?:/|$)", strings.Join(s.pathConfig.RemotePaths, "|")))
	totalPages := 1
	errors := make(chan error)
	var allRepos []*remoteRepo
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
				var pageRepos []*remoteRepo
				for _, p := range ps {
					if pat.MatchString(p.PathWithNamespace) {
						pageRepos = append(pageRepos, &remoteRepo{
							Path: p.PathWithNamespace,
							Id:   fmt.Sprintf("%d", p.ID),
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

func (s *Gitlab) CreateRepo(l *localRepo) error {
	sep := strings.LastIndex(l.CurrentRelativePath, "/")
	namespace, _, err := s.client.Namespaces.GetNamespace(l.CurrentRelativePath[:sep])
	if err == nil {
		_, _, err = s.client.Projects.CreateProject(&gitlab_client.CreateProjectOptions{
			Name:        gitlab_client.String(l.CurrentRelativePath[sep+1:]),
			NamespaceID: gitlab_client.Int(namespace.ID),
		})
	}
	return err
}

func (s *Gitlab) DeleteRepo(r *remoteRepo) error {
	_, err := s.client.Projects.DeleteProject(r.Path)
	return err
}

func (s *Gitlab) RenameRepo(r *remoteRepo, path string) error {
	sep := strings.LastIndex(path, "/")
	namespace, _, err := s.client.Namespaces.GetNamespace(path[:sep])
	name := path[sep+1:]
	if err == nil {
		_, _, err = s.client.Projects.EditProject(r.Path, &gitlab_client.EditProjectOptions{
			Name:        gitlab_client.String(name),
			NamespaceID: gitlab_client.Int(namespace.ID),
		})
	}
	r.Path = path
	return err
}
