# Stark Gestures — App Flow Document (MVP)

*How a person starts the tool, switches modes with hand gestures, controls the cursor, and exits. One camera window, no menus, no settings. Built from the PRD and the Backend / Technical Architecture doc. Target: Windows, one-day build with OpenCode.*

**Numbers used in this document** come from the backend doc's CONFIG block: fist hold 1.0 s, thumbs-down hold 0.4 s, click window 0.8 s, mode lockout 1.0 s, hand-lost grace 0.3 s, no-hand timeout 2.0 s. Change them in one place (CONFIG) and this document still holds.

---

## 1. Flow overview (one full session)

You open a terminal and run `python stark_gestures.py`. The terminal prints a short list of gestures, and a camera window opens showing you like a mirror. A gray label says **NORMAL**. In this mode the program is asleep: it watches your hand but touches nothing.

You raise your hand and make a **fist**. A ring fills up over one second. When it is full, the label turns green and says **CURSOR**. The program is now awake.

You open your hand into an "OK" sign and **pinch** quickly. A white flash appears and your computer does a left click. Next you pinch and **hold**. The pinch dot turns from orange to green and the real cursor glides after your hand. You let go and it stops. You **wave** your hand up and the page scrolls up one step, then wave down and it scrolls down.

When you are done controlling the mouse, you make a **thumbs-down**. The label goes back to gray **NORMAL**. Finally you click the camera window and press **q**. The window closes and the camera light turns off.

*Analogy: a security guard who ignores everything until he sees the secret signal (fist). After that he obeys a few hand signals until he sees the stop signal (thumbs-down).*

---

## 2. Main user journey

| # | User does | Program detects | Program does | User sees |
| --- | --- | --- | --- | --- |
| 1 | Runs `python stark_gestures.py` | Nothing yet | Opens camera, prints the gesture list in the terminal, opens the window | Mirrored camera picture, gray **NORMAL** label, help panel, **DRY RUN** badge if on |
| 2 | Raises one hand, palm open | Hand present, not a fist | Draws hand dots. No mouse output | 21 dots on the hand, label still **NORMAL** |
| 3 | Closes hand into a fist and holds | 4 fingers curled, not a thumbs-down | Starts the 1.0 s fist timer | Yellow ring fills clockwise |
| 4 | Keeps holding the fist for 1.0 s | Timer reaches 1.0 s | Mode becomes CURSOR, 1 s lockout begins | Ring completes, label turns green **CURSOR**, help panel hides |
| 5 | Relaxes hand into an open "OK" shape | Non-fist hand (this also re-arms the fist) | Waits for a gesture | Label stays **CURSOR** |
| 6 | Quick pinch: thumb and index touch, then let go within 0.8 s | Pinch starts, then ends under 0.8 s, click cooldown over | One left click at the current cursor spot | Pinch dot orange, then white **CLICK** flash |
| 7 | Pinch and keep holding past 0.8 s | Pinch longer than the click window | Cursor starts gliding to the hand and follows it | Pinch dot turns green, text **MOVING** |
| 8 | Moves the pinched hand, then opens the pinch | Pinch released after a hold | Cursor stops. No click | Dot disappears |
| 9 | Waves hand quickly **up** (not pinching) | Upward speed above the wave limit | Scrolls up one step | Arrow ▲ near the hand |
| 10 | Waves hand quickly **down** | Downward speed above the wave limit | Scrolls down one step | Arrow ▼ near the hand |
| 11 | Makes a thumbs-down and holds 0.4 s | Fist-like hand, thumb out and pointing down | Mode becomes NORMAL, any pinch cancelled | Label turns gray **NORMAL** |
| 12 | Clicks the camera window, presses **q** | Key "q" | Releases camera, closes window | Window closes, terminal says "Stopped." |

---

## 3. Flow diagram

