#!/usr/bin/env python3
"""
Sovereign AST Matrix — Provider Health Checker
Tests every provider + model with a tiny prompt, respecting rate limits.
Reports: OK / FAIL / SLOW / RATE-LIMITED with latency and error details.

Usage:
    python3 check_providers.py              # check all
    python3 check_providers.py --provider nvidia  # check one provider
    python3 check_providers.py --quick      # skip slow/large models
"""

import json
import os
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


# ── Load secrets ──
def _load_secrets():
    for path in (os.path.expanduser("~/.secrets"), "/home/toxic/.secrets"):
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("export "):
                        line = line[7:]
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip("'\"")
                        if k and v:
                            os.environ.setdefault(k, v)
        except FileNotFoundError:
            pass


_load_secrets()

# ── Providers and their test models ──
# Each entry: (provider_key, model_id, context_hint, is_free)
# We test with a tiny prompt and low max_tokens to minimize credit burn

PROVIDERS = {
    "openrouter": {
        "base": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "models": [
            ("tencent/hy3:free", 262144, True),
            ("qwen/qwen3-coder:free", 262144, True),
            ("nvidia/nemotron-3-super-120b-a12b:free", 262144, True),
            ("google/gemma-4-31b-it:free", 131072, True),
            ("nousresearch/hermes-3-llama-3.1-405b:free", 131072, True),
            ("openai/gpt-oss-20b:free", 131072, True),
        ],
    },
    "nvidia": {
        "base": "https://integrate.api.nvidia.com/v1",
        "key_env": "NVIDIA_API_KEY",
        "models": [
            ("nvidia/nemotron-3-super-120b-a12b", 262144, False),
            ("nvidia/nemotron-3-nano-30b-a3b", 131072, False),
            ("nvidia/llama-3.3-nemotron-super-49b-v1.5", 131072, False),
            ("nvidia/llama-3.1-nemotron-ultra-253b-v1", 131072, False),
            ("thinkingmachines/inkling", 131072, False),
            ("meta/llama-3.3-70b-instruct", 131072, False),
            ("qwen/qwen3.5-397b-a17b", 262144, False),
            ("deepseek-ai/deepseek-v4-pro", 131072, False),
            ("mistralai/mistral-large-3-675b-instruct-2512", 131072, False),
            ("google/gemma-4-31b-it", 131072, False),
        ],
    },
    "groq": {
        "base": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "models": [
            ("llama-3.3-70b-versatile", 131072, True),
            ("llama-3.1-8b-instant", 131072, True),
            ("qwen/qwen3-32b", 131072, True),
            ("openai/gpt-oss-120b", 131072, True),
            ("meta-llama/llama-4-scout-17b-16e-instruct", 131072, True),
            ("moonshotai/kimi-k2-instruct", 131072, True),
        ],
    },
    "cerebras": {
        "base": "https://api.cerebras.ai/v1",
        "key_env": "CEREBRAS_API_KEY",
        "models": [
            ("llama3.1-8b", 8192, True),  # default ctx = 8192!
            ("llama3.1-70b", 8192, True),  # same
            ("qwen-3-235b-a22b-instruct-2507", 65536, True),
            ("gpt-oss-120b", 128000, True),
        ],
    },
    "google": {
        "base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_env": "GOOGLE_API_KEY",
        "models": [
            ("gemini-2.5-flash", 1048576, True),
            ("gemini-2.5-flash-lite", 1048576, True),
            ("gemini-2.0-flash", 1048576, True),
            ("gemma-3-27b-it", 131072, True),
        ],
    },
    "mistral": {
        "base": "https://api.mistral.ai/v1",
        "key_env": "MISTRAL_API_KEY",
        "models": [
            ("mistral-small-latest", 128000, True),
            ("codestral-latest", 256000, True),
            ("mistral-large-latest", 128000, True),
        ],
    },
}

PROMPT = "Say exactly: OK"
MAX_TOKENS = 16
TIMEOUT = 20  # seconds


