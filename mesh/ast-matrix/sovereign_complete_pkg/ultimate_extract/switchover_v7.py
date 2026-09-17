#!/usr/bin/env python3
"""
Live Switchover V7 - Environment-aware with CDP fallback
=========================================================
Auto-detects: Kubernetes, s6, systemd, Docker, bare metal
Uses CDP (Chrome DevTools Protocol) as secondary execution channel.

LESSONS LEARNED FROM V5/V6 BREAKAGE:
- NEVER kill supervised processes expecting auto-restart
- s6 permissions must be verified BEFORE use
- IPython reload is the SAFEST approach
- CDP provides a secondary channel when ipython is down
- Always verify health between approaches

Usage:
    python3 switchover_v7.py
    DRY_RUN=1 python3 switchover_v7.py
    FORCE_APPROACH=ipython python3 switchover_v7.py
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
CDP_URL: str = os.environ.get("CDP_URL", "http://localhost:9222")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

SCRIPT_VERSION = "7.0.0-cdp"

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
        with open(LOG_DIR / "switchover_v7.log", "a") as f:
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
    
    systemd_test = run(["systemctl", "is-system-running"], timeout=5)
    if systemd_test["ok"]:
        return "systemd", details
    
    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        return "docker", details
    
    return "bare", details

def check_cdp_available() -> bool:
    """Check if Chrome DevTools Protocol is available."""
    r = run(["curl", "-s", "-m", "2", f"{CDP_URL}/json/version"], timeout=5)
    return r["ok"] and "Browser" in r["stdout"]

# ============================================================
# APPROACH 0: IPython Kernel Reload (PRIMARY FALLBACK)
# ============================================================
def approach_0_ipython_reload() -> bool:
    """Use IPython to reload modules without restarting the server."""
    log("=== APPROACH 0: IPython Kernel Reload ===")
    
    r = run(["ls", "/tmp/"], timeout=5)
    if not r["ok"]:
        log("Cannot list /tmp", "WARN")
        return False
    
    conn_files = [l for l in r["stdout"].splitlines() if l.startswith("tmp") and l.endswith(".json")]
    if not conn_files:
        log("No IPython connection files found", "WARN")
        return False
    
    conn_file = "/tmp/" + conn_files[0]
    log(f"Using connection file: {conn_file}")
    
    try:
        with open(conn_file) as f:
            conn_data = json.load(f)
        log(f"Connection file keys: {list(conn_data.keys())}")
    except Exception as e:
        log(f"Cannot read connection file: {e}", "WARN")
        return False
    
    if DRY_RUN:
        log("DRY_RUN: Skipping IPython reload execution")
        return False
    
    script_lines = []
    script_lines.append("import sys")
    script_lines.append("import time")
    script_lines.append("try:")
    script_lines.append("    from jupyter_client import KernelManager")
    script_lines.append("except ImportError:")
    script_lines.append('    print("jupyter_client not available")')
    script_lines.append("    sys.exit(1)")
    script_lines.append("")
    script_lines.append(f'conn_file = "{conn_file}"')
    script_lines.append("km = KernelManager(connection_file=conn_file)")
    script_lines.append("km.load_connection_file()")
    script_lines.append("kc = km.client()")
    script_lines.append("kc.start_channels()")
    script_lines.append("")
    script_lines.append("# Execute a deep reload")
    script_lines.append('kc.execute("""')
    script_lines.append("import importlib")
    script_lines.append("import sys")
    script_lines.append("import types")
    script_lines.append("")
    script_lines.append("reloaded = []")
    script_lines.append("for name in list(sys.modules.keys()):")
    script_lines.append("    mod = sys.modules[name]")
    script_lines.append("    if isinstance(mod, types.ModuleType) and hasattr(mod, '__file__') and mod.__file__:")
    script_lines.append("        if '/app/' in mod.__file__ or '/mnt/agents/' in mod.__file__:")
    script_lines.append("            try:")
    script_lines.append("                importlib.reload(mod)")
    script_lines.append("                reloaded.append(name)")
    script_lines.append("            except Exception:")
    script_lines.append("                pass")
    script_lines.append("")
    script_lines.append('print(f"Reloaded {len(reloaded)} modules")')
    script_lines.append('""")')
    script_lines.append("")
    script_lines.append("time.sleep(2)")
    script_lines.append("kc.stop_channels()")
    script_lines.append('print("SUCCESS")')
    
    reload_script = "\n".join(script_lines)
    
    script_path = OUTPUT_DIR / "ipython_reload.py"
    with open(script_path, "w") as f:
        f.write(reload_script)
    
    r = run(["python3", str(script_path)], timeout=30)
    log(f"IPython reload result: ok={r['ok']} rc={r['rc']}")
    log(f"IPython stdout: {r['stdout'][:200]}")
    if r['stderr']:\
        log(f"IPython stderr: {r['stderr'][:200]}")
    
    time.sleep(2)
    health = api_get("/health")
    if health.get("kernel_alive"):
        log("APPROACH 0 SUCCESS (IPython reload)", "SUCCESS")
        return True
    
    log("APPROACH 0 FAILED", "WARN")
    return False

