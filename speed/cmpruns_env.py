"""The scripts' settings as cmpruns.py reads them (speed/local.env under the environment)."""
import os
env = {}
path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "local.env")
if os.path.exists(path):
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = os.path.expanduser(v.strip().strip('"').strip("'").replace("$HOME", "~"))
env.update({k: v for k, v in os.environ.items() if k.startswith("VIC2_")})
WORK = env.get("VIC2_SPEED_WORK", os.path.expanduser("~/.cache/vic2speed/opt"))
