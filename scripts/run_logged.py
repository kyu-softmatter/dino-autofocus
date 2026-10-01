"""Run a command in this console and copy its output to a log file (used by launcher.py).

    python scripts/run_logged.py LOG -- python scripts/scan_4x.py --sample ...

Ctrl+C in the console reaches the child (its `finally` turns the light off); this wrapper
ignores it and keeps copying until the child has exited, then waits for Enter so the
window stays readable.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def main() -> None:
    log, cmd = Path(sys.argv[1]), sys.argv[sys.argv.index("--") + 1:]
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    log.parent.mkdir(parents=True, exist_ok=True)
    print("> " + subprocess.list2cmdline(cmd))
    print(f"  log: {log}\n  Ctrl+C stops the run (lights off in its own cleanup).\n")
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    with log.open("a", encoding="utf-8") as f:
        f.write(f"# {time.strftime('%Y-%m-%d %H:%M:%S')}  {subprocess.list2cmdline(cmd)}\n")
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                             encoding="utf-8", errors="replace")
        for line in p.stdout:
            sys.stdout.write(line)
            f.write(line)
            f.flush()
        code = p.wait()
        f.write(f"# exit {code}\n")
    print(f"\n--- finished, exit code {code} ---")
    with contextlib.suppress(EOFError):
        input("Press Enter to close this window.")
    sys.exit(code)


if __name__ == "__main__":
    main()