# ============================================================
# APPROACH 4: s6 Service Restart (with proper permission check)
# ============================================================
def approach_4_s6_restart() -> bool:
    """Use s6 supervision to restart the service."""
    log("=== APPROACH 4: s6 Service Restart ===")

    which_r = run(["which", "s6-svc"])
    has_s6 = which_r["ok"] and which_r["stdout"].strip()

    if not has_s6:
        log("s6-svc not found in PATH", "WARN")
        return False

    if not S6_SERVICE_PATH.exists():
        log(f"s6 service dir not found: {S6_SERVICE_PATH}", "WARN")
        return False

    # CRITICAL: Test permission FIRST
    test_r = run(["s6-svstat", str(S6_SERVICE_PATH)], timeout=5)
    if not test_r["ok"]:
        log(f"s6 permission test failed: {test_r['stderr'][:200]}", "WARN")
        return False
    log(f"s6-svstat: {test_r['stdout'].strip()}")

    if DRY_RUN:
        log("DRY_RUN: Skipping s6-svc stop/start")
        return False

    health_before = api_get("/health", timeout=3)
    log(f"Health before stop: {json.dumps(health_before)[:120]}")

    log(f"Stopping service {S6_SERVICE_PATH} ...")
    stop_r = run(["s6-svc", "-d", str(S6_SERVICE_PATH)], timeout=15)
    log(f"s6-svc -d: rc={stop_r['rc']} stderr={stop_r['stderr'][:150]}")
    
    if stop_r["rc"] != 0:
        log("s6 stop failed, aborting approach", "ERROR")
        return False
    
    time.sleep(2.5)

    down_check = api_get("/health", timeout=2)
    if down_check.get("kernel_alive"):
        log("Service still alive after stop, aborting", "WARN")
        return False
    log("Service confirmed down")

    log(f"Starting service {S6_SERVICE_PATH} ...")
    start_r = run(["s6-svc", "-u", str(S6_SERVICE_PATH)], timeout=15)
    log(f"s6-svc -u: rc={start_r['rc']} stderr={start_r['stderr'][:150]}")
    
    if start_r["rc"] != 0:
        log("s6 start failed, aborting approach", "ERROR")
        return False

    for i in range(35):
        h = api_get("/health", timeout=4)
        if h.get("kernel_alive"):
            log(f"Service back and healthy after {i+1}s")
            log("APPROACH 4 SUCCESS", "SUCCESS")
            return True
        time.sleep(1)

    log("APPROACH 4 FAILED - service did not recover in time", "ERROR")
    return False

