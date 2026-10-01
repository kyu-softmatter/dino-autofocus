"""Switch the Aura master State and the DiaLamp off, each read back.

    python scripts/lights_off.py

live_focus.py --set DiaLamp State 1 leaves the lamp on when its window closes; this is the
one-click way back to dark. Nothing moves.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mm_grab import aura_off, open_core, set_and_read  # noqa: E402


def main() -> None:
    core, _ = open_core(10.0, 0)
    recs = [aura_off(core), set_and_read(core, "DiaLamp", "State", 0)]
    bad = [f"{r['device']}.{r['property']}" for r in recs if not r["verified"]]
    print(f"WARNING: not verified: {', '.join(bad)}" if bad
          else "Aura OFF, DiaLamp OFF (read back)")


if __name__ == "__main__":
    main()