```
  python stark_gestures.py
            │
            ▼
   Camera opens OK? ──no──► friendly message ──► EXIT
            │ yes
            ▼
 ┌──────────────────────────┐
 │         NORMAL           │  Only a fist is noticed.
 │  (gray label)            │  Pinch, wave, thumbs-down = ignored.
 └──────────────────────────┘
            │ fist held 1.0 s
            ▼
 ┌────────────────────────────────────────────────────────┐
 │                      CURSOR  (green label)             │
 │                                                        │
 │   ┌──────────┐   pinch (stable 0.05 s)  ┌────────────┐ │
 │   │   IDLE   │ ───────────────────────► │  PINCHING  │ │
 │   │          │ ◄─────────────────────── │            │ │
 │   └──────────┘   release                │ 0–0.8 s:   │ │
 │     │                                   │  cursor    │ │
 │     │ wave up / down                    │  FROZEN    │ │
 │     ▼                                   │ after 0.8s:│ │
 │   scroll one step                       │  cursor    │ │
 │   (then wait for calm hand)             │  MOVES     │ │
 │                                         └────────────┘ │
 │   Release before 0.8 s  = LEFT CLICK                   │
 │   Release after  0.8 s  = just stop (no click)         │
 └────────────────────────────────────────────────────────┘
      │ thumbs-down held 0.4 s            │ no hand for 2.0 s
      └──────────────► NORMAL ◄───────────┘

  Press q (window focused) / Ctrl+C / mouse into a screen corner
  / camera lost ─────────────────────────────────────────► EXIT
```

---

## 4. Gesture-by-gesture flow

### 4.1 Fist hold (NORMAL → CURSOR)

| Part | What happens |
| --- | --- |
| Trigger | Index, middle, ring and pinky all curled, and it is not a thumbs-down. Works only in NORMAL |
| Confirmation | Held 1.0 s while the ring fills |
| Result | Mode becomes CURSOR. Green label. 1 s lockout so the next gestures are not read by mistake |
| If interrupted | Hand opens, leaves the picture, or turns into a thumbs-down before 1.0 s: the timer resets to zero and the ring empties. Nothing else happens. The next try needs a new full 1.0 s |

### 4.2 Pinch hold (cursor follows the hand)

| Part | What happens |
| --- | --- |
| Trigger | Thumb tip and index tip touch while at least one of middle, ring or pinky stays open (like an "OK" sign). Works only in CURSOR |
| Confirmation | Pinch is stable for 0.05 s, then kept for more than 0.8 s. Until 0.8 s the cursor stays frozen |
| Result | Cursor glides to the hand, then follows it. Release stops it. No click |
| If interrupted | Released before 0.8 s: this becomes a click (see 4.3). Hand lost: wait 0.3 s, then cancel with no click and no jump. Thumbs-down: cancel and go to NORMAL |

### 4.3 Quick pinch (left click)

| Part | What happens |
| --- | --- |
| Trigger | The same pinch as 4.2, released fast |
| Confirmation | Release happens within 0.8 s of the pinch start, and at least 0.3 s since the last click |
| Result | One left click at the cursor's current position |
| If interrupted | Hand disappears or thumbs-down appears first: no click. Second pinch within 0.3 s of a click: the click is skipped (cooldown) |

*Analogy: tapping a light switch (quick tap = click) versus holding it down (hold = move).*

### 4.4 Wave up / wave down (scroll)

| Part | What happens |
| --- | --- |
| Trigger | Palm moves clearly more up/down than sideways, faster than the wave limit, while not pinching. Works only in CURSOR |
| Confirmation | Speed is measured over the last 0.2 s. After a scroll, the hand must calm down before the next wave counts, and 0.4 s must pass |
| Result | One scroll step in that direction (up or down) |
| If interrupted | Too slow, mostly sideways, or stopped halfway: nothing happens. The swing back to start does not scroll in the other direction, because the program waits for a calm hand |

### 4.5 Thumbs-down (CURSOR → NORMAL)

| Part | What happens |
| --- | --- |
| Trigger | Four fingers curled like a fist, thumb stuck out and pointing down. Works only in CURSOR |
| Confirmation | Held 0.4 s |
| Result | Mode becomes NORMAL. Any pinch is cancelled with no click. 1 s lockout |
| If interrupted | Thumb rises or hand leaves before 0.4 s: stays in CURSOR. The program also needs one non-fist frame before it will read a new fist, so you do not bounce straight back into CURSOR |

---

## 5. Mode transition table

