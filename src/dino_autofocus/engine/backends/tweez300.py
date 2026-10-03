"""Tweez300 (the vendor tweezers software) as `engine.tweezers.Tweezers`: NOT WIRED YET.

Tweez300 stays running on the microscope PC and owns the tweezers hardware; the app would send
it commands. The user says it can be driven over its **Python API** or **TCP**, but the command
names, units and port are not in yet, so every call here refuses and nothing is opened, sent or
imported. When the reference arrives:

1. fill `_Transport.send` for the chosen transport (Python API module or TCP host:port),
2. map `traps`, `move_trap`, `set_trap` to its commands, with its units turned into um from the
   field centre (calibration: Tweez300 units -> camera pixels -> um, per objective),
3. read every move back, and keep `bench=True`: `guards.TrapAxis` then refuses moves while the
   stand's bench-motion lock is on (T-036), as for every other real motion,
4. wire it in `server/__main__.py` (`simulated_extras` gives the bench no tweezers today) behind
   a reviewed card.

Known from the 2026-09 mock agent data: Tweez300GUI.exe / Tweez300GUIPython.exe /
Tweez300SystemManager.exe; positions in its own units; laser power set by hand; no position
feedback; limits per objective. The single-camera cfg notes Tweez300 may hold Kinetix_blue.
"""

from __future__ import annotations

from typing import Literal

from ..backend import require_token
from ..tweezers import TrapState, TweezersInfo

Transport = Literal["python", "tcp"]

NOT_WIRED = ("Tweez300 is not wired yet: its Python API / TCP command reference is not in "
             "(card T-20261002-2205). Nothing was sent.")


class Tweez300NotWired(RuntimeError):
    pass


class Tweez300Tweezers:
    def __init__(self, transport: Transport = "tcp", *, host: str = "127.0.0.1",
                 port: int | None = None, module: str | None = None) -> None:
        # stored only; no socket is opened and no module is imported
        self.transport, self.host, self.port, self.module = transport, host, port, module

    def info(self) -> TweezersInfo:
        return TweezersInfo("tweez300", 0, bench=True,
                            notes={"state": NOT_WIRED, "transport": self.transport})

    def traps(self) -> list[TrapState]:
        raise Tweez300NotWired(NOT_WIRED)

    def move_trap(self, index: int, x_um: float, y_um: float, z_um: float, *,
                  token: object) -> TrapState:
        require_token(token)
        raise Tweez300NotWired(NOT_WIRED)

    def set_trap(self, index: int, on: bool, *, token: object) -> TrapState:
        require_token(token)
        raise Tweez300NotWired(NOT_WIRED)

    def close(self) -> None:
        return None
