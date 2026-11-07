# Stark Gestures — Backend / Technical Architecture (MVP)

*A webcam gesture mouse. One Python file, runs fully on your laptop. Written for a beginner building in one day with OpenCode. Target: Windows.*

---

## 0. Read this first: your Python version

You have **Python 3.15.2**. That is newer than anything MediaPipe officially lists. The latest MediaPipe on PyPI (1.2.2, released Nov 3, 2026) lists support up to Python 3.14. I could not confirm that 3.15 works, and I could not confirm that the older, beginner-friendly `mp.solutions.hands` API still exists in the 1.x line.

**Recommendation (a one-day build cannot afford a surprise here):**

| Decision | Choice | Why |
| --- | --- | --- |
| Python for this project | **3.12**, installed *next to* 3.15 | MediaPipe has Windows wheels for 3.12 |
| MediaPipe version | **0.10.21** (pinned) | Known to have the simple `mp.solutions.hands` API and a 3.12 Windows wheel |
| Environment | A virtual environment ("venv") | Like a separate toolbox for this project. 3.15 stays untouched |

*Analogy: your Python 3.15 is a brand-new car engine. MediaPipe only has spare parts for older engines, so we borrow an older engine just for this project.*

---

## 1. Architecture overview

**Plain-language description.** The program is one loop. Every pass it grabs a camera picture, finds the 21 dots (landmarks) on your hand, asks "which gesture is this?", lets a small two-mode brain (NORMAL / CURSOR) decide what is allowed, and finally moves the mouse, clicks or scrolls. There is no server, no database, no login, no internet.

*Analogy: a security guard watching a camera. He ignores everything until he sees the secret signal (fist). After that he obeys a few simple hand signals until he sees the "stop" signal (thumbs down).*

```
  Camera frame (OpenCV)
          │
          ▼
  Hand Tracker (MediaPipe) ──► 21 landmarks (or "no hand")
          │
          ▼
  Gesture Detector ──► facts only: is_fist? is_pinched? thumbs_down? wave_dir?
          │
          ▼
  State Machine (NORMAL / CURSOR) ──► decides: move / click / scroll / switch mode
          │
          ▼
  Cursor Mapper + Smoother ──► screen x, y
          │
          ▼
  Action Executor (PyAutoGUI) ──► real cursor / click / scroll
          │
          ▼
  On-screen Display ──► preview window with mode + gesture text
```

**Golden rule:** the Gesture Detector only *reports facts*. The State Machine only *decides*. The Action Executor only *does*. Nothing else touches the mouse.

---

## 2. Module breakdown (single file, clear sections)

File: `stark_gestures.py`. Sections appear top-to-bottom in this order.

| # | Section / class | Single job | Inputs | Outputs |
| --- | --- | --- | --- | --- |
| 1 | `CONFIG` (constants block) | Hold every tunable number | none | constants |
| 2 | `Camera` | Open webcam, return one frame at a time, release on exit | camera index | BGR frame (mirrored) or error |
| 3 | `HandTracker` | Run MediaPipe Hands on a frame | frame | 21 landmarks (x, y in 0..1) or `None` |
| 4 | `GestureDetector` | Turn landmarks into yes/no facts and hand speed | landmarks, timestamp | `Facts` (see below) |
| 5 | `StateMachine` | Own the mode, the pinch timer, cooldowns; decide the action | `Facts`, time | list of `Action`s |
| 6 | `CursorMapper` | Camera point → screen point inside the active box, then smooth | landmark point | smoothed screen x, y |
| 7 | `ActionExecutor` | The only code that calls PyAutoGUI. Has a `DRY_RUN` switch | `Action` | real mouse effect (or a printed line) |
| 8 | `Display` | Draw landmarks, mode, gesture, hints in a preview window | frame, mode, facts | window; returns pressed key |
| 9 | `main()` | The loop that wires 2→8 together, plus safe exit | — | — |

**`Facts` (what the detector hands to the state machine):** `hand_present`, `is_fist`, `is_pinched`, `is_thumbs_down`, `wave` (`UP` / `DOWN` / `NONE`), `pointer_xy` (the point used to move the cursor).

**`Action` (what the state machine hands to the executor):** `MOVE(x, y)`, `CLICK`, `SCROLL(amount)`, `NONE`. Mode changes are shown on screen, not sent to PyAutoGUI.

---

## 3. Gesture detection logic