| Current mode | Gesture or event | Next mode | What is ignored |
| --- | --- | --- | --- |
| NORMAL | Fist held 1.0 s (after lockout and re-arm) | CURSOR | Pinch, wave, thumbs-down, all mouse output |
| NORMAL | Anything else | NORMAL | Everything except a fist |
| CURSOR / IDLE | Pinch (stable 0.05 s) | CURSOR / PINCHING | Fist |
| CURSOR / IDLE | Wave up or down (cooldown over) | CURSOR / IDLE (one scroll) | Fist |
| CURSOR / PINCHING | Release within 0.8 s | CURSOR / IDLE (one click) | Fist, wave |
| CURSOR / PINCHING | Release after 0.8 s | CURSOR / IDLE (stop moving, no click) | Fist, wave |
| CURSOR (any) | Thumbs-down held 0.4 s | NORMAL | Mode gestures during the 1 s lockout |
| CURSOR (any) | No hand for 2.0 s | NORMAL (safety) | — |
| CURSOR / PINCHING | Hand lost over 0.3 s | CURSOR / IDLE (no click) | Cursor movement |
| Any mode | q, Ctrl+C, corner fail-safe, camera lost | EXIT | — |

---

## 6. On-screen feedback design

Everything is drawn on the camera window with OpenCV. **Colors are BGR in OpenCV** (Blue, Green, Red), not RGB. The tuples below are ready to paste.

| Element | Appears when | Color and text |
| --- | --- | --- |
| Mode label (top-left, big) | Always | NORMAL: gray `(160,160,160)`, text "NORMAL". CURSOR: green `(0,200,0)`, text "CURSOR" |
| Hand dots and lines | A hand is in view | White dots, thin green lines, drawn on the hand |
| Fist-hold progress ring | NORMAL, while a fist is held | Yellow `(0,255,255)` ring around the wrist, fills 0 → 100% in 1.0 s. Disappears if the fist breaks |
| Pinch indicator | CURSOR, while pinching | Dot at thumb+index. Orange `(0,165,255)` and text "PINCH" during the first 0.8 s. Green `(0,200,0)` and text "MOVING" after that |
| Click flash | The moment a click is sent | Large white circle at the pinch point with text "CLICK", visible for about 0.3 s |
| Scroll arrow | The moment a scroll is sent | Cyan `(255,255,0)` arrow ▲ or ▼ beside the hand, visible for about 0.4 s |
| "No hand" text | No hand detected | Small red `(0,0,255)` text "No hand" at the top |
| DRY RUN badge | `DRY_RUN` is True | Small red box "DRY RUN: mouse not moving" at the bottom |
| Help panel | First 15 s of the session, or until the first switch to CURSOR | Semi-transparent dark box listing the 5 gestures (see §8) |

---

## 7. Edge-case flows

| Situation | What the program does | What the user sees |
| --- | --- | --- |
| **No hand in view** | `hand_present = False`. No action is sent. Fist timer resets. In CURSOR, after 2.0 s of no hand, switch to NORMAL | "No hand" text. After 2 s in CURSOR the label turns gray |
| **Hand leaves frame mid-pinch** | Wait 0.3 s. If the hand returns, carry on. If not, cancel the pinch with **no click** and **no cursor jump**, back to CURSOR/IDLE | "No hand", pinch dot disappears |
| **Accidental fist** | In NORMAL: under 1 s does nothing (ring empties). Over 1 s enters CURSOR, which is harmless until you pinch. In CURSOR: a fist is ignored. To undo: thumbs-down, or hide your hand for 2 s | Ring fills, label turns green. Thumbs-down turns it gray again |
| **Two hands in view** | The tracker follows one hand only (`MAX_HANDS = 1`) and the program treats whatever it reports as "the hand". Keep the other hand down. If the tracked hand switches, the sudden jump is dropped by the step cap, so the cursor does not teleport | Dots on one hand |
| **Poor lighting** | MediaPipe loses the hand. Treated as "No hand" (no clicks, no moves). Safety timeout applies in CURSOR | "No hand" text. Optional: after 3 s add "Can't see your hand. Turn on a light, avoid a bright window behind you" |
| **Camera not found or busy** | Prints one clear message and exits cleanly, no crash trace | Terminal: "Camera not found. Close Zoom/Teams, check Windows camera privacy, try CAMERA\_INDEX = 1" |
| **Wave too slow** | Nothing happens. This is on purpose, so slow hand drift never scrolls | No arrow appears. Tip: wave faster, or lower `WAVE_SPEED` |
| **Click and move confusion** | Cursor stays frozen for the first 0.8 s of every pinch. Release in that time = click, no movement. Holding longer = move, no click | Orange "PINCH" while frozen, green "MOVING" once it follows |
| **Wave while pinching** | Ignored, so moving the cursor never scrolls the page | No arrow |
| **Double pinch too fast** | Second click skipped if under 0.3 s after the first | One flash only |
| **Fist right after thumbs-down** | Ignored until the 1 s lockout ends and one non-fist frame is seen | Label stays gray |

