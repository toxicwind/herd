# Sovereign Mesh — Tool Federation Gateway & AST Matrix

**Port**: `:25127` (MCP Proxy Gateway) | `:25115` (Mesh Hub)  
**Role**: Federated tool routing, AST matrix code navigation, and MCP client aggregation.

---

## 🏛️ Topology

Mesh unifies the tool gateway, dynamic AST Matrix routers, and proxy daemons under a single workspace:

```
mesh/
├── gateway/      ← MCP Proxy Go gateway (mcpproxy-go) connecting 43+ upstream servers
├── router/       ← Sovereign router TS & Python routing services
├── ast-matrix/   ← AST Matrix code extraction and semantic matrix packages
└── config.yml    ← Unified mesh configuration & port mappings
```

---

## 🚀 Quick Verification

```bash
# Verify mesh-hub is responding
curl -sf http://127.0.0.1:25115/health

# Verify mesh MCP gateway
curl -sf http://127.0.0.1:25127/health
```
