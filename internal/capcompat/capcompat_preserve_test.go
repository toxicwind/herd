package capcompat

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// A probe that fails transiently (upstream down, 404s, timeouts) must not
// disturb the last-known capabilities: the UI keeps showing them instead of
// going blank. Only an upstream that answers and is genuinely unsupported
// drops the entry.
func TestCapcompat_RefreshPreservesLastKnownOnTransientFailure(t *testing.T) {
	fastRetries(t)
	good := newUpstream(t, map[string][]byte{
		"/v1/models": fixture(t, "llama-server", "v1_models.json"),
		"/props":     fixture(t, "llama-server", "props_vision.json"),
	})
	cache := newCountingCache()
	svc := New(cache, nil)

	require.NoError(t, svc.Refresh(context.Background(), "k", good.client(t), "model-a"))
	caps, found := svc.Lookup(context.Background(), "k")
	require.True(t, found)
	require.Equal(t, []string{"text", "image"}, caps.In)

	// The upstream goes away: every probe path 404s.
	down := newUpstream(t, map[string][]byte{})
	err := svc.Refresh(context.Background(), "k", down.client(t), "model-a")
	require.Error(t, err, "transient failure must still surface to the caller")

	// Last-known survives: same capabilities, still served, entry intact.
	caps, found = svc.Lookup(context.Background(), "k")
	require.True(t, found, "last-known capabilities must survive a failed refresh")
	assert.Equal(t, []string{"text", "image"}, caps.In)
	assert.True(t, cache.has("k"), "the cached entry must not be deleted on transient failure")
}
