"""Camera-only pymmcore-plus grab: centre ROI of Kinetix_red, live preview or N frames to disk.

    python scripts/mm_grab.py                      # live preview, 's' saves a frame, close to stop
    python scripts/mm_grab.py --n 50 --out D:/AutoFocus/frames/test1

Runs on the system Python (pymmcore-plus + numpy; tkinter is stdlib), not the uv env.

What it touches: loads the config (which applies the file's System/Startup preset,
LappMainBranch1 State 1), sets AutoShutter 0 straight after, sets exposure and ROI,
and reads frames. It never calls a stage, focus, lamp or light-engine method:
illumination is set by hand, and Z is not moved.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np

CONFIG = Path(r"C:\agentic_microscope\config\micromanager\single_cam_red_noDMD_nocom10.cfg")
ROI = 518  # 37 DINO patches; 33.7 um at 100x (0.065 um/px)


def open_core(exposure_ms: float, roi: int, demo: bool = False, config: Path | None = None):
    """Load the instrument config (or, with demo=True, Micro-Manager's simulated devices)."""
    from pymmcore_plus import CMMCorePlus, find_micromanager

    core = CMMCorePlus.instance()
    mm_dir = Path(find_micromanager())
    core.setDeviceAdapterSearchPaths([str(mm_dir)])
    config = mm_dir / "MMConfig_demo.cfg" if demo else Path(config or CONFIG)
    core.loadSystemConfiguration(str(config))
    core.setAutoShutter(False)  # as loaded, every snap would switch the light engine on
    core.waitForSystem()
    if demo:  # a Kinetix22-sized simulated sensor
        cam = core.getCameraDevice()
        core.setProperty(cam, "OnCameraCCDXSize", 2400)
        core.setProperty(cam, "OnCameraCCDYSize", 2400)
        core.setProperty(cam, "PixelType", "16bit")
    core.setExposure(exposure_ms)
    core.clearROI()
    w, h = core.getImageWidth(), core.getImageHeight()
    if 0 < roi < min(w, h):  # roi 0 = full sensor
        core.setROI((w - roi) // 2, (h - roi) // 2, roi, roi)
    def prop(dev: str, *names: str):
        """First of `names` the device has; None if neither (recording must not stop a run)."""
        if dev not in core.getLoadedDevices():
            return None
        for name in names:
            if core.hasProperty(dev, name):
                return core.getProperty(dev, name)
        return None

    info = {
        "config": str(config),
        "camera": core.getCameraDevice(),
        "autoshutter": core.getAutoShutter(),
        "exposure_ms": core.getExposure(),
        "sensor": [w, h],
        "roi": list(core.getROI()),
        # The config's pixel-size table keys on the Nosepiece label only, so a 1.5x
        # intermediate magnification would not show up in pixel_um: record both.
        "pixel_um": core.getPixelSizeUm(),
        "objective": prop("Nosepiece", "Label", "State"),
        "intermediate_mag": prop("IntermediateMagnification", "Label", "State"),
        "position": positions(core),
    }
    print(json.dumps(info))
    return core, info


def set_and_read(core, device: str, prop: str, value) -> dict:
    core.setProperty(device, prop, value)
    core.waitForDevice(device)
    got = core.getProperty(device, prop)
    rec = {"device": device, "property": prop, "wanted": str(value), "read": got,
           "verified": str(got) == str(value)}
    print(json.dumps(rec))
    return rec


def aura_on(core, line: str, percent: float) -> list[dict]:
    """Transmitted lamp off, then the Aura line's intensity, the line, and the master State last.

    Aura intensity is per-mille (soft-matter-agents light_engine_line_intensity_is_per_mille),
    so 5 % is 50. Same order as soft-matter-agents live_view --aura.
    """
    line = line.upper()
    return [set_and_read(core, "DiaLamp", "State", 0),
            set_and_read(core, "Aura", f"{line}_Intensity", int(round(percent * 10))),
            set_and_read(core, "Aura", line, 1),
            set_and_read(core, "Aura", "State", 1)]


def aura_off(core) -> dict:
    return set_and_read(core, "Aura", "State", 0)


class PiezoReader:
    """Link to the NanoBench 6000 piezo controller through its vendor DLL.

    Reads by default: `stage.position.measured.get <channel>`. Writes only through
    `move_z` (one z position command, inside a caller-given window), and before the first
    write the security level is read and, if needed, set to User with the vendor install's
    own code (read from its config.ini at use, never stored); `close` puts the level found
    back. Super-user is never requested. Values are picometres (calibrated range max reads
    6.0e8 = 600 um). Channels 1/2/3 = x/y/z is the controller's labelling; the signs
    relative to the Ti2 axes are not verified.
    """

    VENDOR_CONFIG = Path(r"C:\Program Files (x86)\NanoBench 6000\data\config.ini")

    LIBRARY = Path(r"C:\Program Files (x86)\NanoBench 6000\data\controller_interface64.dll")
    CHANNELS = {"x": 1, "y": 2, "z": 3}

    def __init__(self, address: str = "COM4"):
        import ctypes

        self._ct = ctypes
        lib = ctypes.cdll.LoadLibrary(str(self.LIBRARY))
        lib.Init.restype = ctypes.c_void_p
        lib.Uninit.argtypes = [ctypes.c_void_p]
        lib.OpenSession.restype = ctypes.c_int
        lib.OpenSession.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lib.CloseSession.argtypes = [ctypes.c_void_p]
        lib.DoCommand.restype = ctypes.c_int
        lib.DoCommand.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        for name in ("GetAllResultNames", "GetAllResults"):
            getattr(lib, name).restype = ctypes.c_int
            getattr(lib, name).argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        self._lib, self._h = lib, lib.Init(None)
        if not lib.OpenSession(self._h, address.encode()):
            lib.Uninit(self._h)
            raise OSError(f"piezo controller did not open on {address} "
                          "(is the NanoBench program holding the port?)")
        self.address = address

    def _string(self, getter) -> str:
        probe = self._ct.create_string_buffer(2)
        size = getter(self._h, probe, 1) + 1
        buf = self._ct.create_string_buffer(max(size, 2))
        getter(self._h, buf, size)
        return buf.value.decode("utf-8", errors="replace")

    def read(self) -> dict:
        out = {}
        for axis, ch in self.CHANNELS.items():
            if self._lib.DoCommand(self._h, f"stage.position.measured.get {ch}".encode()) <= 0:
                continue
            names = self._string(self._lib.GetAllResultNames).splitlines()
            values = dict(zip(names, self._string(self._lib.GetAllResults).splitlines()))
            if "value" in values:
                out[f"piezo_{axis}_um"] = round(float(values["value"]) * 1e-6, 4)
        return out

    def _do(self, command: str) -> dict:
        n = self._lib.DoCommand(self._h, command.encode())
        if n <= 0:
            raise OSError(f"piezo command {command!r} failed (return {n})")
        names = self._string(self._lib.GetAllResultNames).splitlines()
        return dict(zip(names, self._string(self._lib.GetAllResults).splitlines()))

    #: picometres per um, confirmed by reading the calibrated range before the first write
    _PM = 1e6
    Z_RANGE_UM = (0.0, 600.0)

    def move_z(self, target_um: float, window_um: tuple[float, float]) -> float:
        """Closed-loop z to `target_um`, refused outside `window_um` or the stage range.

        The only command written is stage.position.command.set 3 -- no security level, no
        waveform. Returns the measured position after it settles (or 1 s).
        """
        lo = max(window_um[0], self.Z_RANGE_UM[0])
        hi = min(window_um[1], self.Z_RANGE_UM[1])
        if not lo <= target_um <= hi:
            raise ValueError(f"piezo z {target_um:.3f} um is outside the allowed "
                             f"{lo:.3f} .. {hi:.3f} um")
        if not getattr(self, "_unit_ok", False):
            mx = float(self._do("stage.position.calibrated-range.maximum.get 3")["value"])
            if mx != 6.0e8:
                raise OSError(f"z calibrated max reads {mx}, not 6.0e8 pm; unit not confirmed")
            self._unit_ok = True
            self.ensure_user_level()
        self._do(f"stage.position.command.set 3 {target_um * self._PM:.0f}")
        t0 = time.monotonic()
        while time.monotonic() - t0 < 1.0:
            z = float(self._do("stage.position.measured.get 3")["value"]) / self._PM
            if abs(z - target_um) < 0.02:
                break
            time.sleep(0.01)
        return z

    # -- security: User level for position commands, the found level put back on close
    def security_level(self) -> str:
        d = self._do("controller.security.user.get")
        return str(d.get("security", d.get("value", d)))

    def _user_code(self) -> str:
        import configparser

        cfg = configparser.ConfigParser()
        if not cfg.read(self.VENDOR_CONFIG, encoding="utf-8"):
            raise OSError(f"no vendor configuration at {self.VENDOR_CONFIG}")
        sec = next((s for s in cfg.sections() if s.lower() == "securitylevels"), None)
        code = sec and next((v for k, v in cfg[sec].items() if k.strip().lower() == "user"),
                            None)
        if not code:
            raise OSError("the vendor configuration names no User access code")
        code = code.strip()
        return code if code.lower().startswith("0x") else "0x" + code

    def ensure_user_level(self) -> None:
        if getattr(self, "found_level", None) is not None:
            return
        self.found_level = self.security_level()
        print(f"piezo security level found: {self.found_level}")
        lvl = self.found_level.lower()
        if "unlock" in lvl or "user" in lvl:
            self.changed_level = False
            return
        # the vendor's levels are None < User < Super User; this controller reports the
        # locked state as "None". Only that -> User is a change this link can undo (lock).
        if lvl not in ("none", "locked") and "lock" not in lvl:
            self.found_level = None
            raise OSError(f"piezo security level {lvl!r} is not one this link changes")
        self._do(f"controller.security.user.set {self._user_code()}")
        self.changed_level = True
        print(f"piezo security level now: {self.security_level()}")

    def restore_level(self) -> None:
        if getattr(self, "changed_level", False):
            self._do("controller.security.lock")
            self.changed_level = False
            now = self.security_level()
            ok = now.lower() == str(self.found_level).lower()
            print(f"piezo security level restored: {now}"
                  + ("" if ok else f"  WARNING: found {self.found_level!r} at start"))

    def close(self) -> None:
        try:
            self.restore_level()
        except Exception as exc:  # noqa: BLE001 - say it, then still close the session
            print(f"WARNING: piezo security level not restored: {exc}")
        try:
            self._lib.CloseSession(self._h)
        finally:
            self._lib.Uninit(self._h)


def positions(core, piezo: PiezoReader | None = None) -> dict:
    """Read-only XY (XYStage), Z (ZDrive) and, if given, the piezo, in um. Sets nothing."""
    out = {}
    if piezo is not None:
        try:
            out.update(piezo.read())
        except Exception as exc:  # noqa: BLE001
            out["piezo_error"] = str(exc)
    try:
        x, y = core.getXYPosition(core.getXYStageDevice() or "XYStage")
        out.update(x_um=round(x, 3), y_um=round(y, 3))
    except Exception as exc:  # noqa: BLE001 - a missing stage must not stop the camera
        out["xy_error"] = str(exc)
    try:
        out["z_um"] = round(core.getPosition("ZDrive"), 3)
    except Exception as exc:  # noqa: BLE001
        out["z_error"] = str(exc)
    return out


def vollath4(img: np.ndarray) -> float:
    """Scale-invariant Vollath F4: lag-1 minus lag-2 autocorrelation. Uncorrelated noise
    cancels between the two terms, so unlike Brenner it does not rise on dim blurred frames."""
    a = img.astype(np.float32)
    a = a - np.median(a)
    a /= max(float(np.abs(a).mean()), 1e-6)
    f = (a[:, :-1] * a[:, 1:]).mean() - (a[:, :-2] * a[:, 2:]).mean()
    g = (a[:-1] * a[1:]).mean() - (a[:-2] * a[2:]).mean()
    return float(f + g)


def brenner(img: np.ndarray) -> float:
    """Scale-invariant Brenner sharpness, a quick sanity number until the DINO head exists."""
    a = img.astype(np.float32)
    a = a - np.median(a)
    a /= max(float(np.abs(a).mean()), 1e-6)
    return float(((a[:, 2:] - a[:, :-2]) ** 2).mean() + ((a[2:] - a[:-2]) ** 2).mean())


def grab(core, n: int, out: Path, info: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    stack, meta = [], []
    core.startSequenceAcquisition(n, 0.0, True)
    t0 = time.monotonic()
    while len(stack) < n:
        if core.getRemainingImageCount():
            img, md = core.popNextImageAndMD()
            stack.append(np.asarray(img, dtype=np.uint16))
            # Read when the frame is popped, not when it was exposed: during a hand-driven
            # focus sweep the two differ by the buffer latency.
            meta.append({"ImageNumber": md.get("ImageNumber", None),
                         "ElapsedTime-ms": md.get("ElapsedTime-ms", None), **positions(core)})
        elif time.monotonic() - t0 > 30 + 3 * n * core.getExposure() / 1000:
            break
        else:
            time.sleep(0.001)
    if core.isSequenceRunning():
        core.stopSequenceAcquisition()
    arr = np.stack(stack)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    np.save(out / f"stack_{stamp}.npy", arr)
    (out / f"stack_{stamp}.json").write_text(json.dumps(
        {**info, "n": len(arr), "position_end": positions(core), "frames": meta},
        default=str, indent=1))
    b = [brenner(f) for f in arr]
    print(f"saved {arr.shape} to {out}  mean {arr.mean():.0f} ADU  max {arr.max()}  "
          f"brenner {np.mean(b):.3f} +- {np.std(b):.3f}")


def live(core, out: Path) -> None:
    import tkinter as tk

    out.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    root.title("Kinetix_red centre ROI -- 's' saves a frame")
    canvas = tk.Canvas(root, width=ROI, height=ROI)
    canvas.pack()
    label = tk.Label(root, font=("Consolas", 11), anchor="w")
    label.pack(fill="x")
    item = canvas.create_image(0, 0, anchor="nw")
    state = {"img": None, "photo": None, "n": 0, "t": time.monotonic(),
             "pos": positions(core), "pos_t": 0.0}

    def save(_event=None):
        if state["img"] is not None:
            p = out / f"frame_{datetime.now():%Y%m%d-%H%M%S-%f}.npy"
            np.save(p, state["img"])
            p.with_suffix(".json").write_text(json.dumps(positions(core)))
            print(f"saved {p}  {state['pos']}")

    def tick():
        if core.getRemainingImageCount():
            img = np.asarray(core.getLastImage(), dtype=np.uint16)
            core.clearCircularBuffer()
            state["img"], state["n"] = img, state["n"] + 1
            f = img.astype(np.float32)
            lo, hi = np.percentile(f, (0.5, 99.8))
            g = np.clip((f - lo) * (255.0 / max(hi - lo, 1.0)), 0, 255).astype(np.uint8)
            state["photo"] = tk.PhotoImage(data=b"P5 %d %d 255\n" % g.shape[::-1] + g.tobytes(),
                                           format="PPM")
            canvas.itemconfigure(item, image=state["photo"])
            fps = state["n"] / max(time.monotonic() - state["t"], 1e-6)
            sat = float(np.mean(img >= 65535)) * 100
            if time.monotonic() - state["pos_t"] > 0.5:  # stage reads are slow; 2 Hz is plenty
                state["pos"], state["pos_t"] = positions(core), time.monotonic()
            p = state["pos"]
            xyz = (f"x {p.get('x_um', float('nan')):9.2f}  y {p.get('y_um', float('nan')):9.2f}  "
                   f"z {p.get('z_um', float('nan')):9.3f} um")
            label.configure(text=f"frame {state['n']:5d}  {fps:4.1f} fps  mean {f.mean():7.0f}  "
                                 f"max {img.max():5d}  sat {sat:4.2f}%  brenner {brenner(img):6.3f}"
                                 f"\n{xyz}")
        root.after(20, tick)

    root.bind("s", save)
    core.startContinuousSequenceAcquisition(0.0)
    try:
        root.after(20, tick)
        root.mainloop()
    finally:
        if core.isSequenceRunning():
            core.stopSequenceAcquisition()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exposure", type=float, default=30.0, help="ms")
    ap.add_argument("--n", type=int, default=0, help="grab N frames to disk instead of live view")
    ap.add_argument("--out", type=Path, default=Path(r"D:\AutoFocus\frames"))
    ap.add_argument("--demo", action="store_true", help="Micro-Manager demo devices, no hardware")
    args = ap.parse_args()

    core, info = open_core(args.exposure, ROI, demo=args.demo)
    if args.n > 0:
        grab(core, args.n, args.out, info)
    else:
        live(core, args.out)


if __name__ == "__main__":
    main()
