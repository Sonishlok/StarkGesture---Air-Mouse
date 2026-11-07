# Stark Gestures — Air Mouse

Webcam hand-gesture mouse for Windows. One Python file, runs fully on your laptop: no server, no database, no internet.

> Status: implemented in a single file (`stark_gestures.py`). There is no test runner or CI; the manual checklist is doc 03 §11.

## Requirements

- Windows
- Python 3.12, via the `py -3.12` launcher
- A webcam

No virtual environment is used. Packages are installed system-wide for Python 3.12.

## Setup

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 -c "import cv2, mediapipe, pyautogui; print('ok')"
```

The second command must print `ok`.

MediaPipe supplies its own OpenCV. Do not install a second OpenCV package such as `opencv-python`; two copies can fight over `import cv2`. If NumPy 2 errors appear, run `py -3.12 -m pip install "numpy<2"`.

## Run

```powershell
py -3.12 stark_gestures.py
```

`DRY_RUN = False` is the default: gestures control the real mouse. For a safe practice run, set `DRY_RUN = True` in the `CONFIG` block; actions are then printed instead of performed.

## Gestures

| Gesture | How to do it | What it does | Works in |
| --- | --- | --- | --- |
| Fist hold | Close all fingers, hold 1 second | Turns CURSOR mode ON | NORMAL |
| Pinch hold | Thumb + index touch, other 3 fingers open, hold over 0.8 s | Cursor follows your hand; release to stop | CURSOR |
| Quick pinch | Thumb + index touch, let go in under 0.8 s | Left click | CURSOR |
| Wave up | Swing your hand up fast, then rest | Scroll up one step | CURSOR |
| Wave down | Swing your hand down fast, then rest | Scroll down one step | CURSOR |
| Thumbs-down | Fist with thumb pointing down, hold 0.4 s | Turns CURSOR mode OFF | CURSOR |

Modes: **NORMAL** (gray label) ignores everything except a fist. **CURSOR** (green label) enables pinch, scroll and thumbs-down.

## Exit

- Click the camera window and press `q`.
- Press `Ctrl+C` in the terminal.
- Slam the real mouse into a screen corner (PyAutoGUI fail-safe).
- Thumbs-down or 2 seconds with no hand returns CURSOR to NORMAL.

## Troubleshooting

- Camera not found: close Zoom/Teams/browser camera tabs, then check Settings -> Privacy & security -> Camera, including "Let desktop apps access your camera".
- Keep the camera at 640x480, use even lighting, and keep one hand in view with the palm facing the camera.
- If the cursor lands in the wrong place, test at 100% display scaling.
