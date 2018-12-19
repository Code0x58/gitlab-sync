package gitlabsync

import (
	"github.com/stretchr/testify/assert"
	"testing"
)

func TestImplementsService(t *testing.T) {
	assert.Implements(t, (*Service)(nil), new(Gitlab))
}