MediaPipe landmark numbers used (picture the hand, palm toward camera):

| No. | Point | No. | Point |
| --- | --- | --- | --- |
| 0 | Wrist | 9 | Middle-finger base knuckle (MCP) |
| 2 | Thumb knuckle (MCP) | 12 / 11 | Middle tip / middle middle-joint (PIP) |
| 4 | Thumb tip | 16 / 15 | Ring tip / ring PIP |
| 5 | Index base knuckle (MCP) | 20 / 19 | Pinky tip / pinky PIP |
| 8 / 7 | Index tip / index PIP |  |  |

**Rule zero: measure everything in "hand sizes", not pixels.** `hand_size = distance(landmark 0, landmark 9)` (wrist to middle knuckle). When your hand is close to the camera, it looks big; far away, small. Dividing by `hand_size` makes the thresholds work at any distance. *Analogy: measuring a shirt in "sleeve lengths" instead of centimetres, so it fits a child or an adult.*

**Helper: `is_curled(finger)`** — a finger is curled if its tip is **closer to the wrist than its middle joint (PIP) is**. `curled = distance(tip, 0) < distance(pip, 0)` This works even if your hand is tilted, because it uses distances, not up/down.

### 3.1 Fist

- **Rule:** index, middle, ring and pinky are all curled, **and** it is not a thumbs-down.
- **Thumb ignored on purpose:** the state machine only looks for a fist in NORMAL mode, so thumb position is not needed.
- Held for `FIST_HOLD_TIME` (1.0 s) → activate (see §4).

### 3.2 Pinch (thumb + index touching)

```
ratio = distance(4, 8) / hand_size
start pinch  when ratio < PINCH_ON    (0.25)
end pinch    when ratio > PINCH_OFF   (0.40)
```

- **Two thresholds ("hysteresis")** stop flicker. *Analogy: a thermostat that turns heat on at 18° and off at 21°, so it does not click on/off every second.*
- **Guard:** a pinch only counts if at least one of middle/ring/pinky is **not** curled. Why: in a fist, the thumb tip sits near the index tip and would look like a pinch. Tell the user: keep the other three fingers open, like an "OK" sign.

### 3.3 Quick pinch

Not a separate pose. It is the **same pinch**, judged by **how long it lasted** when released (see §6).

### 3.4 Wave up / wave down

Track the **palm point (landmark 9)**, not a fingertip. It is steadier.

```
keep the last ~0.2 s of (time, y) samples
vy = (y_now - y_oldest) / elapsed_seconds     # in "frame-heights per second"
In camera pictures y GROWS DOWNWARD, so:
   moving UP   → vy is NEGATIVE
   moving DOWN → vy is POSITIVE
wave = UP    if vy < -WAVE_SPEED
wave = DOWN  if vy > +WAVE_SPEED
ignore if vertical speed is not clearly bigger than sideways speed
```

Dead-zone / re-arm logic is in §7.

### 3.5 Thumbs down

All true at once:

1. Index, middle, ring, pinky are curled (a real thumbs-down is a closed fist with the thumb out).
2. Thumb is extended and pointing down: `(thumb_tip.y - landmark2.y) / hand_size > THUMB_DOWN_MIN` (0.5).
3. Thumb is mostly vertical: `abs(thumb_tip.y - landmark2.y) > abs(thumb_tip.x - landmark2.x)`.

Hold for `THUMBS_DOWN_HOLD` (0.4 s) before it counts.

---

## 4. State machine

```
                 fist held 1.0 s
      ┌────────────────────────────────────┐
      │                                    ▼
  [ NORMAL ]                          [ CURSOR ]
      ▲                                    │
      └──── thumbs-down held 0.4 s ────────┘
      ▲                                    │
      └──── no hand for 2.0 s (safety) ────┘
```

**Two sub-states inside CURSOR** (so pinch logic stays clean): `IDLE` and `PINCHING` (with a timer).

### Transition table

