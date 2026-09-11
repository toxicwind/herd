SOVEREIGN AST MATRIX + FULL ARTIFACTS — July 16 2026 (NVIDIA NIM complete)
==========================================================================

Primary:
  sovereign-ast-matrix/
    router.py              — 5-strategy OpenAI-compatible gateway + full NVIDIA NIM
    zed_settings.json      — Zed settings (includes all nim-* models)
    README.md
    lib/

NVIDIA NIM:
  - Base: https://integrate.api.nvidia.com/v1
  - Key: export NVIDIA_API_KEY=nvapi-... (from build.nvidia.com)
  - Models: nim-nemotron-*, nim-llama-*, nim-qwen*-coder, nim-deepseek-*, etc.

Usage:
  python3 sovereign-ast-matrix/router.py
  Merge zed_settings.json into Zed settings → select openai / auto or any nim-* model
