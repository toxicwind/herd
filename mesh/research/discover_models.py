#!/usr/bin/env python3
"""
Dynamic model discovery for Sovereign AST Matrix
Queries each provider's /models endpoint and builds the CODING dict.
"""

import json, os, time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

for path in (os.path.expanduser("~/.secrets"), "/home/toxic/.secrets"):
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"): continue
                if line.startswith("export "): line = line[7:]
                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k and v: os.environ.setdefault(k, v)
    except FileNotFoundError:
        pass

def fetch(base, key, extra=None):
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra: h.update(extra)
    try:
        return json.load(urlopen(Request(base.rstrip("/") + "/models", headers=h), timeout=15))
    except HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}"}
    except Exception as e:
        return {"error": str(e)}

print("Discovering...")
results = {}
if os.getenv("NVIDIA_API_KEY"):
    results["nvidia"] = fetch("https://integrate.api.nvidia.com/v1", os.getenv("NVIDIA_API_KEY")); time.sleep(0.5)
if os.getenv("OPENROUTER_API_KEY"):
    results["openrouter"] = fetch("https://openrouter.ai/api/v1", os.getenv("OPENROUTER_API_KEY"),
        {"HTTP-Referer": "https://zed.dev", "X-Title": "Sovereign-Discovery"}); time.sleep(0.5)
if os.getenv("GOOGLE_API_KEY"):
    results["google"] = fetch("https://generativelanguage.googleapis.com/v1beta/openai", os.getenv("GOOGLE_API_KEY")); time.sleep(0.5)
if os.getenv("MISTRAL_API_KEY"):
    results["mistral"] = fetch("https://api.mistral.ai/v1", os.getenv("MISTRAL_API_KEY")); time.sleep(0.5)
if os.getenv("GROQ_API_KEY"):
    results["groq"] = fetch("https://api.groq.com/openai/v1", os.getenv("GROQ_API_KEY")); time.sleep(0.5)
if os.getenv("CEREBRAS_API_KEY"):
    results["cerebras"] = fetch("https://api.cerebras.ai/v1", os.getenv("CEREBRAS_API_KEY")); time.sleep(0.5)

with open("/home/toxic/sovereign/tools/ast-matrix/models_discovered.json", "w") as f:
    json.dump(results, f, indent=2)
print("Saved models_discovered.json")

# Build CODING
coding = {"auto": None, "fcm": None}

# NVIDIA
nvidia_map = {
    "nvidia/nemotron-3-super-120b-a12b": "nim-nemotron-super",
    "nvidia/nemotron-3-nano-30b-a3b": "nim-nemotron-nano",
    "nvidia/llama-3.1-nemotron-nano-8b-v1": "nim-nemotron-nano",
    "meta/llama-3.1-70b-instruct": "nim-llama-3.1-70b",
    "meta/llama-3.3-70b-instruct": "nim-llama-3.3-70b",
    "qwen/qwen3.5-397b-a17b": "nim-qwen3.5-397b",
    "qwen/qwen3.5-122b-a10b": "nim-qwen3.5-122b",
    "deepseek-ai/deepseek-v4-flash": "nim-deepseek-v4-flash",
    "deepseek-ai/deepseek-v4-pro": "nim-deepseek-v4-pro",
    "mistralai/mistral-large-3-675b-instruct-2512": "nim-mistral-large-3",
    "google/gemma-4-31b-it": "nim-gemma4-31b",
    "z-ai/glm-5.2": "nim-glm5.2",
    "thinkingmachines/inkling": "nim-inkling",
}
for mid, alias in nvidia_map.items():
    coding[alias] = ("nvidia", mid)

# OpenRouter free
or_free = {
    "tencent/hy3:free": "hy3",
    "poolside/laguna-xs-2.1:free": "laguna-xs",
    "poolside/laguna-m.1:free": "laguna-m1",
    "google/gemma-4-31b-it:free": "gemma4-31b",
    "nvidia/nemotron-3-super-120b-a12b:free": "nemotron-super",
    "nvidia/nemotron-3-nano-30b-a3b:free": "nemotron-nano",
    "qwen/qwen3-coder:free": "qwen3-coder",
    "meta-llama/llama-3.3-70b-instruct:free": "llama-3.3-70b-free",
    "nousresearch/hermes-3-llama-3.1-405b:free": "hermes-3-405b",
    "openai/gpt-oss-20b:free": "gpt-oss-20b",
}
for mid, alias in or_free.items():
    coding[alias] = ("openrouter", mid)

# Google
for mid, alias in {"models/gemini-2.5-flash": "gemini-2.5-flash",
                   "models/gemini-2.5-flash-lite": "gemini-2.5-flash-lite",
                   "models/gemini-2.0-flash": "gemini-2.0-flash",
                   "models/gemma-4-31b-it": "gemma4-31b"}.items():
    coding[alias] = ("google", mid)

# Mistral
for mid, alias in {"mistral-small-latest": "mistral-small",
                   "codestral-latest": "codestral",
                   "mistral-large-latest": "mistral-large",
                   "mistral-medium-latest": "mistral-medium"}.items():
    coding[alias] = ("mistral", mid)

with open("/home/toxic/sovereign/tools/ast-matrix/coding_generated.json", "w") as f:
    json.dump(coding, f, indent=2)
print("Saved coding_generated.json")
print(f"Total aliases: {len([k for k in coding if coding[k]])}")