| From | Trigger | To | Side effect |
| --- | --- | --- | --- |
| NORMAL | Fist held ≥ `FIST_HOLD_TIME` (and re-armed, see below) | CURSOR | Show "CURSOR" banner, start lockout |
| CURSOR / IDLE | Pinch starts (stable ≥ `PINCH_DEBOUNCE`) | CURSOR / PINCHING | Record `pinch_start_time` |
| CURSOR / PINCHING | Pinch held longer than `CLICK_WINDOW` | stays PINCHING in **move** phase | Cursor follows hand |
| CURSOR / PINCHING | Pinch released within `CLICK_WINDOW` and cooldown over | CURSOR / IDLE | **Left click** |
| CURSOR / PINCHING | Pinch released after `CLICK_WINDOW` | CURSOR / IDLE | Stop moving, **no click** |
| CURSOR / IDLE | Wave UP or DOWN and scroll cooldown over | stays | Scroll |
| CURSOR (any) | Thumbs-down held ≥ `THUMBS_DOWN_HOLD` | NORMAL | Cancel any pinch, no click |
| CURSOR (any) | Hand lost > `HAND_LOST_GRACE` while pinching | CURSOR / IDLE | Cancel pinch, **no click** |
| CURSOR (any) | No hand for `NO_HAND_TIMEOUT` | NORMAL | Safety fallback |
| any | Safe-exit key | quit | Release camera, close window |

### What each state ignores

| State | Reacts to | Ignores |
| --- | --- | --- |
| NORMAL | Fist only | Pinch, wave, thumbs-down, all mouse output |
| CURSOR / IDLE | Pinch start, wave, thumbs-down | Fist |
| CURSOR / PINCHING | Pinch release, thumbs-down | Fist, wave (no scrolling while pinching) |

**Re-arm and lockout (my addition).** After any mode change, ignore mode gestures for `MODE_LOCKOUT` (1.0 s), and require at least one frame of a *non-fist* hand before the next fist timer starts. Why: after a thumbs-down, your hand is still in a fist-like shape. Without this, it could flip straight back to CURSOR.

---

## 5. Cursor mapping

### 5.1 Which point moves the cursor

Use **landmark 9 (middle-finger base knuckle)**. *Differs from the PRD, which uses the index tip (8).* Reason: when you pinch, the fingertip itself moves. That makes the cursor wobble exactly when you start or end a click. The knuckle barely moves during a pinch.

### 5.2 Mirror the picture

Flip the camera frame left-right (`cv2.flip(frame, 1)`) before anything else, so moving your hand right moves the cursor right. *Like a bathroom mirror. The PRD does not mention this, but without it the cursor feels backwards.*

### 5.3 The "active box"

Only the middle part of the camera picture is used, so you can reach every screen edge without your hand leaving the camera view.

```
  Camera frame (0..1)
  ┌─────────────────────────┐
  │   margin = 10%          │
  │   ┌─────────────────┐   │
  │   │   ACTIVE BOX    │   │  ← hand inside here covers the whole screen
  │   │  (10%–90%)      │   │
  │   └─────────────────┘   │
  └─────────────────────────┘
```

```
nx = clamp((x - MARGIN) / (1 - 2*MARGIN), 0, 1)
ny = clamp((y - MARGIN) / (1 - 2*MARGIN), 0, 1)
screen_x = nx * (screen_width  - 1)
screen_y = ny * (screen_height - 1)
# then clamp to EDGE_PADDING_PX (5 px) from each edge, so it never touches a corner
```

### 5.4 Smoothing: Exponential Moving Average (EMA) — recommended

```
smooth = ALPHA * new + (1 - ALPHA) * smooth        # ALPHA = 0.25
```

**Why this one for a beginner:** it is one line, needs no history list, and has one dial. *Analogy: a heavy shopping trolley. You push, it follows, but small shaky nudges do not make it zigzag.* Lower ALPHA = smoother but laggier; higher = snappier but shakier.

A moving average of the last N points also works, but it needs a list and lags more for the same smoothness.

### 5.5 The "teleport" problem and the fix

With absolute mapping, the cursor would jump from where it was to where your hand maps the moment you start moving. **Fix:** when a move phase begins, set `smooth` to the **current real cursor position**. The EMA then glides the cursor to your hand over \~0.3 s instead of teleporting. *(Optional V2: "clutch / relative" mode, like lifting a mouse and putting it back.)*

---

## 6. Click vs move separation

The trap: a quick click and a move both start with the same pinch. The solution is simple: **do not move during the click window**.

```
Timeline of one pinch

t0 pinch starts ─────── t0 + CLICK_WINDOW ─────────────► time
   │ cursor FROZEN        │ cursor FOLLOWS the hand
   │ release here = CLICK │ release here = just stop (no click)
```

**Exact rules**