---

## 8. First-run flow

Keep it very simple: **two helpers, both automatic**.

**Helper 1: terminal printout** (printed once at startup, right after the camera opens):

```
STARK GESTURES: hand gesture mouse
  1. FIST, hold 1 sec ........ turn ON (CURSOR mode)
  2. PINCH, quick ............ left click
  3. PINCH, hold ............. move the cursor
  4. WAVE up / down .......... scroll
  5. THUMBS DOWN ............. turn OFF (NORMAL mode)
  Quit: click the camera window, press q   (or Ctrl+C here)
  Tip: rest your elbow on the desk. Keep the other hand out of view.
```

**Helper 2: on-screen help panel** in the camera window, using the same 5 lines (shorter wording). It shows for the first 15 seconds, or until you first enter CURSOR, whichever comes first. After that it is hidden for the rest of the session.

**First-time practice order for a beginner:**

1. Run with `DRY_RUN = True`. Nothing real moves. The terminal prints what would have happened.
2. Make a fist until the ring fills. Check the label turns green.
3. Try a quick pinch. Check "CLICK" flashes.
4. Try a pinch-hold. Check orange then green.
5. Try wave up and down. Check the arrows.
6. Make a thumbs-down. Check the label turns gray.
7. Set `DRY_RUN = False` once all six work.

Optional: an "H" key that shows the help panel again. Not part of the MVP.

---

## 9. Exit and safety flow

| Way out | How it works | Works from |
| --- | --- | --- |
| **q key** | Checked every loop. Releases camera, closes window, prints "Stopped." | Only when the camera window has focus |
| **Ctrl+C** | Stops the program from the terminal. `try/finally` still releases the camera | Terminal, always |
| **PyAutoGUI fail-safe (kept ON)** | Slam the real mouse into any screen corner. PyAutoGUI raises an exception, the program catches it and exits cleanly. The program keeps its own cursor 5 px from corners, so it never trips this by accident | Anywhere |
| **Thumbs-down** | Back to NORMAL, mouse output stops | Camera view |
| **No-hand timeout** | 2.0 s with no hand in CURSOR returns to NORMAL | Automatic |
| **Camera disconnects** | 30 failed frame reads in a row (about 1 second): the program exits cleanly and prints a clear message. No click and no cursor move happen on the way out | Automatic |
| **Global Esc key** | Optional, Windows only, works from any window | Optional |

**Important catch:** once CURSOR mode clicks other windows, the camera window loses focus and **q stops working**. That is why Ctrl+C, the corner fail-safe, thumbs-down and the no-hand timeout exist. Tell the builder to test all four.

---

## 10. Gesture cheat sheet

| Gesture | How to do it | What it does | Works in |
| --- | --- | --- | --- |
| **Fist hold** | Close all fingers, hold 1 second | Turns CURSOR mode ON | NORMAL |
| **Pinch hold** | Thumb + index touch, other 3 fingers open, hold over 0.8 s | Cursor follows your hand. Release to stop | CURSOR |
| **Quick pinch** | Thumb + index touch, let go in under 0.8 s | Left click | CURSOR |
| **Wave up** | Swing your hand up fast, then rest | Scroll up one step | CURSOR |
| **Wave down** | Swing your hand down fast, then rest | Scroll down one step | CURSOR |
| **Thumbs-down** | Fist with thumb pointing down, hold 0.4 s | Turns CURSOR mode OFF (back to NORMAL) | CURSOR |
| **q key** | Click the camera window, press q | Quits the program | Both |

*Rule of thumb: keep your palm facing the camera, elbow resting on the desk, and only one hand in view.*

---

## 11. Acceptance checklist

Run each test by hand. Mark Pass or Fail. Start each test in the mode stated.

