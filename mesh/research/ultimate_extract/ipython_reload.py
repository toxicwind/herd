import sys
import time
try:
    from jupyter_client import KernelManager
except ImportError:
    print("jupyter_client not available")
    sys.exit(1)

conn_file = "/tmp/tmpx7jg80e3.json"
km = KernelManager(connection_file=conn_file)
km.load_connection_file()
kc = km.client()
kc.start_channels()

# Execute a deep reload
kc.execute("""
import importlib
import sys
import types

reloaded = []
for name in list(sys.modules.keys()):
    mod = sys.modules[name]
    if isinstance(mod, types.ModuleType) and hasattr(mod, '__file__') and mod.__file__:
        if '/app/' in mod.__file__ or '/mnt/agents/' in mod.__file__:
            try:
                importlib.reload(mod)
                reloaded.append(name)
            except Exception:
                pass

print(f"Reloaded {len(reloaded)} modules")
""")

time.sleep(2)
kc.stop_channels()
print("SUCCESS")