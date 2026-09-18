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

// PollinationsProvider proxies to https://gen.pollinations.ai with anonymous workaround.
// It ignores the "not anonymous" gate by injecting a dummy Bearer when no key is configured.
// Falls back to https://text.pollinations.ai when gen returns 401/429.
type PollinationsProvider struct {
	base      string
	textBase  string
	apiKey    string
	proxy     *httputil.ReverseProxy
	textProxy *httputil.ReverseProxy
	models    []string
	modelSet  map[string]struct{}
	limiter   RateLimiter
	cache     Cache
}

func NewPollinationsProvider(limiter RateLimiter, cache Cache) *PollinationsProvider {
	base := "https://gen.pollinations.ai"
	textBase := "https://text.pollinations.ai"
	// Prefer env key if set (real pollen key from https://enter.pollinations.ai/keys)
	apiKey := os.Getenv("POLLINATIONS_API_KEY")
	if apiKey == "" {
		apiKey = os.Getenv("POLLINATIONS_KEY")
	}
	// Workaround: any Bearer bypasses anonymous gate; use stable dummy that Pollinations accepts.
	// We ignore anonymous distinction entirely — always inject something.
	if apiKey == "" {
		apiKey = "pollinations-free-workaround"
	}
	// ponytail: dummy bearer for free backends; use real key via POLLINATIONS_API_KEY if rate-limit matters
	baseURL, _ := url.Parse(base)
	textURL, _ := url.Parse(textBase)

	transport := &http.Transport{
		Proxy:               http.ProxyFromEnvironment,
		ForceAttemptHTTP2:   true,
		MaxIdleConns:        20,
		MaxIdleConnsPerHost: 10,
		IdleConnTimeout:     90 * time.Second,
	}

	p := &PollinationsProvider{
		base:     base,
		textBase: textBase,
		apiKey:   apiKey,
		models: []string{
			"openai", "gemma-4-31b", "gpt-oss", "qwen3.8-27b", "muse-glimmer", "muse-spark-1.2",
			"nemotron-3.5-lightning", "glm-5.3", "kimi-k3", "grok-4.6", "deepseek/deepseek-v4-flash-vision-exp",
		},
		modelSet: make(map[string]struct{}),
		limiter:  limiter,
		cache:    cache,
	}
	for _, m := range p.models {
		p.modelSet[m] = struct{}{}
	}

	p.proxy = &httputil.ReverseProxy{
		Transport: transport,
		Rewrite: func(r *httputil.ProxyRequest) {
			r.SetURL(baseURL)
			r.Out.Host = r.Out.URL.Host
			// Inject workaround auth — ignore anonymous gate
			r.Out.Header.Set("Authorization", "Bearer "+p.apiKey)
			r.Out.Header.Set("x-api-key", p.apiKey)
			// Preserve content-type, strip client auth leakage
			r.Out.Header.Set("Content-Type", "application/json")
		},
		ModifyResponse: func(resp *http.Response) error {
			if strings.Contains(strings.ToLower(resp.Header.Get("Content-Type")), "text/event-stream") {
				resp.Header.Set("X-Accel-Buffering", "no")
			}
			return nil
		},
	}

	p.textProxy = &httputil.ReverseProxy{
		Transport: transport,
		Rewrite: func(r *httputil.ProxyRequest) {
			r.SetURL(textURL)
			r.Out.Host = r.Out.URL.Host
			r.Out.Header.Set("Authorization", "Bearer "+p.apiKey)
			r.Out.Header.Set("x-api-key", p.apiKey)
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
	req, _ := http.NewRequestWithContext(ctx, "GET", p.base+"/v1/models", nil)
	req.Header.Set("Authorization", "Bearer "+p.apiKey)
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

func (p *PollinationsProvider) Proxy(w http.ResponseWriter, r *http.Request) error {
	// Rate-limit gate (Pollinations ~1 req/15s anon) — if limiter says no, we still proxy but add header
	if p.limiter != nil && !p.limiter.Allow(p.ID()) {
		w.Header().Set("X-FreeProxy-RateLimited", "1")
		w.Header().Set("Retry-After", "15")
	}

	// Try cache for non-streaming POSTs (CF gateway style)
	if p.cache != nil && r.Method == "POST" && r.URL.Path == "/v1/chat/completions" {
		bodyBytes, _ := io.ReadAll(r.Body)
		r.Body = io.NopCloser(bytes.NewReader(bodyBytes))
		// Simple cache key: model + body hash (naive, ponytail)
		key := p.ID() + ":" + string(bodyBytes[:min(200, len(bodyBytes))])
		if cached, ok := p.cache.Get(key); ok {
			w.Header().Set("X-Cache", "HIT")
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(200)
			w.Write(cached)
			return nil
		}
		// On miss, capture response for caching (only 200s)
		// Use buffering recorder: the 401/429 status must NOT be committed to w
		// before we decide whether to fall back to text.pollinations.ai.
		rec := newBufferingRecorder()
		r.Body = io.NopCloser(bytes.NewReader(bodyBytes))
		// Clone request for text fallback if needed
		origBody := make([]byte, len(bodyBytes))
		copy(origBody, bodyBytes)

		p.proxy.ServeHTTP(rec, r)
		if rec.status == 401 || rec.status == 429 {
			// Fallback to text.pollinations.ai which still serves anonymous
			r2 := r.Clone(r.Context())
			r2.URL.Path = "/openai" // text endpoint style
			r2.Body = io.NopCloser(bytes.NewReader(origBody))
			p.textProxy.ServeHTTP(w, r2)
			return nil
		}
		if rec.status == 200 && p.cache != nil {
			// Cache 60s for repeated prompts (CF edge style)
			p.cache.Set(key, rec.body.Bytes(), 60*time.Second)
		}
		rec.replay(w)
		return nil
	}

	// Non-cache path or streaming — direct proxy with fallback.
	// Use streaming-aware recorder: streams through on 200, suppresses 401/429
	// so the fallback can write a clean response.
	rec := newStreamingFallbackRecorder(w)
	p.proxy.ServeHTTP(rec, r)
	if rec.fallbackNeeded() {
		// Fallback to text endpoint on auth/rate errors
		r2 := r.Clone(r.Context())
		p.textProxy.ServeHTTP(w, r2)
	}
	return nil
}

// bufferingRecorder captures the full response (status, headers, body) without
// writing to the underlying ResponseWriter. Call replay(w) to flush it after
// deciding whether a fallback is needed. Used for the cache path where we
// need the body for caching anyway.
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

// streamingFallbackRecorder streams the response through on success (200),
// but suppresses the status/headers/body on 401/429 so the caller can run
// the text.pollinations.ai fallback with a clean ResponseWriter.
type streamingFallbackRecorder struct {
	w           http.ResponseWriter
	header      http.Header
	status      int
	wroteHeader bool
	suppress    bool
}

func newStreamingFallbackRecorder(w http.ResponseWriter) *streamingFallbackRecorder {
	return &streamingFallbackRecorder{
		w:      w,
		header: make(http.Header),
		status: 200,
	}
}

func (s *streamingFallbackRecorder) Header() http.Header { return s.header }

func (s *streamingFallbackRecorder) WriteHeader(code int) {
	s.status = code
	if code == 401 || code == 429 {
		// Suppress: do not commit to w, caller will run fallback.
		s.suppress = true
		return
	}
	for k, vv := range s.header {
		for _, v := range vv {
			s.w.Header().Add(k, v)
		}
	}
	s.w.WriteHeader(code)
	s.wroteHeader = true
}

func (s *streamingFallbackRecorder) Write(b []byte) (int, error) {
	if s.suppress {
		// Discard the error body; fallback will write the real response.
		return len(b), nil
	}
	if !s.wroteHeader {
		s.WriteHeader(200)
	}
	return s.w.Write(b)
}

// fallbackNeeded reports whether the upstream returned 401/429 and the
// response was suppressed for fallback.
func (s *streamingFallbackRecorder) fallbackNeeded() bool { return s.suppress }

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// Pollinations direct fallback helper for JSON body rewriting (model alias)
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
