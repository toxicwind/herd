package server

import (
	"testing"

	"github.com/mostlygeek/llama-swap/internal/config"
)

// The provenance map must agree with renderCapabilities: every badge key it
// emits gets a source, and the source reflects config-vs-discovery origin.
func TestCapabilityProvenance(t *testing.T) {
	tests := []struct {
		name     string
		cfg      config.ModelCapConfig
		auto     config.ModelCapConfig
		wantKeys map[string]string
	}{
		{
			name: "all discovered",
			cfg:  config.ModelCapConfig{},
			auto: config.ModelCapConfig{In: []string{"text", "image"}, Out: []string{"text"}, Tools: true, Context: 128000},
			wantKeys: map[string]string{
				"vision": "discovered", "function_calling": "discovered", "context": "discovered",
			},
		},
		{
			name: "all configured",
			cfg:  config.ModelCapConfig{In: []string{"text", "image"}, Out: []string{"text"}, Tools: true, Context: 64000},
			auto: config.ModelCapConfig{},
			wantKeys: map[string]string{
				"vision": "configured", "function_calling": "configured", "context": "configured",
			},
		},
		{
			name: "mixed: config wins field by field",
			cfg:  config.ModelCapConfig{Tools: true},
			auto: config.ModelCapConfig{In: []string{"text", "image"}, Out: []string{"text"}, Context: 32000},
			wantKeys: map[string]string{
				"vision": "discovered", "function_calling": "configured", "context": "discovered",
			},
		},
		{
			name: "mixed modalities need both sides configured",
			cfg:  config.ModelCapConfig{In: []string{"text"}},
			auto: config.ModelCapConfig{Out: []string{"image"}},
			wantKeys: map[string]string{
				"image_generation": "discovered",
			},
		},
		{
			name:     "empty stays empty",
			cfg:      config.ModelCapConfig{},
			auto:     config.ModelCapConfig{},
			wantKeys: map[string]string{},
		},
		{
			name: "reranker and image_to_image",
			cfg:  config.ModelCapConfig{},
			auto: config.ModelCapConfig{In: []string{"image"}, Out: []string{"image"}, Reranker: true},
			wantKeys: map[string]string{
				"vision": "discovered", "image_to_image": "discovered", "reranker": "discovered",
			},
		},
		{
			name: "audio both directions",
			cfg:  config.ModelCapConfig{In: []string{"audio"}, Out: []string{"text"}},
			auto: config.ModelCapConfig{},
			wantKeys: map[string]string{
				"audio_transcriptions": "configured",
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := capabilityProvenance(tt.cfg, tt.auto)
			if len(got) != len(tt.wantKeys) {
				t.Fatalf("provenance keys = %v, want %v", got, tt.wantKeys)
			}
			for k, want := range tt.wantKeys {
				if got[k] != want {
					t.Errorf("provenance[%q] = %q, want %q", k, got[k], want)
				}
			}
			// Cross-check: every badge renderCapabilities draws must have a source.
			merged := tt.cfg.Merge(tt.auto)
			_, capsMap, _, _ := renderCapabilities(merged)
			for k := range capsMap {
				if _, ok := got[k]; !ok {
					t.Errorf("badge %q rendered but has no provenance", k)
				}
			}
		})
	}
}
