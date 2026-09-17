#!/usr/bin/env python3
import sys
s = open("internal/server/server.go").read()
lines = [
    "\tif cfg.AstMatrix != nil && cfg.AstMatrix.Enabled {",
    "\t\tamCfg := &astmatrix.AstMatrixConfig{",
    "\t\t\tEnabled:     cfg.AstMatrix.Enabled,",
    "\t\t\tStrategy:    cfg.AstMatrix.Strategy,",
    "\t\t\tMaxParallel: cfg.AstMatrix.MaxParallel,",
    "\t\t\tDbPath:      cfg.AstMatrix.DbPath,",
    "\t\t\tStickyTTL:   cfg.AstMatrix.StickyTTL,",
    "\t\t\tFifoMax:     cfg.AstMatrix.FifoMax,",
    "\t\t}",
    "\t\tamCfg.Providers = make(",
    "\t\tfor name, pcfg := range cfg.AstMatrix.Providers {",
    "\t\t\tamCfg.Providers[name] = astmatrix.ProviderCfg{",
    "\t\t\t\tBaseURL:  pcfg.BaseURL,",
    "\t\t\t\tKeyEnv:   pcfg.KeyEnv,",
    "\t\t\t\tKeyEnvAlt: pcfg.KeyEnvAlt,",
    "\t\t\t\tNoAuth:   pcfg.NoAuth,",
    "\t\t\t}",
    "\t\t}",
    "\t\tcloud, err = astmatrix.NewRouter(amCfg, proxylog)",
    "\t\tif err != nil {",
    '\t\t\treturn nil, fmt.Errorf("creating astmatrix router: %w", err)',
    "\t\t}",
    '\t\tproxylog.Infof("astmatrix cloud router enabled: strategy=%s providers=%d", cfg.AstMatrix.Strategy, len(cloud.Matrix().Providers()))',
    "\t}",
]
for L in lines:
    print(L in s, repr(L[:50]))