# ============================================================
# APPROACH 1: File Patch + /reload
# ============================================================
def approach_1_file_patch_reload() -> bool:
    log("=== APPROACH 1: File Patch + API /reload ===")
    health = api_get("/health")
    log(f"Initial health: {json.dumps(health)[:180]}")
    grep_r = run(["grep", "-q", '@app.post("/reload")', str(KERNEL_SERVER_PATH)], timeout=10)
    has_reload = grep_r["ok"]
    log(f"Has /reload endpoint: {has_reload}")
    if not has_reload:
        log("Adding /reload endpoint to kernel_server.py ...")
        read_r = run(["cat", str(KERNEL_SERVER_PATH)], timeout=15)
        if not read_r["ok"]:
            log(f"Failed to read kernel_server.py: {read_r['stderr'][:200]}", "ERROR")
            return False
        content = read_r["stdout"]
        reload_code = (
            '\n@app.post("/reload")\n'
            "async def reload_modules():\n"
            "    import importlib\n"
            "    import sys\n"
            "    import time as _t\n"
            "    try:\n"
            "        if 'jupyter_kernel' in sys.modules:\n"
            "            importlib.reload(sys.modules['jupyter_kernel'])\n"
            "        return {'success': True, 'message': 'reloaded', 'ts': _t.time()}\n"
            "    except Exception as e:\n"
            "        return {'success': False, 'error': str(e)}\n\n"
        )
        target = '@app.get("/kernel/debug")'
        if target in content:
            content = content.replace(target, reload_code + target)
        else:
            content = reload_code + content
        if DRY_RUN:
            log("DRY_RUN: Skipping write of patched kernel_server.py")
        else:
            write_cmd = ["python3", "-c", f"with open('{KERNEL_SERVER_PATH}', 'w') as f: f.write({repr(content)})"]
            write_r = run(write_cmd, timeout=15)
            log(f"Write result: ok={write_r['ok']} rc={write_r['rc']}")
            if not write_r["ok"]:
                log(f"Write stderr: {write_r['stderr'][:300]}", "ERROR")
                return False
    log("Calling /reload ...")
    reload_resp = api_post("/reload", timeout=15)
    log(f"/reload response: {json.dumps(reload_resp)[:250]}")
    if reload_resp.get("success"):
        log("APPROACH 1 SUCCESS", "SUCCESS")
        return True
    log("APPROACH 1 FAILED", "WARN")
    return False

# ============================================================
# APPROACH 2: Kernel Reset
# ============================================================
def approach_2_kernel_reset() -> bool:
    log("=== APPROACH 2: Kernel Reset via marker + /kernel/reset ===")
    marker = f"# SW2_PATCH_{int(time.time())}"
    patch_code = (
        f"m = {repr(marker)}; "
        f"with open('{KERNEL_SERVER_PATH}') as f: c = f.read(); "
        f"(print('ALREADY_PATCHED') if m in c else "
        f"(open('{KERNEL_SERVER_PATH}', 'w').write(m + '\n"
        f"import time as _t2\n_SW2_TS = _t2.time()\n' + c), print('PATCHED')))"
    )
    if DRY_RUN:
        log("DRY_RUN: Skipping patch of jupyter_kernel.py")
    else:
        patch_r = run(["python3", "-c", patch_code], timeout=15, cwd="/app")
        log(f"Patch result: {patch_r['stdout'].strip()} rc={patch_r['rc']}")
    log("Calling /kernel/reset ...")
    reset_resp = api_post("/kernel/reset", timeout=20)
    log(f"Reset response: {json.dumps(reset_resp)[:250]}")
    time.sleep(2)
    health = api_get("/health")
    log(f"Post-reset health: {json.dumps(health)[:200]}")
    if health.get("kernel_alive"):
        log("APPROACH 2 SUCCESS", "SUCCESS")
        return True
    log("APPROACH 2 FAILED", "WARN")
    return False