| # | Flow | Pass condition |
| --- | --- | --- |
| 1 | Launch | ☐ Window opens, label says gray NORMAL, terminal shows the gesture list |
| 2 | Camera not found | ☐ With `CAMERA_INDEX = 9`, a friendly message appears and the program exits with no crash trace |
| 3 | NORMAL ignores everything | ☐ In NORMAL, pinch, wave and thumbs-down do nothing (no click, no move, no scroll) |
| 4 | Fist activation | ☐ Fist for 1.0 s fills the ring and the label turns green CURSOR |
| 5 | Fist too short | ☐ Fist for under 1.0 s: ring empties, label stays NORMAL |
| 6 | Quick pinch | ☐ In CURSOR, pinch and release in under 0.8 s gives one click and a white CLICK flash |
| 7 | Pinch hold | ☐ Holding over 0.8 s: dot turns green, cursor follows, no click on release |
| 8 | Click does not move | ☐ A quick pinch does not nudge the cursor |
| 9 | Wave up | ☐ One quick upward swing scrolls up once and shows ▲ |
| 10 | Wave down | ☐ One quick downward swing scrolls down once and shows ▼. The return swing does not scroll back |
| 11 | Slow drift | ☐ Moving the hand slowly up and down does not scroll |
| 12 | No scroll while pinching | ☐ Moving the pinched hand quickly up or down does not scroll |
| 13 | Thumbs-down | ☐ Thumbs-down for 0.4 s turns the label gray NORMAL, and later pinches do nothing |
| 14 | No bounce back | ☐ Right after thumbs-down, the mode does not flip back to CURSOR |
| 15 | Hand leaves mid-pinch | ☐ Hide the hand mid-pinch: no click, no cursor jump |
| 16 | No-hand timeout | ☐ Hide the hand for 2 s in CURSOR: label returns to NORMAL |
| 17 | Accidental fist in CURSOR | ☐ A fist in CURSOR does nothing |
| 18 | q exit | ☐ With the window focused, q closes the window and the camera light goes off |
| 19 | Ctrl+C exit | ☐ Ctrl+C in the terminal stops the program cleanly, even after clicking other windows |
| 20 | Corner fail-safe | ☐ Slamming the mouse into a screen corner exits the program cleanly |
| 21 | Camera unplugged | ☐ Covering or unplugging the camera mid-run exits cleanly with a message |
| 22 | Full run x10 | ☐ The full flow (launch, fist, click, move, scroll, thumbs-down, quit) runs 10 times with no accidental click, scroll or mode change |

---

## 12. Conflicts and gaps to resolve

| # | Issue | Where | Suggested call |
| --- | --- | --- | --- |
| 1 | **Click window has three values**: brief says about 1 s, PRD says 0.7 s, backend says 0.8 s | Brief / PRD / Backend | This document uses **0.8 s**. It is one CONFIG number |
| 2 | **"Pinch hold, cursor follows"** (brief and PRD) vs **cursor frozen for the first 0.8 s** (backend) | PRD vs Backend | Follow the backend. It stops clicks from nudging the cursor. The orange "PINCH" and green "MOVING" colors make the delay visible |
| 3 | **Thumbs-down shape differs**: PRD says fingers open, backend says fingers curled with thumb out | PRD vs Backend | Follow the backend. Also fixes the clash with the fist |
| 4 | **`q` only works when the camera window has focus**, but the brief says "pressing q exits" | Brief vs Backend §9 | Keep q, and treat Ctrl+C, corner fail-safe, thumbs-down and timeout as the real emergency exits. Consider the optional global Esc |
| 5 | **PyAutoGUI fail-safe**: PRD says disable it, backend says keep it ON | PRD vs Backend | Keep it ON, as the brief asks for it |
| 6 | **Feedback elements are not in the backend Display module**: it lists only landmarks, mode, gesture text and hints. The fist ring, pinch colors, click flash and scroll arrow in §6 are new | Backend §2 | They are small OpenCV draw calls. Add each when its gesture is built (milestones 5, 8, 9) so the Display module does not grow all at once |
| 7 | **Two hands is undefined**: neither doc says which hand wins, and with `MAX_HANDS = 1` the program cannot tell that two are present, so it cannot show a warning | PRD and Backend | Accept the limit for the MVP. Tell the user to keep one hand in view |
| 8 | **Fist timer on a single bad frame** is not specified (one lost frame could reset the 1 s hold) | Backend §3.1 / §4 | If fist activation feels unreliable, allow a tiny grace (about 0.2 s). Otherwise leave as is |
| 9 | **The 15 s help panel and the "Can't see your hand" tip** are not in either doc | This document | Both are text-only. Mark the lighting tip Optional. The help panel is the simplest first-run helper |
| 10 | **Handedness**: PRD assumes a right hand, backend says either hand works | PRD vs Backend | Either hand works. The flow does not depend on it |
