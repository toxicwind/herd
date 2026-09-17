module github.com/mostlygeek/llama-swap/mesh/gateway

go 1.26

require (
	github.com/smart-mcp-proxy/mcpproxy-go v0.65.0
	github.com/gin-gonic/gin v1.10.0
	github.com/stretchr/testify v1.11.1
	gopkg.in/yaml.v3 v3.0.1
	go.uber.org/zap v1.28.0
)

require (
	github.com/chenzhuoyu/iasm v0.9.0 // indirect
	github.com/bytedance/sonic v1.11.6 // indirect
	github.com/klauspost/compress v1.18.5 // indirect
	github.com/mattn/go-isatty v0.0.20 // indirect
	github.com/mitchellh/mapstructure v1.5.0 // indirect
	github.com/pelletier/go-toml/v2 v2.2.3 // indirect
	github.com/spf13/pflag v1.0.5 // indirect
	golang.org/x/sys v0.45.0 // indirect
	golang.org/x/text v0.17.0 // indirect
	gopkg.in/yaml.v3 v3.0.1 // indirect
)

replace github.com/smart-mcp-proxy/mcpproxy-go => ../..
