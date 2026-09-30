package config

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"
)

// corsGoodBackupName is the file kept beside the config that stores the last
// CORS policy that validated. When a config edit breaks the CORS block, the
// loader falls back to this instead of refusing to start the server.
const corsGoodBackupName = ".herd-cors-good.json"

// corsValidationError marks a config load failure as CORS-specific so
// LoadConfig can degrade to the last-known-good policy instead of failing
// closed. A fallback is not a rollback: the server keeps moving forward on
// the last policy that worked.
type corsValidationError struct{ err error }

func (e *corsValidationError) Error() string { return e.err.Error() }
func (e *corsValidationError) Unwrap() error { return e.err }

// loadGoodCORS reads the last-known-good CORS policy from beside the config
// file. It returns the policy and where it came from; an empty source means
// no usable backup exists and the caller should degrade to the zero policy
// (legacy permissive). A backup that no longer validates is treated as
// absent: a stale escape hatch is worse than none.
func loadGoodCORS(configPath string) (CORSConfig, string) {
	p := filepath.Join(filepath.Dir(configPath), corsGoodBackupName)
	b, err := os.ReadFile(p)
	if err != nil {
		return CORSConfig{}, ""
	}
	var cors CORSConfig
	if err := json.Unmarshal(b, &cors); err != nil {
		return CORSConfig{}, ""
	}
	if err := cors.Validate(); err != nil {
		return CORSConfig{}, ""
	}
	return cors, p
}

// saveGoodCORS persists a validated CORS policy beside the config file. Only
// called after a successful load, so the backup is always a policy that
// worked. Best-effort: a failure is logged, never fatal.
func saveGoodCORS(configPath string, cors CORSConfig) error {
	b, err := json.Marshal(cors)
	if err != nil {
		return err
	}
	p := filepath.Join(filepath.Dir(configPath), corsGoodBackupName)
	return os.WriteFile(p, b, 0600)
}

// loadConfigWithCORSFallback reloads the config after replacing its broken
// CORS block with the last-known-good policy. With no usable backup it
// degrades to the zero CORSConfig, which selects the legacy permissive
// policy. Either way the server starts; the bad edit is logged loudly so it
// gets fixed instead of silently sticking.
func loadConfigWithCORSFallback(path string, loadErr error) (Config, error) {
	log.Printf("herd: WARNING: %v", loadErr)
	good, src := loadGoodCORS(path)
	if src == "" {
		log.Printf("herd: WARNING: no last-known-good CORS policy found; starting with the permissive default. Fix security.cors in %s", path)
	} else {
		log.Printf("herd: WARNING: falling back to last-known-good CORS policy from %s. Fix security.cors in %s", src, path)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return Config{}, err
	}
	var goodPtr *CORSConfig
	if src != "" {
		goodPtr = &good
	}
	patched, err := replaceCORSBlock(raw, goodPtr)
	if err != nil {
		return Config{}, fmt.Errorf("herd: CORS fallback: %w", err)
	}
	return LoadConfigFromReader(bytes.NewReader(patched))
}

// replaceCORSBlock returns the config YAML with its security.cors block
// replaced by cors. A nil cors deletes the key, which selects the legacy
// permissive policy. Macro expansion and every other validation still run in
// LoadConfigFromReader afterwards, so this changes nothing but the CORS
// block.
func replaceCORSBlock(raw []byte, cors *CORSConfig) ([]byte, error) {
	var doc map[string]any
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		return nil, fmt.Errorf("parsing config for CORS fallback: %w", err)
	}
	sec, _ := doc["security"].(map[string]any)
	if sec == nil {
		sec = make(map[string]any)
		doc["security"] = sec
	}
	if cors == nil {
		delete(sec, "cors")
	} else {
		var corsMap map[string]any
		if b, err := yaml.Marshal(cors); err != nil {
			return nil, fmt.Errorf("encoding CORS fallback: %w", err)
		} else if err := yaml.Unmarshal(b, &corsMap); err != nil {
			return nil, fmt.Errorf("encoding CORS fallback: %w", err)
		}
		sec["cors"] = corsMap
	}
	out, err := yaml.Marshal(doc)
	if err != nil {
		return nil, fmt.Errorf("re-encoding config for CORS fallback: %w", err)
	}
	return out, nil
}
