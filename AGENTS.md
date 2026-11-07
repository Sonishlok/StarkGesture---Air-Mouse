# AGENTS.md

> **Status: implemented.** `stark_gestures.py` contains the full tool in one file, alongside `Documentation/`, `requirements.txt`, and `README.md`. There is no lint config, automated test suite, or CI yet; the manual acceptance checklist is doc 03 §11.

## Source of truth (read before coding)

| Priority | File | Authority |
|---|---|---|
| 1 | `Documentation/02_Stark Gestures — Backend Technical Architecture (MVP).md` | Authoritative architecture, constants, algorithms, setup. Its "differences from the PRD" appendix wins every conflict. |
| 2 | `Documentation/03_Stark Gestures — App Flow Document (MVP).md` | Applies doc 02's resolutions; authoritative UX flow, feedback, acceptance checklist. |
| 3 | `Documentation/01_Stark Gestures -- Rroduct Requirnment Documnent.md` | Product intent only. Several numbers/signs are outdated (click window, scroll sign, fail-safe, cursor point). Do not implement it literally. |

Exact paths contain typos (`Rroduct Requirnment Documnent`, doubled dashes). Use the real names above.

When docs disagree, doc 02/03 already state the resolution: click window **0.8 s**, cursor point **landmark 9**, scroll sign per camera coords, PyAutoGUI fail-safe **ON**. Do not re-litigate these.

## Build target

- One file: `stark_gestures.py` at repo root, sectioned exactly as doc 02 §2. Plus `requirements.txt` and `README.md` (doc 02 §12). No extra files, packages, modules, or features.
- The user asked for the full tool in one pass: build/fix the whole app directly instead of gating work by milestone. Still stop and let the user test after a substantial change.
- `DRY_RUN = False` is the current default because the user asked for a ready-to-use tool. Use `True` for safe practice runs.
- All tunable numbers live in the `CONFIG` block; no magic numbers elsewhere.

## Environment (Windows)

Python 3.15 is the system default and is **not** supported by the pinned MediaPipe. Python 3.12 is installed, and all packages are installed **system-wide** for it. There is no virtual environment: do not create or use `.venv`. Always invoke Python 3.12 as `py -3.12`.

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 -c "import cv2, mediapipe, pyautogui; print('ok')"
```

`requirements.txt`:

```
mediapipe==0.10.21
pyautogui>=0.9.54
```

- `py -3.12 --version` must say 3.12.x.
- **Do not add `opencv-python`** — MediaPipe bundles its own OpenCV; two copies fight over `import cv2`.
- If NumPy 2 errors appear: `py -3.12 -m pip install "numpy<2"`.
- Run: `py -3.12 stark_gestures.py`. There is no test runner or linter; the manual acceptance checklist in doc 03 §11 is the test plan, and doc 02 §13 has the tuning cheat-sheet.

## Architecture invariants

```
Camera (OpenCV) -> HandTracker (MediaPipe) -> GestureDetector (facts only)
  -> StateMachine (decisions only) -> CursorMapper/EMA -> ActionExecutor (PyAutoGUI only)
  -> Display (OpenCV overlays)
```

- The detector reports facts; the state machine decides; only `ActionExecutor` may call PyAutoGUI. Do not let other sections move the mouse.
- Cursor movement happens only in the pinch-hold move phase inside CURSOR mode.

## Non-obvious rules an agent will get wrong

- Mirror the frame first (`cv2.flip(frame, 1)`) or left/right feels reversed.
- Use **landmark 9** (middle-finger MCP) for cursor mapping, not index tip 8 (PRD says 8; doc 02 overrides).
- Measure all distances in "hand sizes" (`distance(0, 9)`), never raw pixels/normalized units.
- Pinch uses hysteresis: on `< 0.25`, off `> 0.40`, plus a guard that at least one of middle/ring/pinky is open (otherwise a fist reads as a pinch).
- Camera `y` grows **downward**: moving up gives negative `vy`; scroll signs are opposite the PRD.
- Cursor stays **frozen** for the first `CLICK_WINDOW` (0.8 s) of a pinch. Release before it = click; hold past it = move; release after = stop with no click.
- Keep `pyautogui.FAILSAFE = True` (the PRD says disable it; do not) and set `pyautogui.PAUSE = 0` (default 0.1 s causes lag).
- Webcam: `cv2.VideoCapture(index, cv2.CAP_DSHOW)` and `CAP_PROP_BUFFERSIZE = 1`.
- `q` only works while the preview window is focused. Ctrl+C, corner fail-safe, thumbs-down, and the no-hand timeout are the real exits.
- After any mode change apply `MODE_LOCKOUT` and require a non-fist frame before the next fist timer (prevents thumbs-down bouncing back to CURSOR).
- MVP maps to the primary monitor only; admin-elevated windows ignore synthetic input (Windows UIPI).

## Canonical timings (from CONFIG; change only in one block)

| Setting | Value |
|---|---|
| `FIST_HOLD_TIME` | 1.0 s |
| `THUMBS_DOWN_HOLD` | 0.4 s |
| `CLICK_WINDOW` | 0.8 s |
| `CLICK_COOLDOWN` | 0.3 s |
| `MODE_LOCKOUT` | 1.0 s |
| `HAND_LOST_GRACE` / `NO_HAND_TIMEOUT` | 0.3 s / 2.0 s |

Full defaults: doc 02 §8.

## Windows gotchas

- Camera permission: Settings -> Privacy & security -> Camera, including "Let desktop apps access your camera". Close Zoom/Teams/browser camera tabs.
- Use 640x480, not 1080p; `MODEL_COMPLEXITY = 0`, `MAX_HANDS = 1`.
- If the cursor lands in the wrong place, test at 100% display scaling.
