package freeproxy

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strings"
	"time"
)

// PollinationsProvider — the real free path (verified live 2026-09-20).
//
// This is NOT a hack: it is Pollinations' documented legacy anonymous lane.
// Their own 404 body says it outright: "The Pollinations legacy text API is being
// deprecated for authenticated users... Anonymous requests to text.pollinations.ai
// are NOT affected." Deliberate policy, not an accident.
//
//	POST https://text.pollinations.ai/openai/v1/chat/completions, NO key,
//	model "openai" (resolves to gpt-oss-20b) → HTTP 200 in ~240-550ms.
//
// Rules baked in from the deep-dig (2026-09-20):
//   - Exactly ONE anonymous model exists. /models lists only "openai-fast"
//     (tier "anonymous"); any other model name 404s. Keyless mode therefore
//     advertises and handles ONLY "openai". Do not request others.
//   - Anonymous lane allows 1 CONCURRENT request per IP ("Queue full for IP").
//     The provider serializes keyless upstream calls client-side (semaphore
//     of 1, bounded wait, 429 if the slot stays busy).
//   - Never touch the shared-key lane: classic GET /{prompt}?model=openai runs
//     on a shared server-side key whose budget is drained (the P0 key-leak
//     scenario live). The anonymous POST lane is the durable one.
//   - The old gen.pollinations.ai + dummy-Bearer ("pollinations-free-workaround")
//     approach is DEAD: the dummy bearer was only ever a TEST CASE, and gen's
//     OpenAI-compatible endpoint 401s ("A valid API key is required") without a
//     real key. Do not resurrect it.
//   - If POLLINATIONS_API_KEY is set (free at https://enter.pollinations.ai/keys),
//     the provider upgrades to gen.pollinations.ai/v1 (keyed: higher limits,
//     full catalog) and injects the real Bearer.
//
// SECURITY (pollinations-deep-audit-2026-06-27):
//
//	P0 — the API key travels ONLY in the Authorization: Bearer header, NEVER as
//	a URL query param. Their own code comments warn query keys leak into access
//	logs, referrers and browser history. POST + Bearer keeps the key server-side.
//	P2 — no key-prefix console logging either; this provider never logs key
//	material (presence bit only).
//
// Caveat: the keyless text route draws from a SHARED anonymous pollen budget.
// When the budget is exhausted the API still returns HTTP 200 but the content
// is a "not enough credits / top up" notice. The provider detects that,
// refuses to cache it, and sets X-FreeProxy-Budget-Exhausted: 1 so callers
// know to retry later instead of mistaking it for a completion.
type PollinationsProvider struct {
	base     string
	apiKey   string
	keyed    bool
	proxy    *httputil.ReverseProxy
	models   []string
	modelSet map[string]struct{}
	cache    Cache
	// sem serializes keyless upstream calls: the anonymous lane allows exactly
	// 1 concurrent request per IP. Keyed mode does not take the semaphore.
	sem chan struct{}
}

// keylessModels is the complete anonymous catalog: exactly one model.
// Anything else 404s upstream, so advertising more would only misroute.
var keylessModels = []string{"openai"}

var keyedModels = []string{
	"openai", "gemma-4-31b", "gpt-oss", "qwen3.8-27b", "muse-glimmer", "muse-spark-1.2",
	"nemotron-3.5-lightning", "glm-5.3", "kimi-k3", "grok-4.6", "deepseek/deepseek-v4-flash-vision-exp",
}

// NewPollinationsProvider builds the provider; key comes from
// POLLINATIONS_API_KEY (fallback POLLINATIONS_KEY). Empty key = free route.
func NewPollinationsProvider(cache Cache) *PollinationsProvider {
	apiKey := os.Getenv("POLLINATIONS_API_KEY")
	if apiKey == "" {
		apiKey = os.Getenv("POLLINATIONS_KEY")
	}
	// Free path first: keyless text route. Keyed users get gen.
	base := "https://text.pollinations.ai/openai"
	models := keylessModels
	keyed := false
	if apiKey != "" {
		base = "https://gen.pollinations.ai"
		models = keyedModels
		keyed = true
	}
	baseURL, _ := url.Parse(base)
	transport := &http.Transport{
		Proxy:               http.ProxyFromEnvironment,
		ForceAttemptHTTP2:   true,
		MaxIdleConns:        20,
		MaxIdleConnsPerHost: 10,
		IdleConnTimeout:     90 * time.Second,
	}
	p := &PollinationsProvider{
		base:     base,
		apiKey:   apiKey,
		keyed:    keyed,
		cache:    cache,
		models:   models,
		modelSet: make(map[string]struct{}),
		sem:      make(chan struct{}, 1),
	}
	for _, m := range p.models {
		p.modelSet[m] = struct{}{}
	}
	p.proxy = &httputil.ReverseProxy{
		Transport: transport,
		Rewrite: func(r *httputil.ProxyRequest) {
			r.SetURL(baseURL)
			r.Out.Host = r.Out.URL.Host
			// Keyed mode only: real Bearer. Keyless mode sends NO auth —
			// the dummy-bearer test hack is gone and stays gone.
			// SECURITY P0 (pollinations-deep-audit-2026-06-27): the API key
			// travels ONLY in the Authorization: Bearer header — NEVER as a
			// URL query param. Query-param keys leak into browser history,
			// proxy logs, and (on GET image paths) into every visitor page,
			// letting anyone scrape and burn the shared budget. POST + Bearer
			// keeps the key server-side. No key-prefix console logging either
			// (their P2) — this provider never logs key material.
			if p.keyed {
				r.Out.Header.Set("Authorization", "Bearer "+p.apiKey)
			} else {
				r.Out.Header.Del("Authorization")
			}
			r.Out.Header.Set("Content-Type", "application/json")
		},
		ModifyResponse: func(resp *http.Response) error {
			if strings.Contains(strings.ToLower(resp.Header.Get("Content-Type")), "text/event-stream") {
				resp.Header.Set("X-Accel-Buffering", "no")
			}
			return nil
		},
	}
	return p
}

