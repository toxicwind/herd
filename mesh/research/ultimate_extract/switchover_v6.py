#!/usr/bin/env python3
"""
Live Switchover V6 - Environment-aware kernel/agent server migration
=====================================================================
Auto-detects: Kubernetes, s6, systemd, Docker, bare metal
Uses the correct approach for each environment.

Usage:
    python3 switchover_v6.py
    DRY_RUN=1 python3 switchover_v6.py
    FORCE_APPROACH=ipython python3 switchover_v6.py
"""

import os
import sys
import time
import json
import signal
import subprocess
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# ============================================================
# CONFIGURATION
# ============================================================
def _get_env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default)).expanduser().resolve()

AGENTS_ROOT: Path = _get_env_path("AGENTS_ROOT", "/mnt/agents")
OUTPUT_DIR: Path = _get_env_path("OUTPUT_DIR", str(AGENTS_ROOT / "output"))
API_BASE: str = os.environ.get("API_BASE", "http://localhost:8888").rstrip("/")
NEW_API_BASE: str = os.environ.get("NEW_API_BASE", "http://localhost:8889").rstrip("/")
KERNEL_SERVER_PATH: Path = _get_env_path("KERNEL_SERVER_PATH", "/app/kernel_server.py")
LOG_DIR: Path = _get_env_path("LOG_DIR", str(OUTPUT_DIR))
S6_SERVICE_PATH: Path = _get_env_path("S6_SERVICE_PATH", "/run/service/kernel-server")
DEFAULT_TIMEOUT: int = int(os.environ.get("DEFAULT_TIMEOUT", "30"))
DRY_RUN: bool = os.environ.get("DRY_RUN", "0").lower() in ("1", "true", "yes", "on")
FORCE_APPROACH: Optional[str] = os.environ.get("FORCE_APPROACH", None)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

SCRIPT_VERSION = "6.0.0-k8s"

def run(
    cmd: Union[str, List[str]],
    timeout: Optional[int] = None,
    cwd: Union[str, Path] = "/",
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    if timeout is None:
        timeout = DEFAULT_TIMEOUT
    if isinstance(cmd, str):
        cmd_list = cmd.split()
    else:
        cmd_list = list(cmd)
    result: Dict[str, Any] = {
        "meta": {"cmd": cmd_list, "cwd": str(cwd), "timeout": timeout, "ts": time.time()},
        "stdout": "", "stderr": "", "rc": None, "ok": False, "exc": None, "timed_out": False,
    }
    try:
        proc_env = os.environ.copy()
        if env:
            proc_env.update(env)
        proc_env["LC_ALL"] = "C"
        proc = subprocess.run(cmd_list, capture_output=True, text=True, env=proc_env, timeout=timeout, cwd=str(cwd), shell=False)
        result["stdout"] = proc.stdout
        result["stderr"] = proc.stderr
        result["rc"] = proc.returncode
        result["ok"] = proc.returncode == 0
    except subprocess.TimeoutExpired as e:
        result["timed_out"] = True
        result["exc"] = f"Timeout after {timeout}s"
        if e.stdout: result["stdout"] = e.stdout.decode(errors="replace")
        if e.stderr: result["stderr"] = e.stderr.decode(errors="replace")
    except Exception as e:
        result["exc"] = str(e)
    return result

def api_get(endpoint: str, timeout: int = 5) -> Dict[str, Any]:
    url = f"{API_BASE}{endpoint}"
    r = run(["curl", "-s", "-m", str(timeout), url], timeout=timeout + 2)
    if r["ok"]:
        try:
            return json.loads(r["stdout"])
        except Exception:
            return {"raw": r["stdout"], "ok": True, "parsed": False}
    return {"ok": False, "err": r["stderr"], "exc": r["exc"], "url": url}

def api_post(endpoint: str, timeout: int = 10) -> Dict[str, Any]:
    url = f"{API_BASE}{endpoint}"
    r = run(["curl", "-s", "-m", str(timeout), "-X", "POST", url], timeout=timeout + 2)
    if r["ok"]:
        try:
            return json.loads(r["stdout"])
        except Exception:
            return {"raw": r["stdout"], "ok": True, "parsed": False}
    return {"ok": False, "err": r["stderr"], "exc": r["exc"], "url": url}

def log(msg: str, level: str = "INFO") -> None:
    ts = time.strftime("%H:%M:%S")
    line = f"[{level}] {ts} | {msg}"
    print(line, flush=True)
    try:
        with open(LOG_DIR / "switchover_v6.log", "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

def find_kernel_pid(port: str = "8888") -> Optional[int]:
    r = run(["ps", "aux"])
    if not r["ok"]:
        return None
    for line in r["stdout"].splitlines():
        if "kernel_server.py" in line and port in line:
            parts = line.split()
            if len(parts) > 1 and parts[1].isdigit():
                return int(parts[1])
    return None

def detect_environment() -> Tuple[str, Dict[str, Any]]:
    """Detect runtime environment and return (env_type, details)."""
    details: Dict[str, Any] = {}
    
    # Kubernetes detection via cgroup or env vars
    try:
        with open("/proc/self/cgroup") as f:
            cgroup = f.read()
        if "kubepods" in cgroup or "kubernetes" in cgroup:
            details["cgroup"] = "kubepods"
    except Exception:
        pass
    
    k8s_env = [k for k in os.environ if "KUBERNETES" in k]
    if k8s_env:
        details["k8s_env_vars"] = k8s_env
    
    if "kubepods" in details.get("cgroup", "") or k8s_env:
        return "k8s", details
    
    # s6 detection
    s6_test = run(["which", "s6-svc"], timeout=5)
    if s6_test["ok"] and s6_test["stdout"].strip():
        details["s6_svc_path"] = s6_test["stdout"].strip()
        if S6_SERVICE_PATH.exists():
            svstat = run(["s6-svstat", str(S6_SERVICE_PATH)], timeout=5)
            if svstat["ok"]:
                details["s6_perms"] = True
                return "s6", details
            else:
                details["s6_perms"] = False
    
    # systemd detection
    systemd_test = run(["systemctl", "is-system-running"], timeout=5)
    if systemd_test["ok"]:
        return "systemd", details
    
    # Docker detection
    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        return "docker", details
    
    return "bare", details