1. **Debounce start:** pinch must read "pinched" for `PINCH_DEBOUNCE` (0.05 s, about 2 frames) before the timer starts. One bad frame never starts a pinch.
2. **Debounce release:** same idea, release must be stable for 2 frames. (The two-threshold hysteresis in §3.2 already does most of this.)
3. **On release:** `duration = now - pinch_start_time`. If `duration <= CLICK_WINDOW` **and** `now - last_click_time >= CLICK_COOLDOWN` → send one left click at the **current** cursor position.
4. **If `duration > CLICK_WINDOW`** → it was a hold. No click.
5. **Cooldown:** after a click, ignore new clicks for `CLICK_COOLDOWN` (0.30 s). Prevents one sloppy pinch from firing twice.
6. **Never click while thumbs-down, hand lost, or mode changed.**

**PRD differences:**

- The PRD says click window 0.7 s; your brief says "about 1 s". I set **0.8 s** as a middle value. It is one number, so change it freely.
- The PRD says to start moving "as soon as pinch is detected". That would nudge the cursor during every click and miss small targets. I wait until the click window passes.

---

## 7. Scroll logic

**Measuring speed:** see §3.4. Speed is in **frame-heights per second** (1.0 means "crossed the whole picture height in one second"). The PRD used "per frame" units, which change when the frame rate changes. Per-second does not.

**State of the scroll detector:** `ARMED` or `WAITING_FOR_CALM`.

```
if ARMED and wave detected and scroll cooldown over:
      send scroll (up or down), remember time, state = WAITING_FOR_CALM
if WAITING_FOR_CALM and abs(vy) < WAVE_DEADZONE:
      state = ARMED          # the hand has calmed down: next wave allowed
```

| Term | Meaning | Default |
| --- | --- | --- |
| Wave speed | Minimum speed to count as a wave | 1.0 frame-heights/s |
| Dead zone | Speed must fall below this before the next wave | 0.3 frame-heights/s |
| Scroll cooldown | Minimum time between scrolls | 0.4 s |
| Scroll amount | Wheel units per wave. On Windows, \~120 ≈ one wheel notch | 200 |

- Wave UP → `pyautogui.scroll(+SCROLL_AMOUNT)` (positive = up).
- Wave DOWN → `pyautogui.scroll(-SCROLL_AMOUNT)`.
- *Why the dead zone:* returning your hand to the start position is also a movement (the opposite direction). The dead zone and cooldown stop that "return swing" from scrolling back.
- Ignore waves while pinching, so moving the cursor never scrolls the page.

---

## 8. Configuration table

All values live in one `CONFIG` block at the top of the file. Edit only there.

| Name | Default | What it does |
| --- | --- | --- |
| `CAMERA_INDEX` | 0 | Which camera. Try 1 if 0 fails |
| `FRAME_WIDTH` / `FRAME_HEIGHT` | 640 / 480 | Camera resolution. Lower = faster |
| `MIRROR` | True | Flip picture so movement feels natural |
| `MAX_HANDS` | 1 | Only one hand is tracked |
| `MODEL_COMPLEXITY` | 0 | MediaPipe "lite" model. Faster, good enough |
| `MIN_DETECT_CONF` / `MIN_TRACK_CONF` | 0.7 / 0.6 | How sure MediaPipe must be before it reports a hand |
| `PINCH_ON` | 0.25 | Thumb-index gap (in hand sizes) that starts a pinch |
| `PINCH_OFF` | 0.40 | Gap that ends a pinch (bigger than ON = no flicker) |
| `PINCH_DEBOUNCE` | 0.05 s | Pinch must be stable this long before it counts |
| `FIST_HOLD_TIME` | 1.0 s | How long to hold a fist to enter CURSOR |
| `THUMBS_DOWN_HOLD` | 0.4 s | How long to hold thumbs-down to leave CURSOR |
| `THUMB_DOWN_MIN` | 0.5 | How far below its knuckle the thumb tip must point |
| `MODE_LOCKOUT` | 1.0 s | Ignore mode gestures after a mode change |
| `CLICK_WINDOW` | 0.8 s | Longest pinch that still counts as a click |
| `CLICK_COOLDOWN` | 0.3 s | Minimum gap between clicks |
| `ACTIVE_BOX_MARGIN` | 0.10 | Ignored border (10%) of the camera frame |
| `SMOOTHING_ALPHA` | 0.25 | Smoothing strength (lower = smoother, laggier) |
| `EDGE_PADDING_PX` | 5 | Keeps the cursor off exact screen corners |
| `MAX_STEP_PX` | 150 | Biggest allowed cursor jump per frame (anti-runaway) |
| `WAVE_SPEED` | 1.0 | Hand speed needed to count as a wave |
| `WAVE_DEADZONE` | 0.3 | Speed below this re-arms the next wave |
| `WAVE_WINDOW` | 0.2 s | Time span used to measure speed |
| `SCROLL_AMOUNT` | 200 | How far each wave scrolls |
| `SCROLL_COOLDOWN` | 0.4 s | Minimum gap between scrolls |
| `HAND_LOST_GRACE` | 0.3 s | How long a missing hand is tolerated mid-pinch |
| `NO_HAND_TIMEOUT` | 2.0 s | No hand this long in CURSOR → back to NORMAL |
| `EXIT_KEY` | `"q"` | Quit key (preview window must be focused) |
| `DRY_RUN` | True at first | Print actions instead of moving the real mouse |
| `SHOW_PREVIEW` | True | Show the camera window with overlays |

