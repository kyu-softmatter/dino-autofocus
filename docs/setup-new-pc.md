# Setting up dino-autofocus on another PC

## 1. Clone

```
git clone https://github.com/kyu-softmatter/dino-autofocus
```

Any folder works; the launcher exe is built for the clone it is built from.

## 2. Python

Two interpreters are used:

| Interpreter | Runs | Install |
|---|---|---|
| System Python 3.12 (`%LOCALAPPDATA%\Programs\Python\Python312`, or on PATH) | `scripts/launcher.py` (tkinter UI) and the hardware scripts it starts | python.org installer, then `python -m pip install numpy pillow opencv-python pymmcore==12.5.0.75.0 pymmcore-plus==0.18.1` |
| Repo uv env (`.venv`) | plots, the DINO focus scorer, dataset generation, training | `uv sync` in the repo (pulls torch cu126) |

## 3. DINOv2 backbone (only for the focus scorer / training)

`dino_autofocus.backbone` loads a pinned local clone, by default `../dinov2` next to
the repo (override with the `DINOV2_REPO` environment variable):

```
git clone https://github.com/facebookresearch/dinov2 ../dinov2
git -C ../dinov2 checkout 7764ea0f912e53c92e82eb78a2a1631e92725fc8
```

## 4. Build the desktop launcher

```
powershell -ExecutionPolicy Bypass -File tools\launcher\build.ps1
```

Writes `DINO Autofocus.exe` to the Desktop using the .NET Framework compiler that ships
with Windows. The exe only starts `scripts/launcher.py`, so editing the launcher needs no
rebuild. If `autofocus.ico` is missing, `make_icon.py` (Pillow) redraws it.

## 5. Trained focus head

`models/heads/head_k100x_dinov2_vits14_L1.joblib` (+ `.json` metrics) is the head trained
on the synthetic 100x set. Pass it to the live view with
`--head models/heads/head_k100x_dinov2_vits14_L1.joblib`.

## Microscope-PC only (not needed to build or open the UI)

These are hard-coded for the Ti2 bench and only matter where the hardware is attached:

- `C:\agentic_microscope` -- the `hardware` module and the Micro-Manager config
  `config\micromanager\single_cam_red_noDMD_nocom10.cfg` (`scripts/mm_grab.py`,
  `scan_4x.py`, `focus_100x.py`)
- `C:\Program Files (x86)\NanoBench 6000` -- stage controller DLL and config
- `D:\AutoFocus\samples`, `D:\AutoFocus\frames` -- default sample / frame folders
  (`SAMPLES_ROOT` in `launcher.py`, `live_focus.py`, `scan_4x.py`; `--samples-root` /
  `--out` override them)

Generated data (`data/`, `outputs/`, `*.npz`, `*.npy`, `*.tif`) is not in git; regenerate
it with `scripts/farm_p5.py` / `scripts/make_dataset.py`.
