package gitlabsync

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strings"

	homedir "github.com/mitchellh/go-homedir"

	"github.com/BurntSushi/toml"
)

type UserConfig struct {
	// naming of the last two should be improvable
	PathConfigs               []PathConfig `toml:"path-config"`
	MaxParallelSyncs          uint         `toml:"max-parallel-syncs"`
	MaxParallelSyncOperations uint         `toml:"max-parallel-sync-operationns"`
}

type PathConfig struct {
	BasePath    string
	AccessToken string
	Strategy    string
	APIURL      string
	GitURL      string
	StripPath   bool
	RemotePaths []string
}

func (c *PathConfig) UnmarshalTOML(data interface{}) error {
	d, _ := data.(map[string]interface{})
	{ // required string/[]string -> string
		typeError := errors.New("path-configs.access-token must be a string or list of strings")
		i, exists := d["access-token"]
		if !exists {
			return errors.New("path-configs.access-token is required")
		}
		switch v := i.(type) {
		case string:
			c.AccessToken = v
		case []interface{}:
			if len(v) == 0 {
				return typeError
			}
			a := make([]string, len(v))
			for j, p := range v {
				s, ok := p.(string)
				if !ok {
					return typeError
				}
				a[j] = s
			}
			command := exec.Command(a[0], a[1:]...)
			out, err := command.Output()
			if err != nil {
				return fmt.Errorf("Getting the acess token failed with %q failed: %s", a, err)
			}
			c.AccessToken = strings.TrimSuffix(string(out), "\n")
		default:
			return fmt.Errorf("Bad %#v", v) //typeError
		}
	}
	{ // required string
		i, exists := d["base-path"]
		if !exists {
			return errors.New("path-configs.base-path is required")
		}
		v, ok := i.(string)
		if !ok {
			return errors.New("path-configs.base-path must be a string")
		}
		var err error
		c.BasePath, err = homedir.Expand(v)
		if err != nil {
			return err
		}
	}
	{ // required string
		i, exists := d["strategy"]
		if !exists {
			return errors.New("path-configs.strategy is required")
		}
		v, ok := i.(string)
		if !ok {
			return errors.New("path-configs.strategy must be a string")
		}
		c.Strategy = v
	}
	{ // optional string
		i, exists := d["http-url"]
		if exists {
			v, ok := i.(string)
			if !ok {
				return errors.New("path-configs.api-url must be a string")
			}
			c.APIURL = v
		} else {
			c.APIURL = "https://gitlab.com/"
		}
	}
	{ // optional string
		i, exists := d["git-url"]
		if exists {
			v, ok := i.(string)
			if !ok {
				return errors.New("path-configs.git-url must be a string")
			}
			c.GitURL = v
		} else {
			c.GitURL = "git+ssh://git@gitlab.com/"
		}
	}
	{ // optional bool
		i, exists := d["strip-path"]
		if exists {
			v, ok := i.(bool)
			if !ok {
				return errors.New("path-configs.strip-path must be a boolean")
			}
			c.StripPath = v
		} else {
			c.StripPath = false
		}
	}
	{ // optional []string
		typeError := errors.New("path-configs.paths must be a list of strings")
		i, exists := d["paths"]
		if exists {
			v, ok := i.([]interface{})
			if !ok {
				return typeError
			}
			a := make([]string, len(v))
			for j, p := range v {
				s, ok := p.(string)
				if !ok {
					return typeError
				}
				a[j] = s
			}
			c.RemotePaths = a
		} else {
			c.RemotePaths = []string{}
		}
	}
	return nil
}

// FIXME: separate file finding and loading, use ioutil to read bytes from file
// then have this method use that, then defaults can be tested
func LoadConfig() (*UserConfig, error) {
	// TODO: put the defaults in the userconfig instantiation - works for top level but not for lists/maps... have to use primitives/decode one at a time?
	var c *UserConfig
	// load in the base config (before validation+transforms)
	for _, p := range []string{
		"${GITLAB_SYNC_CONFIG}",
		"~/.config/gitlab-sync.toml",
		"~/.gitlab-sync.toml",
	} {
		var err error
		p, err = homedir.Expand(p)
		if err != nil {
			return nil, err
		}
		p := os.ExpandEnv(p)
		config := UserConfig{
			MaxParallelSyncs:          1,
			MaxParallelSyncOperations: 1,
		}

		_, err = toml.DecodeFile(p, &config)
		if err != nil {
			if os.IsNotExist(err) {
				continue
			}
			return nil, fmt.Errorf("Unable load %s: %s", p, err)
		}

		c = &config
		break
	}
	if c == nil {
		return nil, errors.New("No config file found")
	}

	return c, nil
}
