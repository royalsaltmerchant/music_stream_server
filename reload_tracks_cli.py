#!/usr/bin/env python3
"""
CLI script to reload tracks in the running radio server.

Usage:
    python reload_tracks_cli.py

This sends SIGHUP to the running radio.py process, triggering a track reload
from the configured source (local CSV or Google Sheets).
"""
import os
import signal
import subprocess
import sys


def find_radio_pid() -> int | None:
    """Find the PID of the running radio.py server."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "python.*radio.py"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            # May return multiple PIDs, take the first (parent process)
            pids = result.stdout.strip().split("\n")
            return int(pids[0])
    except Exception:
        pass
    return None


def main():
    pid = find_radio_pid()

    if not pid:
        print("Error: radio.py server not found running", file=sys.stderr)
        sys.exit(1)

    try:
        os.kill(pid, signal.SIGHUP)
        print(f"Sent SIGHUP to radio server (PID {pid}) - tracks will reload")
    except ProcessLookupError:
        print(f"Error: Process {pid} not found", file=sys.stderr)
        sys.exit(1)
    except PermissionError:
        print(f"Error: Permission denied to signal process {pid}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
