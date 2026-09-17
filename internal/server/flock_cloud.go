package server

// flockCloud delegates cloud-model serving to Flock (http://127.0.0.1:8000),
// the unified multi-provider remote-API/completions subsystem.
//
// It replaces the retired in-process astmatrix.Router (2026-09-17): herd no
// longer routes cloud providers itself. Flock owns the provider pools,
// health/circuit state, retries and failover; herd is a thin reverse proxy
// that authenticates with its own FLOCK_API_KEY and rewrites configured
// model aliases to the upstream IDs the account actually serves.

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"sync"
	"time"

	"github.com/mostlygeek/llama-swap/internal/config"
	"github.com/mostlygeek/llama-swap/internal/logmon"
	"github.com/mostlygeek/llama-swap/internal/shared"
)

// flockModelsCacheTTL bounds how long herd trusts its snapshot of Flock's
// /v1/models listing for Handles() and discovery.
const flockModelsCacheTTL = 60 * time.Second

type flockCloud struct {
	baseURL  *url.URL
	apiKey   string
	modelMap map[string]string

	proxy *httputil.ReverseProxy
	log   *logmon.Monitor

	mu           sync.Mutex
	cachedModels []string
	cachedAt     time.Time
}

// newFlockCloud builds the Flock delegation handler. The API key is resolved
// once from cfg.KeyEnv so per-request env lookups don't happen on the hot path.
func newFlockCloud(cfg *config.FlockConfig, log *logmon.Monitor) *flockCloud {
	base, err := url.Parse(cfg.BaseURL)
	if err != nil || base.Host == "" {
		base = &url.URL{Scheme: "http", Host: "127.0.0.1:8000"}
	}
	f := &flockCloud{
		baseURL:  base,
		modelMap: cfg.ModelMap,
		log:      log,
	}
	if f.modelMap == nil {
		f.modelMap = map[string]string{}
	}
	if cfg.KeyEnv != "" {
		f.apiKey = os.Getenv(cfg.KeyEnv)
	}

	target := *base
	f.proxy = &httputil.ReverseProxy{
		Director: func(req *http.Request) {
			req.URL.Scheme = target.Scheme
			req.URL.Host = target.Host
			req.Host = target.Host
			// Upstream auth is herd's own Flock client key, not the caller's
			// herd key (already validated by herd's auth middleware).
			if f.apiKey != "" {
				req.Header.Set("Authorization", "Bearer "+f.apiKey)
			}
			req.Header.Set("X-Forwarded-By", "herd-flock-delegation")
		},
		ModifyResponse: func(resp *http.Response) error {
			resp.Header.Set("X-Served-By", "flock")
			return nil
		},
		ErrorHandler: func(w http.ResponseWriter, r *http.Request, err error) {
			if f.log != nil {
				f.log.Warnf("flock delegation failed: %v", err)
			}
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusBadGateway)
			fmt.Fprintf(w, `{"error":{"code":"flock_unreachable","message":"cloud delegation to Flock failed","type":"proxy_error"}}`)
		},
	}
	return f
}

// Aliases returns the configured local-alias -> upstream-ID map.
func (f *flockCloud) Aliases() map[string]string {
	return f.modelMap
}

// Handles reports whether modelID is a configured alias or is served by Flock.
func (f *flockCloud) Handles(modelID string) bool {
	if modelID == "" {
		return false
	}
	if _, ok := f.modelMap[modelID]; ok {
		return true
	}
	for _, id := range f.ModelIDs() {
		if id == modelID {
			return true
		}
	}
	return false
}

// ModelIDs returns Flock's served model IDs (cached 60s), for /v1/models discovery.
func (f *flockCloud) ModelIDs() []string {
	f.mu.Lock()
	defer f.mu.Unlock()
	if time.Since(f.cachedAt) < flockModelsCacheTTL && f.cachedModels != nil {
		return f.cachedModels
	}
	ids := f.fetchModelIDs()
	f.cachedModels = ids
	f.cachedAt = time.Now()
	return ids
}

func (f *flockCloud) fetchModelIDs() []string {
	u := *f.baseURL
	u.Path = "/v1/models"
	req, err := http.NewRequest(http.MethodGet, u.String(), nil)
	if err != nil {
		return nil
	}
	if f.apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+f.apiKey)
	}
	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		if f.log != nil {
			f.log.Warnf("flock /v1/models fetch failed: %v", err)
		}
		return nil
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	if err != nil || resp.StatusCode != http.StatusOK {
		return nil
	}
	var listing struct {
		Data []struct {
			ID string `json:"id"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &listing); err != nil {
		return nil
	}
	ids := make([]string, 0, len(listing.Data))
	for _, m := range listing.Data {
		if m.ID != "" {
			ids = append(ids, m.ID)
		}
	}
	return ids
}

// ServeHTTP implements http.Handler: rewrites configured model aliases to the
// upstream IDs the account serves, then reverse-proxies to Flock's /v1.
func (f *flockCloud) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if model, err := shared.ExtractModel(r); err == nil && model != "" {
		if upstream, ok := f.modelMap[model]; ok && upstream != "" {
			if nr, rerr := shared.ReplaceRequestModel(r, model, upstream); rerr == nil {
				r = nr
				if f.log != nil {
					f.log.Debugf("flock: alias %q -> upstream %q", model, upstream)
				}
			}
		}
	}
	// Normalize the body after any rewrite so ContentLength stays exact.
	if r.Body != nil {
		if body, err := io.ReadAll(r.Body); err == nil {
			r.Body.Close()
			r.Body = io.NopCloser(bytes.NewReader(body))
			r.ContentLength = int64(len(body))
		}
	}
	f.proxy.ServeHTTP(w, r)
}
