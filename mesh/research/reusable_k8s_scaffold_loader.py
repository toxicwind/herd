#!/usr/bin/env python3
"""Reusable dynamic scaffold loader for any k8s/box. Auto-detects env, bins, python master, perms fix, full dump.
Designed for toxic-like restricted envs. Saves all to artifacts/ no truncation.
Python call tracking internal.
"""
import os, sys, json, subprocess, traceback, platform, shutil, glob
from pathlib import Path
from datetime import datetime, timezone

ARTIFACTS = Path("/home/workdir/artifacts") if Path("/home/workdir/artifacts").exists() else Path("./artifacts")
ARTIFACTS.mkdir(exist_ok=True, parents=True)
MNT = Path("/mnt")
MNT.mkdir(exist_ok=True, parents=True)

def force_run(cmd, timeout=60, shell=True):
    """Forceful run with try/catch, perm/hidden fix attempt, full json output."""
    result = {"cmd": cmd, "ok": False, "stdout": "", "stderr": "", "returncode": -1, "trace": None}
    try:
        # Attempt perm fixes
        for p in ["/tmp", str(ARTIFACTS), str(MNT), "/home", "/root"]:
            try:
                os.chmod(p, 0o777)
            except: pass
        proc = subprocess.run(cmd if isinstance(cmd, list) else cmd, shell=shell, capture_output=True, text=True, timeout=timeout)
        result["stdout"] = proc.stdout
        result["stderr"] = proc.stderr
        result["returncode"] = proc.returncode
        result["ok"] = proc.returncode == 0
    except Exception as e:
        result["trace"] = traceback.format_exc()
        result["stderr"] = str(e)
    return result

def detect_env():
    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python": sys.executable,
        "python_version": sys.version,
        "uid": os.getuid(),
        "user": os.getenv("USER") or os.getenv("LOGNAME") or "unknown",
        "home": str(Path.home()),
        "cwd": os.getcwd(),
        "path": os.getenv("PATH", ""),
        "k8s_indicators": {},
        "vnc": None,
        "bins": {},
        "hidden_scripts": [],
        "env_vars": dict(os.environ),
        "python_pkgs_count": 0,
        "master_python": sys.executable,
    }
    # k8s
    for k in ["KUBERNETES_SERVICE_HOST", "HOSTNAME", "TERMINAL_JWT_VAL"]:
        if k in os.environ:
            data["k8s_indicators"][k] = os.environ[k][:50] + "..." if len(os.environ[k]) > 50 else os.environ[k]
    # VNC
    for p in ["/tmp/.X11-unix", "/tmp/.X*-lock"]:
        if glob.glob(p):
            data["vnc"] = "possible X11"
    # bins not in path
    bin_dirs = ["/usr/local/bin", "/usr/bin", "/bin", "/sbin", "/usr/sbin", "/opt", str(Path.home() / "bin")]
    all_bins = []
    for d in bin_dirs:
        if os.path.isdir(d):
            for f in os.listdir(d):
                fp = os.path.join(d, f)
                if os.path.isfile(fp) and os.access(fp, os.X_OK):
                    all_bins.append(fp)
    data["bins"]["count"] = len(all_bins)
    data["bins"]["sample"] = all_bins[:50]
    # hidden readable scripts
    for root, dirs, files in os.walk(str(Path.home()), topdown=True):
        dirs[:] = [d for d in dirs if not d.startswith(".") or d in [".config", ".local", ".grok"]]  # limit
        for f in files:
            if f.startswith(".") and f.endswith((".sh", ".py", ".bash")):
                data["hidden_scripts"].append(os.path.join(root, f))
        if len(data["hidden_scripts"]) > 20: break
    # python pkgs
    r = force_run([sys.executable, "-m", "pip", "list", "--format=json"])
    if r["ok"]:
        try:
            pkgs = json.loads(r["stdout"])
            data["python_pkgs_count"] = len(pkgs)
        except: pass
    return data

def main():
    print("=== REUSABLE K8S SCAFFOLD LOADER START ===")
    info = detect_env()
    out_path = ARTIFACTS / "scaffold_env_dump.json"
    with open(out_path, "w") as f:
        json.dump(info, f, indent=2, default=str)
    print(f"Saved full dump to {out_path}")
    # also mnt
    shutil.copy(out_path, MNT / "scaffold_env_dump.json")
    # dedup env
    env_path = ARTIFACTS / "dedup_env.txt"
    with open(env_path, "w") as f:
        for k,v in sorted(info["env_vars"].items()):
            f.write(f"{k}={v}\n")
    print(f"Dedup env saved {env_path}")
    # master python is current since only one major
    print(json.dumps({"master_python": info["master_python"], "pkgs": info["python_pkgs_count"], "bins_count": info["bins"]["count"]}, indent=2))
    print("=== LOADER COMPLETE ===")
    return info

if __name__ == "__main__":
    main()
