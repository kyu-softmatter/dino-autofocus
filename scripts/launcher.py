"""One-window launcher for the substrate-scan workflow (docs/runs/2026-09-30_substrate-scan.md).

    pythonw scripts/launcher.py          # or "DINO Autofocus.exe" on the desktop
    python scripts/launcher.py --screenshot out.png   # layout check, no jobs started

Every job opens in its own console (Ctrl+C there stops it, and the script's own cleanup
switches the light off) with its output also written to a log: the sample folder when a
sample is chosen, else outputs/launcher_logs. Hardware jobs refuse to start while another
program is already driving the microscope. The objective change and 100x steps stay manual.

Runs on the system Python (stdlib only); hardware scripts use the same interpreter, plots
the repo's uv env.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
SAMPLES_ROOT = Path(r"D:\AutoFocus\samples")
LOG_ROOT = REPO / "outputs" / "launcher_logs"
HW_PY = Path(sys.executable).with_name("python.exe")  # pythonw -> python: console output
VENV_PY = REPO / ".venv" / "Scripts" / "python.exe"
# command-line fragments of programs that hold the camera / stage
HW_MARKERS = ("live_focus.py", "scan_4x.py", "focus_100x.py", "change_objective.py",
              "find_particle_z.py", "focus_servo.py", "mm_grab.py", "edge_track.py",
              "lights_off.py", "ImageJ.exe", "Micro-Manager", "NIS-Elements", "nis_ar")
MUTED, SERIES = "#52514e", "#2a78d6"  # live_focus.py's palette


def hint(parent, text: str, row: int) -> None:
    ttk.Label(parent, text=text, style="Hint.TLabel", justify="left").grid(
        row=row, column=0, columnspan=4, sticky="w", pady=(2, 0))


def samples() -> list[str]:
    if not SAMPLES_ROOT.is_dir():
        return []
    return sorted((d.name for d in SAMPLES_ROOT.iterdir() if d.is_dir()), reverse=True)


def hardware_users() -> list[str]:
    """Other processes whose command line names a microscope program (empty if unknown)."""
    ps = ("Get-CimInstance Win32_Process | ForEach-Object "
          "{ \"$($_.ProcessId)`t$($_.Name)`t$($_.CommandLine)\" }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True,
                             text=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW,
                             encoding="utf-8", errors="replace").stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    hits = []
    for line in out.splitlines():
        if any(s in line for s in ("--demo", "launcher.py", "run_logged.py", "powershell")):
            continue
        if any(m.lower() in line.lower() for m in HW_MARKERS):
            hits.append(line.replace("\t", "  ")[:160])
    return hits


class Launcher:
    def __init__(self, root: tk.Tk):
        self.root, self.jobs = root, []  # jobs: (label, Popen, hardware)
        root.title("DINO Autofocus")
        root.resizable(False, False)
        st = ttk.Style(root)
        st.configure(".", font=("Segoe UI", 10))
        st.configure("Head.TLabel", font=("Segoe UI", 15, "bold"))
        st.configure("Hint.TLabel", foreground=MUTED, font=("Segoe UI", 9))
        st.configure("Go.TButton", font=("Segoe UI", 10, "bold"), padding=6)
        st.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        pad = {"padx": 8, "pady": 5}
        f = ttk.Frame(root, padding=12)
        f.grid()
        ttk.Label(f, text="DINO Autofocus", style="Head.TLabel").grid(
            row=0, column=0, sticky="w", padx=8)
        ttk.Label(f, text="Find the sample, then autofocus-scan it. Work top to bottom.",
                  style="Hint.TLabel").grid(row=1, column=0, sticky="w", padx=8)

        # -- sample
        s = ttk.LabelFrame(f, text="Sample", padding=8)
        s.grid(row=2, column=0, sticky="ew", **pad)
        self.sample = tk.StringVar(value=(samples() or [""])[0])
        self.sample_box = ttk.Combobox(s, textvariable=self.sample, width=26, values=samples(),
                                       postcommand=lambda: self.sample_box.configure(
                                           values=samples()))
        self.sample_box.grid(row=0, column=0, sticky="w")
        ttk.Button(s, text="Open folder", command=self.open_folder).grid(row=0, column=1, padx=6)
        ttk.Button(s, text="New", command=lambda: self.sample.set("")).grid(row=0, column=2)
        hint(s, "Pick a sample to continue, or New: live view names it from the clock.", 1)

        # -- 0 status
        s0 = ttk.LabelFrame(f, text="Step 0   Check the microscope", padding=8)
        s0.grid(row=3, column=0, sticky="ew", **pad)
        ttk.Button(s0, text="Show objective / Z / PFS", style="Go.TButton",
                   command=lambda: self.run("status", [HW_PY, SCRIPTS / "change_objective.py",
                                                       "--status"], hw=True)
                   ).grid(row=0, column=0, columnspan=4, sticky="ew")
        s0.columnconfigure(0, weight=1)
        hint(s0, "Read only. The 4x scan needs the 4x objective in place.", 1)

        # -- 1 live view
        lv = ttk.LabelFrame(f, text="Step 1   Find the sample: live view + edge trace",
                            padding=8)
        lv.grid(row=4, column=0, sticky="ew", **pad)
        self.light = tk.StringVar(value="bf")
        ttk.Radiobutton(lv, text="Brightfield (DiaLamp): to find the hole edge",
                        variable=self.light, value="bf", command=self.light_changed
                        ).grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Radiobutton(lv, text="Aura line", variable=self.light, value="aura",
                        command=self.light_changed).grid(row=1, column=0, sticky="w")
        self.line = tk.StringVar(value="GREEN")
        self.pct = tk.StringVar(value="1")
        ttk.Combobox(lv, textvariable=self.line, values=["GREEN"], width=8).grid(
            row=1, column=1, sticky="w")
        ttk.Entry(lv, textvariable=self.pct, width=5).grid(row=1, column=2, sticky="e")
        ttk.Label(lv, text="%").grid(row=1, column=3, sticky="w")
        self.exposure = tk.StringVar(value="12")
        self.hole = tk.StringVar(value="6")
        self.speed = tk.StringVar(value="100")
        for r, (label, var, unit) in enumerate((("Exposure", self.exposure, "ms"),
                                                ("Hole diameter", self.hole, "mm"),
                                                ("Trace speed", self.speed, "um/s")), start=2):
            ttk.Label(lv, text=label).grid(row=r, column=0, sticky="w")
            ttk.Entry(lv, textvariable=var, width=8).grid(row=r, column=1, sticky="w")
            ttk.Label(lv, text=unit).grid(row=r, column=2, columnspan=2, sticky="w")
        ttk.Button(lv, text="Start live view", style="Go.TButton", command=self.live).grid(
            row=5, column=0, columnspan=4, sticky="ew", pady=(6, 2))
        hint(lv, "Put the hole edge in view and press  t  to trace it (stops after a full\n"
                 "loop).  + / -  change speed,  Esc  stops. Brightfield leaves the DiaLamp\n"
                 "ON when the window closes: use  Lights off  below when done.", 6)

        # -- 2 scan
        sc = ttk.LabelFrame(f, text="Step 2   Autofocus scan at 4x (Aura GREEN 1 %)",
                            padding=8)
        sc.grid(row=5, column=0, sticky="ew", **pad)
        self.scan_exp = tk.StringVar(value="")
        ttk.Label(sc, text="Exposure").grid(row=0, column=0, sticky="w")
        ttk.Entry(sc, textvariable=self.scan_exp, width=8).grid(row=0, column=1, sticky="w")
        ttk.Label(sc, text="ms  (blank = auto)").grid(row=0, column=2, sticky="w")
        self.dry = tk.BooleanVar(value=False)
        ttk.Checkbutton(sc, text="Dry run: only print the tile plan", variable=self.dry).grid(
            row=1, column=0, columnspan=3, sticky="w")
        ttk.Button(sc, text="Start 4x scan", style="Go.TButton", command=self.scan).grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=(6, 2))
        ttk.Button(sc, text="Show scan result (mosaic + z map)", command=self.plot).grid(
            row=3, column=0, columnspan=3, sticky="ew", pady=2)
        hint(sc, "Moves the stage and focus over the traced hole.\n"
                 "Ctrl+C in its window stops it and switches the light off.", 4)

        # -- misc
        m = ttk.Frame(f)
        m.grid(row=6, column=0, sticky="ew", **pad)
        ttk.Button(m, text="Lights off (Aura + DiaLamp)",
                   command=lambda: self.run("lights_off", [HW_PY, SCRIPTS / "lights_off.py"],
                                            hw=True)).pack(side="left", expand=True, fill="x")
        ttk.Button(m, text="Try the demo (no hardware)",
                   command=lambda: self.run("live_demo", [HW_PY, SCRIPTS / "live_focus.py",
                                                          "--demo"], hw=False)
                   ).pack(side="left", expand=True, fill="x", padx=(6, 0))

        self.status = tk.StringVar(value="Idle.")
        ttk.Label(f, textvariable=self.status, foreground=SERIES, wraplength=420).grid(
            row=7, column=0, sticky="w", **pad)
        self.light_changed()
        self.poll()

    # -- helpers
    def light_changed(self) -> None:
        # brightfield at 12-bit: 10-12 ms; Aura GREEN 1 % at 4x needs ~1 s (run log)
        if self.light.get() == "bf" and self.exposure.get() in ("", "500"):
            self.exposure.set("12")
        elif self.light.get() == "aura" and self.exposure.get() == "12":
            self.exposure.set("500")

    def sample_id(self, required: bool) -> str | None:
        sid = self.sample.get().strip()
        if required and not (sid and (SAMPLES_ROOT / sid / "sample.json").is_file()):
            messagebox.showerror("DINO Autofocus", f"Sample {sid!r} has no sample.json yet.\n"
                                 "Trace the hole edge in brightfield live view first (Step 1).")
            return None
        return sid

    def open_folder(self) -> None:
        d = SAMPLES_ROOT / self.sample.get().strip()
        subprocess.Popen(["explorer", str(d if d.is_dir() else SAMPLES_ROOT)])

    def number(self, var: tk.StringVar, name: str) -> str | None:
        try:
            float(var.get())
        except ValueError:
            messagebox.showerror("DINO Autofocus", f"{name}: {var.get()!r} is not a number.")
            return None
        return var.get().strip()

    def run(self, label: str, cmd: list, hw: bool) -> None:
        if hw:
            mine = [j for j in self.jobs if j[2] and j[1].poll() is None]
            if mine:
                messagebox.showwarning("DINO Autofocus",
                                       f"{mine[0][0]} is still running; close it first.")
                return
            self.status.set("Checking that the microscope is free ...")
            self.root.update_idletasks()
            others = hardware_users()
            if others and not messagebox.askyesno(
                    "DINO Autofocus", "Another program seems to be using the microscope:\n\n"
                    + "\n".join(others[:5]) + "\n\nStart anyway?", icon="warning"):
                self.status.set("Not started.")
                return
        sid = self.sample.get().strip()
        sdir = SAMPLES_ROOT / sid if sid else None
        log_dir = sdir if sdir and sdir.is_dir() else LOG_ROOT
        log = log_dir / f"launcher_{label}_{time.strftime('%Y%m%d-%H%M%S')}.log"
        wrapped = [HW_PY, SCRIPTS / "run_logged.py", log, "--", *cmd]
        p = subprocess.Popen([str(c) for c in wrapped], cwd=REPO,
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.jobs.append((label, p, hw))
        self.status.set(f"Started {label} (log: {log.name}).")

    def poll(self) -> None:
        running = [j[0] for j in self.jobs if j[1].poll() is None]
        if running:
            self.status.set("Running: " + ", ".join(running))
        elif self.status.get().startswith("Running"):
            self.status.set("Idle.")
        self.root.after(1000, self.poll)

    # -- jobs
    def live(self) -> None:
        exp, hole, speed = (self.number(v, n) for v, n in ((self.exposure, "Exposure"),
                                                           (self.hole, "Hole diameter"),
                                                           (self.speed, "Trace speed")))
        if None in (exp, hole, speed):
            return
        cmd = [HW_PY, SCRIPTS / "live_focus.py", "--exposure", exp, "--hole-diameter", hole,
               "--track-speed", speed]
        if sid := self.sample_id(required=False):
            cmd += ["--sample", sid]
        if self.light.get() == "bf":
            cmd += ["--set", "Aura", "State", "0", "--set", "DiaLamp", "State", "1"]
            label = "live_bf"
        else:
            if (pct := self.number(self.pct, "Aura %")) is None:
                return
            cmd += ["--set", "DiaLamp", "State", "0", "--aura", self.line.get().strip(), pct]
            label = f"live_{self.line.get().strip().lower()}"
        self.run(label, cmd, hw=True)

    def scan(self) -> None:
        if not (sid := self.sample_id(required=True)):
            return
        cmd = [HW_PY, SCRIPTS / "scan_4x.py", "--sample", sid]
        if self.scan_exp.get().strip():
            if (exp := self.number(self.scan_exp, "Scan exposure")) is None:
                return
            cmd += ["--exposure", exp]
        if self.dry.get():
            cmd.append("--dry-run")
        elif not messagebox.askokcancel(
                "Start 4x scan",
                f"Sample {sid}\n\nThis moves the XY stage and ZDrive and switches on Aura "
                "GREEN 1 %.\n\n- Nosepiece on 4x?\n- Hole traced in brightfield this "
                "session (the sample can move)?\n\nCtrl+C in the scan window stops it.",
                icon="warning"):
            return
        self.run("scan4x", cmd, hw=True)

    def plot(self) -> None:
        if not (sid := self.sample_id(required=True)):
            return
        scans = sorted((SAMPLES_ROOT / sid).glob("scan4x_*/scan.json"))
        if not scans:
            messagebox.showinfo("DINO Autofocus", f"No finished 4x scan in {sid} yet.")
            return
        self.run("plot_scan", [VENV_PY, SCRIPTS / "plot_scan.py", scans[-1].parent], hw=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshot", type=Path, default=None,
                    help="save the window to this PNG after ~1.5 s and exit (layout check)")
    args = ap.parse_args()
    if sys.platform == "win32":  # crisp text under display scaling
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    root = tk.Tk()
    Launcher(root)
    if args.screenshot is not None:
        def snap_window() -> None:
            from PIL import ImageGrab  # only needed for the layout check

            root.update()
            x, y = root.winfo_rootx(), root.winfo_rooty()
            ImageGrab.grab((x, y, x + root.winfo_width(), y + root.winfo_height())).save(
                args.screenshot)
            root.destroy()

        root.after(1500, snap_window)
    root.mainloop()


if __name__ == "__main__":
    main()
