"""Install or remove the Kalshi recorder's scheduled jobs (user LaunchAgents).

    python ops/kalshi_launchd.py install
    python ops/kalshi_launchd.py uninstall
    python ops/kalshi_launchd.py print      # show the plists, install nothing

Quotes every 5 minutes, depth every 15. launchd does not run jobs while the
machine sleeps, so a sleeping laptop produces gaps; `runs.jsonl` shows them.
"""
import os
import plistlib
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AGENTS = os.path.expanduser("~/Library/LaunchAgents")
JOBS = {"quotes": 300, "depth": 900}


def label(job):
    return f"local.strategy-lab.kalshi-{job}"


def plist(job, interval):
    logs = os.path.expanduser("~/Library/Logs/strategy-lab")
    return {
        "Label": label(job),
        "ProgramArguments": [sys.executable, "-m", "lab.recorders.kalshi", job],
        "WorkingDirectory": REPO,
        "StartInterval": interval,
        "RunAtLoad": True,
        "StandardOutPath": os.path.join(logs, f"kalshi-{job}.log"),
        "StandardErrorPath": os.path.join(logs, f"kalshi-{job}.err"),
        "ProcessType": "Background",
    }


def main(argv):
    action = argv[0] if argv else "print"
    uid = os.getuid()
    for job, interval in JOBS.items():
        path = os.path.join(AGENTS, label(job) + ".plist")
        if action == "print":
            print(plistlib.dumps(plist(job, interval)).decode())
        elif action == "install":
            os.makedirs(AGENTS, exist_ok=True)
            os.makedirs(os.path.expanduser("~/Library/Logs/strategy-lab"), exist_ok=True)
            subprocess.run(["launchctl", "bootout", f"gui/{uid}/{label(job)}"], capture_output=True)
            with open(path, "wb") as handle:
                plistlib.dump(plist(job, interval), handle)
            subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", path], check=True)
            print(f"installed {label(job)} every {interval}s")
        elif action == "uninstall":
            subprocess.run(["launchctl", "bootout", f"gui/{uid}/{label(job)}"], capture_output=True)
            if os.path.exists(path):
                os.remove(path)
            print(f"removed {label(job)}")
        else:
            print(__doc__)
            return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