---

## 9. Error handling and safety

| Situation | What the program does |
| --- | --- |
| **Camera not found / busy** | `isOpened()` is False or first read fails → print one clear message ("Camera not found. Close Zoom/Teams, check Windows camera privacy, try `CAMERA_INDEX = 1`") and exit cleanly. No crash trace |
| **Camera stops mid-run** | A failed frame read 30 times in a row → exit cleanly |
| **No hand detected** | Facts say `hand_present = False`. No action is sent. Display shows "No hand" |
| **Hand lost mid-pinch** | Wait `HAND_LOST_GRACE`. If it returns, continue. If not, cancel the pinch with **no click** and **no cursor move** |
| **Hand lost for long (CURSOR)** | After `NO_HAND_TIMEOUT` → NORMAL |
| **PyAutoGUI fail-safe** | **Keep it ON** (`pyautogui.FAILSAFE = True`). Slam the real mouse into any screen corner and PyAutoGUI raises an exception. Catch it in `main()` and exit cleanly. *The PRD suggests turning it off. I recommend the opposite: it is your emergency brake.* Because we keep the cursor 5 px from corners, our own code never trips it by accident |
| **Safe exit key `q`** | Checked every loop via `cv2.waitKey(1)` |
| **Runaway cursor** | (1) Cursor only moves in the pinch-hold move phase. (2) `MAX_STEP_PX` caps jumps per frame. (3) A frame where landmarks teleport is dropped. (4) Cursor never moves with no hand. (5) `DRY_RUN` for first tests |
| **Any other crash** | `try/finally` always releases the camera and closes windows |

**Important catch about the `q` key.** `cv2.waitKey` only hears keys when the **preview window has focus**. Once CURSOR mode clicks other windows, the preview loses focus and `q` stops working. So you need backups:

1. **Ctrl+C in the terminal** (always works).
2. **Mouse-to-corner fail-safe** (above).
3. **Optional global Esc key** that works from any window, with no extra install, using `ctypes.windll.user32.GetAsyncKeyState(0x1B)` (Windows only).
4. **Thumbs-down** and the **no-hand timeout** both return to NORMAL.

---

## 10. Performance notes

| Item | Target |
| --- | --- |
| Frame rate | 30 fps goal, 15 fps acceptable. Gestures need ≥ 10 fps |
| Latency (hand moves → cursor moves) | Under 100 ms |
| CPU | About 15–25% on a modern laptop (PRD estimate) |

**Tips**

- Camera at **640×480**. Do not use 1080p.
- `MODEL_COMPLEXITY = 0`, `MAX_HANDS = 1`.
- On Windows open the camera with `cv2.VideoCapture(index, cv2.CAP_DSHOW)`: faster start-up.
- Set the camera buffer to 1 frame (`CAP_PROP_BUFFERSIZE`) so you never process old pictures. *Analogy: always read today's newspaper, not the pile from last week.*
- **Set `pyautogui.PAUSE = 0`.** PyAutoGUI waits 0.1 s after every call by default. At 30 calls per second this alone causes bad lag. The PRD misses this.
- Mark the frame read-only before passing it to MediaPipe (`frame.flags.writeable = False`) and convert BGR→RGB once.
- Draw overlays only if `SHOW_PREVIEW`. Drawing is cheap, but not free.
- If CPU is still high: lower FPS by processing every 2nd frame (Optional).

