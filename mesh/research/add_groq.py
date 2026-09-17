#!/usr/bin/env python3
"""Add Groq models to sovereign-ast-matrix router."""
import re

ROUTER = "/home/toxic/sovereign/tools/ast-matrix/sovereign-ast-matrix/router.py"

with open(ROUTER) as f:
    src = f.read()

# Fix 1: Add Groq models to PROVIDER_MODELS
OLD_GROQ_MODELS = '''    "groq": [
        # all 403 - key issue
    ],'''

NEW_GROQ_MODELS = '''    "groq": [
        "llama-3.3-70b-versatile",
        "qwen/qwen3-32b",
        "qwen/qwen3.6-27b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "meta-llama/llama-4-scout-17b-16e-instruct",
    ],'''

# Fix 2: Add Groq aliases to CODING
OLD_GROQ_COMMENT = '''    # Groq (key was 403, retesting)'''

NEW_GROQ_ENTRIES = '''    # Groq (fast inference, free tier)
    "groq-llama-3.3-70b": ("groq", "llama-3.3-70b-versatile"),
    "groq-qwen3-32b": ("groq", "qwen/qwen3-32b"),
    "groq-qwen3.6-27b": ("groq", "qwen/qwen3.6-27b"),
    "groq-gpt-oss-120b": ("groq", "openai/gpt-oss-120b"),
    "groq-gpt-oss-20b": ("groq", "openai/gpt-oss-20b"),
    "groq-llama-4-scout": ("groq", "meta-llama/llama-4-scout-17b-16e-instruct"),'''

count = 0
if OLD_GROQ_MODELS in src:
    src = src.replace(OLD_GROQ_MODELS, NEW_GROQ_MODELS, 1)
    count += 1
    print("OK: updated PROVIDER_MODELS groq")
else:
    print("WARN: groq PROVIDER_MODELS not found")

if OLD_GROQ_COMMENT in src:
    src = src.replace(OLD_GROQ_COMMENT, NEW_GROQ_ENTRIES, 1)
    count += 1
    print("OK: added CODING groq aliases")
else:
    # Try to find where to insert — after last mistral entry
    mistral_end = '''    "mistral-medium": ("mistral", "mistral-medium-latest"),
}'''
    if mistral_end in src:
        insert = mistral_end.replace(
            "}",
            NEW_GROQ_ENTRIES + "\n}"
        )
        src = src.replace(mistral_end, insert, 1)
        count += 1
        print("OK: added CODING groq aliases (after mistral)")
    else:
        print("WARN: could not find insertion point for CODING aliases")

if count > 0:
    with open(ROUTER, "w") as f:
        f.write(src)
    print(f"\nPatched {count} section(s)")
else:
    print("\nNo patches applied")
