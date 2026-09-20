package freeproxy

import (
	"context"
	"io"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strings"
	"time"
)

// LLM7Provider proxies to LLM7 (https://api.llm7.io, OpenAI-compatible).
//
// Evaluated 2026-09-20: the DOCUMENTED anonymous key ("Bearer unused") is
// REJECTED on /v1/chat/completions (invalid_api_key), and headerless calls
// get missing_api_key. Anonymous is dead — a real key from
// https://dash.llm7.io/#/api-keys is required (30 req/min free tier,
// 120/min with email). With LLM7_API_KEY set this provider is a clean
// keyed fallback next to pollinations in the registry.
// If no key, it is disabled (Handles always false) but still listed for health.
type LLM7Provider struct {
	base     string
	apiKey   string
	proxy    *httputil.ReverseProxy
	models   []string
	modelSet map[string]struct{}
}

// NewLLM7Provider builds the provider; key comes from LLM7_API_KEY.
func NewLLM7Provider() *LLM7Provider {
	base := "https://api.llm7.io"
	key := os.Getenv("LLM7_API_KEY")
	u, _ := url.Parse(base)
	transport := &http.Transport{
		Proxy:             http.ProxyFromEnvironment,
		ForceAttemptHTTP2: true,
		IdleConnTimeout:   90 * time.Second,
	}
	p := &LLM7Provider{
		base:   base,
		apiKey: key,
		// Curated from GET /v1/models 2026-09-20 (46 IDs); stable chat IDs.
		models: []string{
			"DeepSeek-V4-Flash-0731", "DeepSeek-V4.1-Flash",
			"GLM-5.3-Flash", "gemini-3-flash", "gemini-3.1-flash-lite",
			"gemini-3.7-flash", "claude-haiku-4-5",
			"Inkling", "Inkling-Small",
			"deepseek-v4-pro", "codestral-latest",
		},
		modelSet: make(map[string]struct{}),
	}
	for _, m := range p.models {
		p.modelSet[m] = struct{}{}
	}
	p.proxy = &httputil.ReverseProxy{
		Transport: transport,
		Rewrite: func(r *httputil.ProxyRequest) {
			r.SetURL(u)
			r.Out.Host = r.Out.URL.Host
			if p.apiKey != "" {
				// SECURITY P0 (pollinations-deep-audit-2026-06-27): the API key travels
				// ONLY in the Authorization: Bearer header -- NEVER as a URL query param.
				// Query-param keys leak into browser history, proxy logs, and (on GET image
				// paths) into every visitor page, letting anyone scrape and burn the shared
				// budget. POST + Bearer keeps the key server-side. No key-prefix console
				// logging either (their P2) -- this provider never logs key material.
				r.Out.Header.Set("Authorization", "Bearer "+p.apiKey)
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

func (l *LLM7Provider) ID() string       { return "llm7-free" }
func (l *LLM7Provider) BaseURL() string  { return l.base }
func (l *LLM7Provider) Models() []string { return l.models }
func (l *LLM7Provider) Handles(model string) bool {
	if l.apiKey == "" {
		return false
	}
	_, ok := l.modelSet[model]
	return ok
}
func (l *LLM7Provider) Proxy(w http.ResponseWriter, r *http.Request) error {
	l.proxy.ServeHTTP(w, r)
	return nil
}
func (l *LLM7Provider) Health(ctx context.Context) error {
	// /v1/models needs no auth — true liveness probe even without a key.
	req, _ := http.NewRequestWithContext(ctx, "GET", l.base+"/v1/models", nil)
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