---

## 11. Dependencies and setup (Windows)

**Step A: install Python 3.12 next to 3.15.** Either download it from python.org (tick "Add to PATH" is not needed if you use the `py` launcher), or run:

```
winget install Python.Python.3.12
```

**Step B: create the project environment** (in PowerShell, inside the project folder):

```
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python --version          # must say 3.12.x
pip install -r requirements.txt
```

If PowerShell blocks the activate script, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or use `.venv\Scripts\activate.bat` in Command Prompt.

**`requirements.txt`**

```
mediapipe==0.10.21
pyautogui>=0.9.54
```

- MediaPipe installs its own OpenCV automatically. **Do not also `pip install opencv-python`**: two OpenCV packages can fight over `import cv2`.
- If you see an error mentioning NumPy 2, run `pip install "numpy<2"`.
- First check: `python -c "import cv2, mediapipe, pyautogui; print('ok')"`.

**Windows notes**

| Topic | What to do |
| --- | --- |
| Camera permission | Settings → Privacy & security → Camera → turn on camera access and **"Let desktop apps access your camera"** |
| Camera in use | Close Zoom, Teams, Meet, browser tabs using the camera |
| Mouse control | No special permission for normal windows |
| Admin windows | Task Manager and other "Run as administrator" windows will **ignore** the fake mouse. That is Windows security (UIPI). Run the terminal as administrator only if you truly need this |
| Antivirus / SmartScreen | May warn about a script controlling the mouse. Allow it if it is your own script |
| Display scaling | If the cursor lands in the wrong place, test at 100% scaling (Settings → System → Display) |
| Multiple monitors | MVP maps to the **primary** monitor only |

---

## 12. File and folder structure

```
stark-gestures/
├── stark_gestures.py     # the whole program (sections from §2)
├── requirements.txt      # from §11
├── README.md             # how to install and run, gesture cheat-sheet
└── .venv/                # created by you, never edited by hand
```

Run it: `python stark_gestures.py`

---

## 13. Build order for OpenCode

**Rules to paste at the top of every OpenCode prompt:**

1. Single file `stark_gestures.py`. Do not add files, packages or features not listed.
2. All tunable numbers live in the `CONFIG` block. No magic numbers elsewhere.
3. Build **only the milestone I name**. Stop and wait for me to test.
4. Keep `DRY_RUN = True` until I say otherwise.
5. Keep functions short, with a one-line comment explaining each.

| # | Milestone | Build | How to test it works |
| --- | --- | --- | --- |
| 0 | Setup | venv, `requirements.txt`, import check | `python -c "import cv2, mediapipe, pyautogui; print('ok')"` prints `ok`; `python --version` says 3.12 |
| 1 | Camera + exit | `Camera`, preview window, mirror, `q` to quit, camera-not-found message | Live mirrored video appears. `q` closes it. Cover/unplug camera or set `CAMERA_INDEX = 9`: you get the friendly message, not a crash |
| 2 | Landmarks | `HandTracker`, draw the 21 points | Dots and lines follow your hand. Hand out of view → "No hand" text |
| 3 | Measurements HUD | `hand_size`, pinch ratio, curled-finger flags shown as live numbers | Pinch: ratio falls below 0.25. Open hand: ratio is well above 0.4. Make a fist: four "curled" flags turn True. Note your real values to tune later |
| 4 | Gesture facts | `GestureDetector`: fist, pinch (with hysteresis and guard), thumbs-down, wave | HUD text names each gesture only when you do it. Wave shows UP/DOWN once per wave. Fist and thumbs-down are never confused |
| 5 | State machine (no mouse) | `StateMachine` with timers, lockout, re-arm, hand-lost rules; print actions | Fist 1 s → "CURSOR". Quick pinch prints `CLICK`. Long pinch prints `MOVE` lines, no click on release. Thumbs-down → "NORMAL". In NORMAL nothing prints |
| 6 | Cursor mapping | `CursorMapper`: active box, EMA, edge padding, step cap | Debug dot on the preview moves smoothly and reaches all four edges with your hand inside the box. No jumps |
| 7 | Real mouse: move | `ActionExecutor` with `PAUSE = 0`, `FAILSAFE = True`; set `DRY_RUN = False` | Pinch-hold moves the real cursor; release stops it; it glides rather than teleports. Slam the mouse to a corner: program exits cleanly |
| 8 | Real mouse: click | Enable click on quick pinch | Open Notepad and a folder: quick pinch selects an icon. Hold longer: no click. Fast double pinch gives two clicks about 0.3 s apart, never accidental extras |
| 9 | Scroll | Enable wave scroll with dead zone and cooldown | Open a long web page: wave up scrolls up once, wave down scrolls down once. Hand drifting slowly does nothing. Return swing does not scroll back |
| 10 | Safety pass | Hand-lost grace, no-hand timeout, `try/finally`, optional global Esc | Hide your hand mid-pinch: no click, no jump. Hide it for 2 s in CURSOR: back to NORMAL. Ctrl+C always stops it |
| 11 | Tune and polish | Adjust CONFIG values with the checklist below. Write README cheat-sheet | Run the full flow 10 times in a row with no accidental click, scroll or mode change |