# ============================================================
# APPROACH 3: Spawn + Socat Port Flip
# ============================================================
def approach_3_spawn_socat_flip() -> bool:
    log("=== APPROACH 3: Spawn on new port + socat port flip ===")
    if DRY_RUN:
        log("DRY_RUN: Skipping dangerous spawn/kill/socat operations")
        return False
    old_pid = find_kernel_pid("8888")
    log(f"Old kernel PID on 8888: {old_pid}")
    new_log = LOG_DIR / "new_server_8889.log"
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    log(f"Spawning new server on {NEW_API_BASE} ...")
    try:
        with open(new_log, "w") as logf:
            proc = subprocess.Popen(
                ["python3", str(KERNEL_SERVER_PATH), "--host", "0.0.0.0", "--port", "8889", "--log-level", "info"],
                cwd="/app", env=env, stdout=logf, stderr=subprocess.STDOUT, start_new_session=True,
            )
        new_pid = proc.pid
        log(f"New server PID: {new_pid}")
    except Exception as e:
        log(f"Failed to spawn new server: {e}", "ERROR")
        return False
    healthy = False
    for i in range(25):
        r = run(["curl", "-s", "-m", "3", f"{NEW_API_BASE}/health"], timeout=6)
        if r["ok"] and "kernel_alive" in r["stdout"]:
            log(f"New server healthy after {i+1}s")
            healthy = True
            break
        time.sleep(1)
    if not healthy:
        log("New server did not become healthy, aborting", "ERROR")
        try:
            os.kill(new_pid, signal.SIGKILL)
        except Exception:
            pass
        return False
    log("Starting temporary socat forwarder 8888 -> 8889 ...")
    try:
        socat_proc = subprocess.Popen(
            ["socat", "TCP-LISTEN:8888,reuseaddr,fork", "TCP:localhost:8889"],
            start_new_session=True,
        )
        log(f"Socat PID: {socat_proc.pid}")
    except Exception as e:
        log(f"socat failed: {e}", "ERROR")
        return False
    time.sleep(1.5)
    fwd_test = run(["curl", "-s", "-m", "4", f"{API_BASE}/health"], timeout=8)
    log(f"Forward test via 8888: ok={fwd_test['ok']} out={fwd_test['stdout'][:120]}")
    if old_pid:
        log(f"Terminating old PID {old_pid} ...")
        try:
            os.kill(old_pid, signal.SIGTERM)
            time.sleep(3)
            try:
                os.kill(old_pid, 0)
                os.kill(old_pid, signal.SIGKILL)
                log("Old process SIGKILLed")
            except ProcessLookupError:
                log("Old process terminated cleanly")
        except Exception as e:
            log(f"Kill error: {e}", "WARN")
    try:
        os.kill(socat_proc.pid, signal.SIGTERM)
    except Exception:
        pass
    time.sleep(1)
    try:
        os.kill(new_pid, signal.SIGTERM)
    except Exception:
        pass
    time.sleep(1.5)
    log("Starting final server on original port 8888 ...")
    final_log = LOG_DIR / "new_server_8888.log"
    try:
        with open(final_log, "w") as logf2:
            proc2 = subprocess.Popen(
                ["python3", str(KERNEL_SERVER_PATH), "--host", "0.0.0.0", "--port", "8888", "--log-level", "info"],
                cwd="/app", env=env, stdout=logf2, stderr=subprocess.STDOUT, start_new_session=True,
            )
        final_pid = proc2.pid
        log(f"Final server PID: {final_pid}")
    except Exception as e:
        log(f"Failed to start final server: {e}", "ERROR")
        return False
    for i in range(25):
        r = run(["curl", "-s", "-m", "3", f"{API_BASE}/health"], timeout=6)
        if r["ok"] and "kernel_alive" in r["stdout"]:
            log(f"Final server healthy on {API_BASE} after {i+1}s")
            log("APPROACH 3 SUCCESS", "SUCCESS")
            return True
        time.sleep(1)
    log("APPROACH 3 FAILED - final server not healthy", "ERROR")
    return False

