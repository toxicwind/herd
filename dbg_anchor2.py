#!/usr/bin/env python3
s = open("internal/server/server.go").read()
anchor = (
    "\t// Initialize cloud router (AST Matrix) if configured.\n"
    "\tvar cloud *astmatrix.Router\n"
    "\tif cfg.AstMatrix != nil && cfg.AstMatrix.Enabled {\n"
    "\t\tamCfg := &astmatrix.AstMatrixConfig{\n"
    "\t\t\tEnabled:     cfg.AstMatrix.Enabled,\n"
    "\t\t\tStrategy:    cfg.AstMatrix.Strategy,\n"
    "\t\t\tMaxParallel: cfg.AstMatrix.MaxParallel,\n"
    "\t\t\tDbPath:      cfg.AstMatrix.DbPath,\n"
    "\t\t\tStickyTTL:   cfg.AstMatrix.StickyTTL,\n"
    "\t\t\tFifoMax:     cfg.AstMatrix.FifoMax,\n"
    "\t\t}\n"
    "\t\tamCfg.Providers = make(map[string]astmatrix.ProviderCfg)\n"
    "\t\tfor name, pcfg := range cfg.AstMatrix.Providers {\n"
    "\t\t\tamCfg.Providers[name] = astmatrix.ProviderCfg{\n"
    "\t\t\t\tBaseURL:  pcfg.BaseURL,\n"
    "\t\t\t\tKeyEnv:   pcfg.KeyEnv,\n"
    "\t\t\t\tKeyEnvAlt: pcfg.KeyEnvAlt,\n"
    "\t\t\t\tNoAuth:   pcfg.NoAuth,\n"
    "\t\t\t}\n"
    "\t\t}\n"
    "\t\tcloud, err = astmatrix.NewRouter(amCfg, proxylog)\n"
    "\t\tif err != nil {\n"
    '\t\t\treturn nil, fmt.Errorf("creating astmatrix router: %w", err)\n'
    "\t\t}\n"
    '\t\tproxylog.Infof("astmatrix cloud router enabled: strategy=%s providers=%d", cfg.AstMatrix.Strategy, len(cloud.Matrix().Providers()))\n'
    "\t}"
)
print("full anchor in s:", anchor in s)
# find longest prefix that matches
i = s.find(anchor[:60])
print("start idx:", i)
seg = s[i:i+len(anchor)+5]
for n in range(len(anchor)):
    if seg[n] != anchor[n]:
        print("first diff at anchor offset", n)
        print("anchor:", repr(anchor[max(0,n-40):n+40]))
        print("actual:", repr(seg[max(0,n-40):n+40]))
        break
else:
    print("no diff found in overlap; len anchor", len(anchor), "len seg", len(seg))