def test_model(
    provider_key: str, provider: dict, model_id: str, ctx: int, is_free: bool
) -> dict:
    """Test a single model. Returns result dict."""
    key = os.getenv(provider["key_env"], "")
    if not key:
        return {
            "status": "NO_KEY",
            "latency": 0,
            "error": f"missing {provider['key_env']}",
            "free": is_free,
            "ctx": ctx,
        }

    base = provider["base"]
    url = base.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }
    if provider_key == "openrouter":
        headers["HTTP-Referer"] = "https://zed.dev"
        headers["X-Title"] = "Sovereign-Checker"

    body = json.dumps(
        {
            "model": model_id,
            "messages": [{"role": "user", "content": PROMPT}],
            "max_tokens": MAX_TOKENS,
            "temperature": 0,
        }
    ).encode()

    start = time.time()
    try:
        req = Request(url, data=body, headers=headers, method="POST")
        resp = urlopen(req, timeout=TIMEOUT)
        latency = time.time() - start
        raw = resp.read()
        data = json.loads(raw)

        # Extract content
        choices = data.get("choices", [])
        content = ""
        if choices:
            content = choices[0].get("message", {}).get("content", "")[:80]

        # Extract usage
        usage = data.get("usage", {})
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)

        # Determine status
        if latency > 15:
            status = "SLOW"
        elif content:
            status = "OK"
        else:
            status = "EMPTY"

        return {
            "status": status,
            "latency": round(latency, 2),
            "content": content.strip(),
            "tokens": f"{in_tok}→{out_tok}",
            "free": is_free,
            "ctx": ctx,
            "error": "",
        }

    except HTTPError as e:
        latency = time.time() - start
        body_text = ""
        try:
            body_text = e.read()[:200].decode("utf-8", errors="replace")
        except Exception:
            pass

        if e.code == 429:
            status = "RATE_LIMIT"
        elif e.code == 404:
            status = "NOT_FOUND"
        elif e.code == 401:
            status = "AUTH_FAIL"
        elif e.code == 402:
            status = "NO_CREDITS"
        else:
            status = f"HTTP_{e.code}"

        return {
            "status": status,
            "latency": round(latency, 2),
            "content": "",
            "tokens": "",
            "free": is_free,
            "ctx": ctx,
            "error": body_text[:150],
        }

    except Exception as e:
        latency = time.time() - start
        err = str(e)[:150]
        if "timed out" in err.lower() or "timeout" in err.lower():
            status = "TIMEOUT"
        elif "connection" in err.lower():
            status = "CONN_ERR"
        else:
            status = "ERROR"
        return {
            "status": status,
            "latency": round(latency, 2),
            "content": "",
            "tokens": "",
            "free": is_free,
            "ctx": ctx,
            "error": err,
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Check all AST Matrix providers")
    parser.add_argument("--provider", "-p", help="Check only this provider")
    parser.add_argument(
        "--quick", "-q", action="store_true", help="Skip large/slow models"
    )
    parser.add_argument(
        "--delay",
        "-d",
        type=float,
        default=1.5,
        help="Delay between requests (seconds)",
    )
    args = parser.parse_args()

    providers_to_check = PROVIDERS
    if args.provider:
        if args.provider not in PROVIDERS:
            print(
                f"Unknown provider: {args.provider}. Available: {', '.join(PROVIDERS.keys())}"
            )
            sys.exit(1)
        providers_to_check = {args.provider: PROVIDERS[args.provider]}

    print("=" * 72)
    print("  Sovereign AST Matrix — Provider Health Check")
    print(f"  Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Prompt: {PROMPT!r} | Max tokens: {MAX_TOKENS} | Timeout: {TIMEOUT}s")
    print("=" * 72)

    results = {}
    totals = {"ok": 0, "fail": 0, "skip": 0}

    for pkey, pconf in providers_to_check.items():
        key = os.getenv(pconf["key_env"], "")
        print(f"\n{'─' * 72}")
        print(f"  {pkey.upper()} (key: {'✓' if key else '✗ missing'})")
        print(f"{'─' * 72}")

        if not key:
            print(f"  ⚠  No key ({pconf['key_env']}) — skipping all models")
            totals["skip"] += len(pconf["models"])
            continue

        for model_id, ctx, is_free in pconf["models"]:
            # Quick mode: skip models with >100B params or huge context (slow to respond)
            if args.quick and (
                "480b" in model_id or "397b" in model_id or "ultra-253b" in model_id
            ):
                print(f"  ⏭  {model_id[:45]:<45} SKIP (quick mode)")
                totals["skip"] += 1
                continue

            result = test_model(pkey, pconf, model_id, ctx, is_free)
            results[f"{pkey}/{model_id}"] = result

            # Format output
            status = result["status"]
            lat = result["latency"]
            free_tag = "FREE" if is_free else "paid"
            ctx_k = f"{ctx // 1024}K" if ctx >= 1024 else str(ctx)

            icon = {"OK": "✅", "EMPTY": "⚠️ ", "SLOW": "🐌"}.get(status, "❌")
            if status in ("RATE_LIMIT",):
                icon = "🚦"
            elif status in ("NOT_FOUND",):
                icon = "🔍"
            elif status in ("TIMEOUT",):
                icon = "⏰"

            line = f"  {icon} {model_id[:45]:<45} {status:<12} {lat:>5.1f}s  ctx={ctx_k:<6} [{free_tag}]"
            if result.get("tokens"):
                line += f"  tok={result['tokens']}"
            if result.get("content"):
                line += f'  "{result["content"][:40]}"'
            if result.get("error"):
                line += f'  err="{result["error"][:60]}"'
            print(line)

            if status in ("OK", "EMPTY", "SLOW"):
                totals["ok"] += 1
            else:
                totals["fail"] += 1

            # Rate limit respect: delay between requests
            time.sleep(args.delay)

    # Summary
    print(f"\n{'=' * 72}")
    print(
        f"  SUMMARY: {totals['ok']} OK | {totals['fail']} FAIL | {totals['skip']} SKIP"
    )
    print(f"{'=' * 72}")

    # Save results
    out_path = os.path.join(os.path.dirname(__file__), "check_results.json")
    with open(out_path, "w") as f:
        json.dump(
            {
                "timestamp": time.time(),
                "results": results,
                "totals": totals,
            },
            f,
            indent=2,
        )
    print(f"  Results saved to: {out_path}")

    # Return exit code
    sys.exit(1 if totals["fail"] > 0 else 0)


if __name__ == "__main__":
    main()
