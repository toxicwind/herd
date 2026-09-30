package config

import (
	"os"
	"path/filepath"
	"testing"
)

// A config whose CORS block fails validation must still load: the loader
// falls back to the last-known-good policy and the server starts.
func TestLoadConfigCORSFallback(t *testing.T) {
	dir := t.TempDir()
	cfgPath := filepath.Join(dir, "config.yaml")

	goodYAML := `models:
  m:
    cmd: "echo hi --port ${PORT}"
security:
  cors:
    allowedOrigins: ["https://app.example.com"]
    allowCredentials: true
`
	if err := os.WriteFile(cfgPath, []byte(goodYAML), 0600); err != nil {
		t.Fatal(err)
	}
	cfg, err := LoadConfig(cfgPath)
	if err != nil {
		t.Fatalf("good config failed to load: %v", err)
	}
	if len(cfg.Security.CORS.AllowedOrigins) != 1 {
		t.Fatalf("good CORS not loaded: %+v", cfg.Security.CORS)
	}
	// The good policy must have been persisted for the fallback.
	if _, err := os.Stat(filepath.Join(dir, corsGoodBackupName)); err != nil {
		t.Fatalf("last-known-good CORS not persisted: %v", err)
	}

	// Now break the CORS block: credentials with a wildcard origin.
	badYAML := `models:
  m:
    cmd: "echo hi --port ${PORT}"
security:
  cors:
    allowedOrigins: ["*"]
    allowCredentials: true
`
	if err := os.WriteFile(cfgPath, []byte(badYAML), 0600); err != nil {
		t.Fatal(err)
	}
	cfg, err = LoadConfig(cfgPath)
	if err != nil {
		t.Fatalf("bad CORS config must not fail the load: %v", err)
	}
	// Fell back to the persisted good policy.
	if len(cfg.Security.CORS.AllowedOrigins) != 1 || cfg.Security.CORS.AllowedOrigins[0] != "https://app.example.com" {
		t.Errorf("fallback CORS = %+v, want the persisted good policy", cfg.Security.CORS)
	}
	if !cfg.Security.CORS.AllowCredentials {
		t.Errorf("fallback lost allowCredentials")
	}
	// The model config must be intact: only the CORS block was replaced.
	if _, ok := cfg.Models["m"]; !ok {
		t.Errorf("fallback lost the models block")
	}
}

// With no backup at all, a broken CORS block degrades to the permissive
// default rather than failing the load.
func TestLoadConfigCORSFallbackNoBackup(t *testing.T) {
	dir := t.TempDir()
	cfgPath := filepath.Join(dir, "config.yaml")
	badYAML := `models:
  m:
    cmd: "echo hi --port ${PORT}"
security:
  cors:
    allowedOrigins: ["*"]
    allowCredentials: true
`
	if err := os.WriteFile(cfgPath, []byte(badYAML), 0600); err != nil {
		t.Fatal(err)
	}
	cfg, err := LoadConfig(cfgPath)
	if err != nil {
		t.Fatalf("bad CORS config with no backup must not fail the load: %v", err)
	}
	if len(cfg.Security.CORS.AllowedOrigins) != 0 {
		t.Errorf("fallback CORS = %+v, want zero policy (permissive default)", cfg.Security.CORS)
	}
}

// Non-CORS load errors still fail closed.
func TestLoadConfigNonCORSErrorStillFails(t *testing.T) {
	dir := t.TempDir()
	cfgPath := filepath.Join(dir, "config.yaml")
	// Invalid capability modality: not a CORS problem.
	badYAML := `models:
  m:
    cmd: "echo hi --port ${PORT}"
    capabilities:
      in: ["telepathy"]
`
	if err := os.WriteFile(cfgPath, []byte(badYAML), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadConfig(cfgPath); err == nil {
		t.Errorf("non-CORS config error must still fail the load")
	}
}

// A corrupted backup is treated as absent, not trusted.
func TestLoadGoodCORSCorruptBackup(t *testing.T) {
	dir := t.TempDir()
	cfgPath := filepath.Join(dir, "config.yaml")
	if err := os.WriteFile(filepath.Join(dir, corsGoodBackupName), []byte("{not json"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, src := loadGoodCORS(cfgPath); src != "" {
		t.Errorf("corrupt backup treated as usable: %s", src)
	}
}
