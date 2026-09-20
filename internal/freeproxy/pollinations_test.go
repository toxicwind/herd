package freeproxy

import (
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"testing"
)

func TestBudgetExhausted(t *testing.T) {
	drained := []byte(`{"choices":[{"message":{"content":"The account behind this API key doesn't have enough credits. Please [top up](https://enter.pollinations.ai/top-up)"}}]}`)
	if !budgetExhausted(drained) {
		t.Error("expected drained-budget body to be detected")
	}
	ok := []byte(`{"choices":[{"message":{"content":"HERD-POLL-LIVE"}}]}`)
	if budgetExhausted(ok) {
		t.Error("normal completion flagged as budget-exhausted")
	}
}

func proxyReq(t *testing.T, target string) *httputil.ProxyRequest {
	t.Helper()
	in, err := http.NewRequest("POST", "http://localhost/v1/chat/completions", nil)
	if err != nil {
		t.Fatal(err)
	}
	outURL, err := url.Parse(target)
	if err != nil {
		t.Fatal(err)
	}
	out := in.Clone(in.Context())
	out.URL = outURL
	out.RequestURI = ""
	return &httputil.ProxyRequest{In: in, Out: out}
}

func TestPollinationsKeylessSendsNoAuth(t *testing.T) {
	os.Unsetenv("POLLINATIONS_API_KEY")
	os.Unsetenv("POLLINATIONS_KEY")
	p := NewPollinationsProvider(nil)
	if p.keyed {
		t.Fatal("expected keyless mode with no env key")
	}
	if p.BaseURL() != "https://text.pollinations.ai/openai" {
		t.Errorf("keyless base should be the text route, got %s", p.BaseURL())
	}
	pr := proxyReq(t, "https://text.pollinations.ai/openai/v1/chat/completions")
	pr.In.Header.Set("Authorization", "Bearer client-should-be-stripped")
	p.proxy.Rewrite(pr)
	if h := pr.Out.Header.Get("Authorization"); h != "" {
		t.Errorf("keyless mode must not send Authorization, got %q", h)
	}
}

func TestPollinationsKeyedUsesGen(t *testing.T) {
	t.Setenv("POLLINATIONS_API_KEY", "test-key-123")
	p := NewPollinationsProvider(nil)
	if !p.keyed {
		t.Fatal("expected keyed mode with POLLINATIONS_API_KEY set")
	}
	if p.BaseURL() != "https://gen.pollinations.ai" {
		t.Errorf("keyed base should be gen, got %s", p.BaseURL())
	}
	pr := proxyReq(t, "https://gen.pollinations.ai/v1/chat/completions")
	p.proxy.Rewrite(pr)
	if h := pr.Out.Header.Get("Authorization"); h != "Bearer test-key-123" {
		t.Errorf("keyed mode must send real Bearer, got %q", h)
	}
	// P0 (pollinations-deep-audit-2026-06-27): key must never be in the URL.
	if pr.Out.URL.RawQuery != "" {
		t.Errorf("key material must never be in the URL query: %q", pr.Out.URL.RawQuery)
	}
	if pr.Out.URL.String() != "https://gen.pollinations.ai/v1/chat/completions" {
		t.Errorf("unexpected outbound URL: %s", pr.Out.URL.String())
	}
}

func TestPollinationsKeylessSingleModel(t *testing.T) {
	os.Unsetenv("POLLINATIONS_API_KEY")
	os.Unsetenv("POLLINATIONS_KEY")
	p := NewPollinationsProvider(nil)
	if len(p.Models()) != 1 || p.Models()[0] != "openai" {
		t.Errorf("keyless catalog must be exactly [openai], got %v", p.Models())
	}
	if !p.Handles("openai") {
		t.Error("keyless provider must handle openai")
	}
	for _, m := range []string{"gpt-oss", "gemma-4-31b", "openai-fast"} {
		if p.Handles(m) {
			t.Errorf("keyless provider must NOT handle %q (upstream 404s it)", m)
		}
	}
	if cap(p.sem) != 1 {
		t.Errorf("keyless concurrency semaphore must have capacity 1, got %d", cap(p.sem))
	}
}

func TestPollinationsKeyedFullCatalog(t *testing.T) {
	t.Setenv("POLLINATIONS_API_KEY", "test-key-123")
	p := NewPollinationsProvider(nil)
	if len(p.Models()) < 5 {
		t.Errorf("keyed catalog should be the full list, got %v", p.Models())
	}
	if !p.Handles("gpt-oss") {
		t.Error("keyed provider should handle gpt-oss")
	}
}