**Tuning cheat-sheet**

| Problem | Change |
| --- | --- |
| Cursor shaky | Lower `SMOOTHING_ALPHA` (0.15) |
| Cursor laggy | Raise `SMOOTHING_ALPHA` (0.4) |
| Can't reach screen edges | Raise `ACTIVE_BOX_MARGIN` (0.15) |
| Pinch missed | Raise `PINCH_ON` (0.30) |
| Accidental pinches | Lower `PINCH_ON` (0.20) |
| Fist triggers by accident | Raise `FIST_HOLD_TIME` (1.3 s) |
| Scrolls too easily | Raise `WAVE_SPEED` (1.4) |
| Scroll never fires | Lower `WAVE_SPEED` (0.7) |

---

## 14. Known limitations and future improvements

**Known limitations (MVP)**

- Needs decent, even lighting. Dark rooms and bright windows behind you cause lost tracking.
- One hand only. Works with either hand, but the guide assumes your dominant hand.
- Palm should roughly face the camera. Edge-on or back-of-hand views confuse the rules.
- "Gorilla arm": holding an arm up gets tiring. Rest your elbow on the desk and move mostly the wrist and forearm.
- Cursor precision is low (small icons are hard). This is a limit of webcam tracking.
- Primary monitor only. Elevated (admin) windows ignore it.
- Thresholds are tuned for one person's hand and camera. Expect to adjust.
- The preview window `q` key only works while the window is focused (backups in §9).

**V2 ideas (NOT part of the MVP)**

- Right-click gesture (thumb + middle pinch).
- Real drag-and-drop with mouse-down / mouse-up.
- Double-click gesture.
- Relative "clutch" cursor mode instead of absolute mapping.
- Left/right hand auto-detection and mirroring.
- Multi-monitor support.
- Transparent always-on-top HUD overlay.
- Config file or small settings window (instead of editing the top of the code).
- Calibration step ("show me a fist, a pinch") that sets thresholds for you.
- Small ML model trained on your own landmarks to replace hand-written rules.
- Global hotkey library for pause/resume.

---

## Appendix: where this document differs from the PRD

| Topic | PRD says | This document | Why |
| --- | --- | --- | --- |
| Click window | 0.7 s | 0.8 s | Between PRD (0.7) and your brief (\~1 s). One number to change |
| Start of movement | As soon as pinch is detected | After the click window | Stops quick clicks nudging the cursor |
| Cursor point | Index tip (8) | Middle knuckle (9) | Does not wobble when you pinch |
| Distance units | Raw normalized (0.04) | In "hand sizes" with two thresholds | Works at any distance, no flicker |
| Scroll direction maths | `y_now − y_prev` positive = up | Positive = **down** (camera y grows downward) | The PRD's sign is backwards for camera coordinates |
| Scroll speed units | Per frame | Per second | Frame rate varies, seconds do not |
| Thumbs-down | Thumb down with fingers open | Fingers curled, thumb out and down | Matches how people really make a thumbs-down |
| PyAutoGUI fail-safe | Disable it | Keep it ON | It is the emergency brake |
| Mirroring | Not mentioned | Flip frame horizontally | Otherwise left/right feels reversed |
| Frame delay | `sleep(0.01)` | `pyautogui.PAUSE = 0` | Default 0.1 s pause per call causes lag |
| Mode switching | Simple | Lockout + re-arm after each switch | Stops accidental bounce back to CURSOR |