func (p *PollinationsProvider) ID() string       { return "pollinations-free" }
func (p *PollinationsProvider) BaseURL() string  { return p.base }
func (p *PollinationsProvider) Models() []string { return p.models }
func (p *PollinationsProvider) Handles(model string) bool {
	_, ok := p.modelSet[model]
	return ok
}
func (p *PollinationsProvider) Health(ctx context.Context) error {
	// gen's /text/models is the no-auth models list (HTTP 200, verified).
	req, _ := http.NewRequestWithContext(ctx, "GET", "https://gen.pollinations.ai/text/models", nil)
	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return io.ErrUnexpectedEOF
	}
	return nil
}

// budgetExhausted sniffs a 200 response for the shared-budget-exhausted notice.
func budgetExhausted(body []byte) bool {
	s := string(body)
	return strings.Contains(s, "doesn't have enough credits") ||
		strings.Contains(s, "not enough credits") ||
		strings.Contains(s, "enter.pollinations.ai/top-up")
}

// serveUpstream proxies one request upstream. In keyless mode the anonymous
// lane is serialized: 1 concurrent request per IP ("Queue full for IP").
// Returns false if the concurrency slot stayed busy past the wait ceiling.
func (p *PollinationsProvider) serveUpstream(w http.ResponseWriter, r *http.Request) bool {
	if !p.keyed {
		select {
		case p.sem <- struct{}{}:
			defer func() { <-p.sem }()
		case <-time.After(30 * time.Second):
			http.Error(w, "pollinations: anonymous lane busy (1 concurrent/IP); retry shortly", http.StatusTooManyRequests)
			return false
		}
	}
	p.proxy.ServeHTTP(w, r)
	return true
}

func (p *PollinationsProvider) Proxy(w http.ResponseWriter, r *http.Request) error {
	// No artificial pacing: the real anonymous-lane constraint is 1 concurrent
	// request per IP, enforced by the semaphore in serveUpstream (event-driven,
	// not a timer). The old 1-req/15s guess is gone.
	if p.cache != nil && r.Method == "POST" && r.URL.Path == "/v1/chat/completions" {
		bodyBytes, _ := io.ReadAll(r.Body)
		r.Body = io.NopCloser(bytes.NewReader(bodyBytes))
		key := p.ID() + ":" + string(bodyBytes[:min(200, len(bodyBytes))])
		if cached, ok := p.cache.Get(key); ok {
			w.Header().Set("X-Cache", "HIT")
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(200)
			w.Write(cached)
			return nil
		}
		rec := newBufferingRecorder()
		r.Body = io.NopCloser(bytes.NewReader(bodyBytes))
		if !p.serveUpstream(rec, r) {
			rec.replay(w) // 429 from the concurrency gate
			return nil
		}
		if budgetExhausted(rec.body.Bytes()) {
			// Honest signal: shared budget empty right now — retry later.
			for k, vv := range rec.header {
				for _, v := range vv {
					w.Header().Add(k, v)
				}
			}
			w.Header().Set("X-FreeProxy-Budget-Exhausted", "1")
			w.WriteHeader(rec.status)
			w.Write(rec.body.Bytes())
			return nil
		}
		if rec.status == 200 {
			p.cache.Set(key, rec.body.Bytes(), 60*time.Second)
		}
		rec.replay(w)
		return nil
	}
	// Streaming / other paths: direct passthrough (serialized for keyless).
	p.serveUpstream(w, r)
	return nil
}

// bufferingRecorder captures the full response (status, headers, body) without
// writing to the underlying ResponseWriter, so the caller can inspect the
// body (budget sniffing, caching) before committing. Call replay(w) to flush.
type bufferingRecorder struct {
	header http.Header
	body   *bytes.Buffer
	status int
}

func newBufferingRecorder() *bufferingRecorder {
	return &bufferingRecorder{
		header: make(http.Header),
		body:   &bytes.Buffer{},
		status: 200,
	}
}

func (b *bufferingRecorder) Header() http.Header { return b.header }

func (b *bufferingRecorder) WriteHeader(code int) { b.status = code }

func (b *bufferingRecorder) Write(data []byte) (int, error) {
	return b.body.Write(data)
}

// replay flushes the buffered response to w.
func (b *bufferingRecorder) replay(w http.ResponseWriter) {
	for k, vv := range b.header {
		for _, v := range vv {
			w.Header().Add(k, v)
		}
	}
	w.WriteHeader(b.status)
	w.Write(b.body.Bytes())
}

// rewriteModel rewrites a model alias inside a JSON body.
func rewriteModel(body []byte, from, to string) []byte {
	var m map[string]any
	if err := json.Unmarshal(body, &m); err != nil {
		return body
	}
	if m["model"] == from {
		m["model"] = to
		if b, err := json.Marshal(m); err == nil {
			return b
		}
	}
	return body
}
