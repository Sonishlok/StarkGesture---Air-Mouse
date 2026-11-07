# 1. Overview and problem statement  
Many users want to move the mouse without touching the trackpad or mouse – for fun or to improve accessibility. “Stark Gestures” uses the built‑in webcam to let you control the cursor with hand signals, with no extra hardware needed. It runs entirely on the laptop (no cloud). In **Normal** mode, nothing happens until you make an **activation gesture** (a fist hold). Then it enters **Cursor** mode, where pinching, waving, etc. act on the mouse. A thumbs‑down exits Cursor mode. This PRD describes a simple, one‑day MVP of the idea.  

# 2. Goals and non‑goals  
**Goals:** Allow basic mouse control by simple hand poses (no tracking of everything). Must run locally with Python+MediaPipe+OpenCV+PyAutoGUI. Keep it robust enough for a beginner to build in a day. Use only gestures listed below (no extra features). Provide visual or on‑screen feedback so the user knows when gestures register.  

**Non‑goals:** We will *not* add right‑click, drag (beyond pinch‑hold), head or face tracking, multi‑hand support, handwriting recognition, or custom gesture training. We *won’t* require or support special hardware (no Leap Motion, depth cameras, etc.). We *won’t* integrate voice or complex GUIs. We assume a single right hand (the user can adapt if left‑handed, but we won’t build handedness switching).  

# 3. Target users and use cases  
- **General users:** People who want to experiment with new inputs. Use case: controlling a presentation or media player hands‑free.  
- **Accessibility use:** For users with limited hand mobility but able to form simple gestures. E.g. a user who can make a fist to start control and pinch to click. It can be an alternative to “eye control” or head‑tracking for those who prefer hand motions.  
- **Presenters:** Someone giving a talk uses pinch or wave gestures to advance slides.  
- **Gamers (simple games):** Might wave or pinch instead of keyboard/joystick (though precision will be low).  
- **Novelty/tool:** Just for fun demos, or to show off computer vision capabilities in class or DIY projects.  

# 4. Competitive and landscape summary  
- **Open-source projects:** Many DIY projects exist. For example, Chaitanya029’s *Virtual Mouse* (MIT licensed) uses MediaPipe + OpenCV + PyAutoGUI: it tracks the index finger for cursor, and closes the index & middle fingers (“pellizco” pinch) to click. It includes smoothing to reduce shake. Ignacio Breñas’ *Virtual_Mouse* (MIT) also uses pinch for left‑click, plus index+middle for right‑click and raising two fingers for scroll. Another is Kinetic-OS’s *HandTrackingModule* (MIT) which separates camera capture, hand-tracking, gesture logic, and OS output. These typically do: capture webcam, get MediaPipe landmarks, then geometry checks (like thumb‑tip close to index‑tip) to decide actions. They often add smoothing (e.g. linear interpolation) to cut cursor jitter. Strengths: no extra hardware needed; works reasonably well in good light. Weaknesses: jittery pointer if unsmoothed, mis-detection (false clicks), and poor performance in dim light or extreme angles. Many warn of PyAutoGUI issues (e.g. needing Python ≤3.8 or disabling fail-safes).  

- **Commercial/OS solutions:** No major OS has built-in webcam hand gestures for the mouse. Windows has “Eye Control” (for eye trackers) and Mac has “Head Pointer” (camera tracking of head), but these use eyes/face, not hands. Leap Motion is a well-known hand‑gesture controller, but it’s special hardware (USB sensor) with high accuracy. Some apps exist: for example **Touchless** (Windows) lets you use an open palm as an “air mouse” and pinch to click, lifting two fingers to scroll. It runs locally and also does voice; it uses pinch/open-hand gestures very similar to our plan. **Hands-Free Control** (TechForAll) and **SmyleMouse** use face or mouth gestures (smiling, head tilt) for mouse, aimed at accessibility. There was Mgestyk (2008), claiming 3D‑camera hand control, but it needed special hardware and had lag. Overall: no free, standard webcam solution is widely used; existing tools are niche (often face/eye) or need hardware. This project sits between hobby Python demos and polished commercial efforts (like Touchless or hardware kits), offering a simple, local, code‑driven approach.  

# 5. Functional requirements (gestures)  

| Gesture         | Trigger condition                                            | Action / Output                               | Edge cases                  |
|-----------------|--------------------------------------------------------------|-----------------------------------------------|-----------------------------|
| **Fist hold (open to fist)** | Hand visible & relaxed; user closes all fingers into a fist and holds for ~1 s. | Switch from *Normal* mode to *Cursor* mode (activation). Provide a visible indicator (e.g. text/box) that Cursor mode is ON. | **False trigger:** avoid if hand jitters or partial; require sustained fist (use time threshold ~1s). If user moves while holding, still count as fist. |
| **Open palm / ignore** | Hand open (not fist) while in Normal mode.  | No action; stays in Normal mode. | – |
| **Pinch hold (thumb + index tips close)** | When in Cursor mode: thumb tip and index tip come together and stay within a small distance threshold. | As long as the pinch is held, **move** the cursor following the hand (use index finger tip position mapped to screen). On pinch release, stop moving. (So pinch-hold = drag/point mode). | **Spurious:** if hand wobbles, small jitter shouldn’t move too suddenly – use smoothing. Ensure pinch threshold isn’t too large. |
| **Quick pinch (tap)** | Pinch (thumb+index) that is released quickly (e.g. within ~0.5–1 s). | **Left click** at the current cursor location on pinch release. (If double quick‑pinch within short time could double-click, optional). | Must avoid double-click if user holds too long; use a timing threshold and cooldown. If user holds beyond 1s, treat it as pinch‑hold (move) instead. |
| **Hand wave up** | In Cursor mode: a rapid upward motion of hand. E.g. index finger Y-velocity exceeds +V_thresh (towards top of frame) for a short burst. | **Scroll up** by one “click” of wheel (or fixed amount). Only once per wave motion (prevent continuous). | Avoid repeated triggers if hand keeps moving; require hand to return to neutral (dead zone) before next scroll. |
| **Hand wave down** | Analogous downward motion (index Y-velocity below –V_thresh). | **Scroll down** one step. | Same dead-zone logic as above. |
| **Thumbs down** | With palm facing camera, thumb extended downward. A simple test: thumb tip is significantly lower (higher Y on screen) than other fingers, and fingers are open. | Switch back to *Normal* mode (deactivate Cursor). Provide indicator. | Must ensure thumb is indeed pointing down; if hand rotates strangely, false negatives may occur. May require palm facing roughly camera. |

# 6. State machine (NORMAL <-> CURSOR)  
- **NORMAL mode:** By default. All gestures are ignored except the **activation (fist)**. In Normal mode, the app should not move the cursor or click on any gestures, to avoid accidental triggers. The user’s hand is effectively “sleeping” until a fist is detected.  
- **CURSOR mode:** Activated when a fist is detected. In this state, gestures (pinch, wave, thumbs down) control the mouse/scroll. If a **thumbs down** gesture is detected, or possibly another reserved “deactivate” gesture, switch back to NORMAL.  

**Text Diagram:**  
```
[NORMAL] --(fist hold 1s)--> [CURSOR]  
[CURSOR] --(thumb down)--> [NORMAL]  
```  

While in Cursor mode, pinch and wave gestures do actions, but do **not** exit Cursor mode (except thumbs-down). In Normal mode, open-hand or pinch should be ignored.  

# 7. Technical architecture and data flow  
1. **Camera Input:** Acquire video frames via OpenCV from the built‑in webcam. (Simple frame loop at ~15–30 FPS.)  
2. **Hand Landmark Detection:** Feed each frame to MediaPipe Hands. This yields up to 2 hand detections; we’ll use only one (the primary hand). MediaPipe returns 21 3D landmarks per detected hand (normalized coordinates).  
3. **Gesture Detection:** For each frame (or at some cadence), compute features from landmarks: distances (e.g. between thumb tip & index tip), relative positions, and motion (difference in landmark positions between frames). Apply logic:  
   - Check if palm/fingers indicate a fist.  
   - If in Cursor mode: check pinch distance, check thumb-down position, compute vertical velocity of hand.  
4. **State Machine:** Based on gesture logic and timing, maintain a simple state (Normal or Cursor) and triggers.  
5. **Cursor Control:** In Cursor mode, map the detected pointer position (e.g. index tip or midpoint of pinch) from camera coordinates to screen coordinates, then issue OS input via PyAutoGUI: moveTo(x,y) for cursor; click() for clicks; scroll() for scrolling.  
6. **Feedback:** Optionally overlay debug annotations on the camera view (e.g. circles or text when gestures recognized) or print status to console for the user.  

Diagram:  
```
Webcam Frame 
    ↓ 
MediaPipe Hands → Landmark list 
    ↓ 
Gesture detection logic (pinch, wave, etc.) 
    ↓ 
State & Mode logic 
    ↓ 
PyAutoGUI actions (move/ click/ scroll) 
```  

# 8. Gesture detection logic (plain language)  
Use MediaPipe landmark points (see endnotes for indexes). The key landmarks are: wrist (0), thumb tip (4), index tip (8), middle tip (12), ring tip (16), pinky tip (20). Also base knuckles like index MCP (5), etc.  

- **Fist (Normal→Cursor):** Check that all finger tips are close to the palm. For example, measure distances from index tip (8), middle tip (12), ring tip (16), pinky tip (20) to the wrist (0) or to the palm center. If *all* fingertips are within a small radius, and they stay so for ~1 second, declare a fist. (A simpler hack: thumb tip (4) to wrist distance is small and other fingers bent.)  

- **Pinch detection:** Compute distance between thumb tip (4) and index tip (8). Normalize by something (like hand size) or use raw pixel distance. If distance < threshold (e.g. in normalized coords ~0.04) then it’s a pinch. We also ensure other fingers (middle, ring, pinky) are not close together to avoid confusion with 2-finger join.  

- **Pinch vs tap:** On pinch start, record the time. If the pinch is released before ~0.7s, count it as a “quick pinch tap”: trigger a left click on release. If the pinch lasts longer than ~0.7s, treat it as a **pinch hold**: begin moving the cursor. (We may start moving as soon as pinch is detected; simply ignore click on release if held past threshold.) On pinch release after a hold, just stop moving (no extra click). Use a small “cooldown” so multiple quick pinches don’t cause accidental double-clicks.  

- **Cursor movement:** When a pinch hold is active, use the current hand position as the cursor target. A common choice is the index finger tip (8) or the midpoint of thumb+index. Map its (x,y) from camera frame to screen. Apply smoothing/filter (see below).  

- **Scroll (hand waves):** Track the vertical motion of the hand (e.g. index tip’s Y coordinate). Compute approximate velocity by difference between frames (y_current – y_prev). If this velocity exceeds a positive threshold (hand moving up quickly) and wasn’t already scrolling, send one `scroll(up)` event. Similarly if velocity < –threshold for down. After sending a scroll, require the hand to return to near-stationary (velocity ≈0) before recognizing a new wave (dead zone). This prevents continuous scroll while the hand moves slowly.  

- **Thumbs-down (Cursor→Normal):** Detect if palm is facing camera (all fingers somewhat visible) and the thumb is pointed downward. For instance, check that thumb tip’s Y coordinate is **below** (i.e. larger on screen) the index tip and the other finger tips, and maybe below the wrist. Also index and middle should be up above thumb. If this posture holds for a short time, exit Cursor mode. Be careful: upside-down camera or side views could confuse it. (Alternatively use MediaPipe’s hand orientation: if z of index and thumb indicate palm facing camera, and thumb vector points down.)  

# 9. Tunable settings (defaults & rationale)  

| Setting                | Default   | Description & Why                                               |
|------------------------|----------|-----------------------------------------------------------------|
| **Camera FPS target**  | 15–30 fps | How many frames per second to process. 30fps is smooth but heavier; 15–20 may suffice for gestures. Lower on slow PCs to save CPU. |
| **Active box margin**  | 10% of frame edges | How far from the camera view edges the pointer goes. E.g. if camera is 0–100% width, map only 10–90% to full screen. This ensures you can reach screen edges without moving hand off-camera. (See i-hmzakhan [13†L333-L342]). Adjust if pointer feels clipped. |
| **Smooth factor**      | α = 0.25 (exponential) | New_cursor = α * new_position + (1–α) * old. Reduces jitter. A value 0.2–0.3 is gentle smoothing with moderate responsiveness. If too jittery, lower to 0.1; if too laggy, raise to 0.5. |
| **Pinch distance thresh.** | ~0.04 (normalized) | Thumb-to-index distance threshold to detect pinch. Roughly 3–4% of image width works; tune by testing. See [23†L268-L270] had 0.035. Must be small enough to avoid false pinch. |
| **Fist hold time**     | 1.0 s    | Time fist must be held to activate. Longer guard reduces accidental triggers. 1s is long but safe. Could try 0.8s if too slow. |
| **Click time window**  | 0.7 s    | Max pinch duration considered a “tap” for click. If pinch released before this, do click. 0.7–1.0s works. We choose 0.7s to avoid confusion with hold. |
| **Scroll velocity thr.** | 0.03 per frame | Minimum normalized Y velocity to count as a wave. 0.03 means hand moved ~3% of frame per frame. Adjust so normal hand drift doesn’t scroll. |
| **Scroll dead zone**   | 0.01 | If Y velocity falls below this after a scroll, allow next. Prevents rapid repeat. |
| **Cursor speed scaling** | 1× mapping | We map camera movement to screen directly via linear interp. If cursor seems too fast/slow, we could scale. Usually direct mapping suffices if active box set properly. |
| **Python sleep time**   | 0.01 s  | Delay between frames or after actions to yield CPU. Use a small sleep (10ms) in loop if needed to reduce CPU load. |

# 10. Non-functional requirements  
- **Latency:** Cursor motion should feel near-real-time. Aim for total loop latency <100ms (MediaPipe runs ~10–20 ms per frame on CPU). Use reduced resolution (e.g. 640×480) for speed.  
- **Frame rate:** ~15–30 FPS. Lower fps (10–15) is acceptable and less CPU heavy. At least 10fps ensures gesture recognition works.  
- **Lighting:** Requires moderate lighting. MediaPipe works best with evenly lit, uncluttered background. Dark rooms or very bright backlight may fail detection.  
- **Camera angle:** Hand should face the camera roughly palm-forward. Extreme angles (side view or back of hand) may break tracking. Recommend user hold hand at a comfortable 30–90° angle to camera.  
- **Handedness:** The code can treat whichever hand appears. However, mapping of left-hand might be mirrored. We suggest using the right hand; supporting left hand is extra logic. (MediaPipe can label left/right). For a beginner MVP, just use whichever hand is detected first.  
- **Jitter:** Without smoothing, the cursor will shake due to detection noise. We mitigate with smoothing as above. There will still be slight wobble.  
- **False triggers:** Even with thresholds, some random pinch-like noise or gestures may occur. We use time thresholds (hold times) and dead-zones to reduce accidental clicks or scrolls. A short cooldown after each action can help.  
- **CPU usage:** MediaPipe+OpenCV is moderately heavy. On a modern laptop, expect ~15–25% CPU usage. Low-power CPUs may struggle at high fps. We accept reduced fps on slower machines.  
- **PyAutoGUI fail-safe:** By default, PyAutoGUI raises an exception if the cursor goes to a screen corner. We should disable `pyautogui.FAILSAFE = False` or ensure our mapping never puts the cursor exactly in a corner.  
- **OS permissions:**  
  - *Windows:* No special permission needed for camera or mouse control, aside from antivirus prompt. Only requirement is Python 3.  
  - *macOS:* The app must be granted Camera access (System Prefs→Security→Privacy) and also “Accessibility” control to send mouse events. The user should be prompted, or instructed to enable these. PyAutoGUI may fail on macOS without granting *Control your computer*.  
  - *Linux:* On X11, PyAutoGUI works; on Wayland (modern Ubuntu GNOME), it may not. Also need X permissions for mouse.  
- **Privacy:** All processing is local. No video or landmarks are sent over network. No logging of images unless developer adds it. (MediaPipe does not require internet.)  

# 11. Risks and mitigations  
- **Jitter/Instability:** Risk: unsteady cursor. Mitigation: smoothing filter (moving average or exp. smoothing). If still bad, reduce camera resolution or lower sensitivity. Provide user knob for smoothing if possible.  
- **Lighting failure:** If too dark, hand not detected → gestures fail. Mitigation: instruct user to ensure lighting. Could show warning text if no hand found for a while.  
- **Hand out of view:** If hand moves off-camera, tracking breaks. Mitigation: calibrate a modest active box, but user education is key: keep hand in view. Possibly auto-pause if hand lost.  
- **False positives:** E.g. a quick middle finger motion might be mistaken for something. Mitigate with thresholds and require clear shapes. Possibly add a “gesture confidence” check (MediaPipe has visibility scores).  
- **Fatigue (“gorilla arm”):** Holding arm up leads to muscle strain. Mitigation: Minimize required reach. Advise user to keep elbows down (see “Home Zone”). Perhaps allow resting arms on desk and moving wrist only. Keep sessions short or include breaks.  
- **PyAutoGUI pitfalls:** On some systems, PyAutoGUI may fail (e.g. multi‑monitor, or slow). Mitigation: if failures, instruct user to use single-monitor and use appropriate flags. Disabling fail-safe and using `.click()` instead of `.mouseDown()` may avoid issues.  
- **Mediapipe errors:** If using wrong version or missing libs, it can crash. Mitigation: specify correct versions in README (we saw one project locked Mediapipe 0.10).  
- **Resource constraints:** On a very slow computer or heavy background load, frame rate may drop. Mitigation: allow user to lower resolution or fps.  

# 12. Test plan (manual)  
For each test, verify corresponding mode (Normal/Cursor) at start. A helper on-screen marker (e.g. text “Mode: CURSOR” or colored border) makes pass/fail clear.

1. **Activation (fist)**: Hold an open palm, then make a fist. *Pass:* After ~1s of solid fist, the app enters Cursor mode (indicator changes). No cursor movement should occur in Normal mode before fist. If fist too short (<1s), no activation.  
2. **Cursor movement (pinch & hold):** In Cursor mode, make a steady pinch and hold (thumb+index together). Move your hand slowly. *Pass:* Cursor follows your finger smoothly (within reason). Release pinch: cursor stops (no extra movement).  
3. **Click (quick pinch):** In Cursor mode, do a quick pinch and release (<0.7s). *Pass:* The cursor position briefly changes color or an indicator shows, and a left-click is registered (e.g. try clicking an icon or pressing a click-detect utility). If held longer (>0.7s), it should not count as click but rather movement.  
4. **Scroll up (wave up):** In Cursor mode with fingers up (no pinch), swiftly move hand up ~20cm. *Pass:* The window scrolls up one step. The cursor should stay in place or follow if pinch was held. On minor shakes, no scroll should occur.  
5. **Scroll down (wave down):** Similar with downward motion. *Pass:* Window scrolls down.  
6. **Deactivation (thumbs-down):** In Cursor mode, give a clear thumbs‑down (thumb extended down, fingers open). *Pass:* The app switches to Normal mode (indicator off), and further pinches or waves do nothing until next fist. If thumb is slightly down but fingers not open, should not trigger.  
7. **Edge cases:**  
   - Perform a false pinch: bring thumb near index briefly but not quite together. *Expected:* no click or movement.  
   - Move hand without pinching: palm open moving up/down slowly. *Expected:* no click (only scroll when velocity threshold is met), no cursor move.  
   - Quick repetitive pinches: pinch-release-pinch-release quickly. *Expected:* multiple clicks, but not missed.  
   - Rest cursor at edge of screen and pinch: pointer should not wrap or fail.  
   - Vary lighting (dim, bright): detection should degrade, confirm it fails gracefully (maybe stop tracking).  

Record pass/fail and any unwanted behaviors (e.g. accidental clicks).

# 13. One-day build plan (milestones)  
1. **Setup & camera capture:** Set up Python env. Get OpenCV capturing webcam and display it. *Check:* Live webcam feed window appears.  
2. **MediaPipe integration:** Install MediaPipe, and detect hand landmarks in real-time. Draw landmarks on frame. *Check:* You see 21 dots/joints on your hand in camera view.  
3. **Cursor mapping:** Choose index tip (8) for pointer. Map its x,y to screen coords (using pyautogui.size()) and do `pyautogui.moveTo()` each frame. Add smoothing. *Check:* Cursor follows your index finger when visible. (Use a large window or known screen area to verify.)  
4. **Pinch detection & click:** Add logic to measure distance(4,8). If < threshold, start timing. If released quickly, send click. *Check:* Quick pinch issues a click (confirm by e.g. clicking notepad or printed output). Long pinch does not click.  
5. **Pinch-hold for move:** If pinch hold passes threshold, toggle a “drag mode”. When active, continually move cursor with finger. Release ends mode. *Check:* When holding pinch, cursor moves; no accidental clicks when released after hold.  
6. **Scroll detection:** Track vertical velocity: compute dy = y_now - y_prev. If dy > +thr (up motion), call `pyautogui.scroll(…)`. If < -thr, scroll down. Use a flag so it triggers once per wave. *Check:* Waving hand up scrolls the page up. Test on a scrollable window.  
7. **Fist/activate & thumbs-down/deactivate:** Implement detection: if all fingers folded (small tip distances), start activation timer. If held 1s, set mode=Cursor. For thumbs-down, check thumb vs fingers. *Check:* Making a fist triggers Cursor mode; thumbs down exits. Ensure it toggles as expected and Normal mode ignores pinch/scroll.  
8. **User feedback/UI:** Print mode (“NORMAL”/“CURSOR”) and detected gesture to console or overlay text. (Optional but helpful). *Check:* The indicator updates on mode changes.  
9. **Tuning & test:** Tune thresholds (distance, times) by testing above steps. Add delays (`time.sleep(0.01)`) if CPU too high. Disable PyAutoGUI failsafe. *Check:* All gestures reliably recognized; CPU usage and lag acceptable.  
Each milestone’s **how to know it works** is listed above. By end of day, all gestures and transitions should be tested and working reasonably (based on test plan above).  

# 14. Future roadmap (V2 ideas)  
- **Right-click gesture:** e.g. thumb+middle finger pinch for right-click (as in some projects).  
- **Drag & drop:** Extend pinch-hold: on release, release mouse down vs hold. Maybe double-pinch for drag.  
- **Volume/media controls:** Add gestures for volume (e.g. rotate hand, or spread fingers) or map two-finger pinch for right-click.  
- **Custom gestures:** Allow user to record a static pose or motion (perhaps using the “Touchless” custom mapping concept). E.g. two-finger pinch for double-click, or a “pinch+middle down” for special keys.  
- **HUD overlay:** Display a heads-up overlay showing mode and simple animation of recognized gesture. (This could be done with OpenCV on the frame, or as a transparent window.)  
- **Left-hand support:** Auto-detect left vs right hand (MediaPipe can say handedness) and mirror appropriately or allow left-hand mapping.  
- **Machine learning:** Use collected landmark data to train a small model to recognize gestures more robustly, instead of hard-coded thresholds.  
- **Gesture combos or sequences:** e.g. pinch + rotate for gestures, or swipes.  

# 15. Sources  
Open-source demos and code: Virtual mouse tutorials and repos (using MediaPipe+OpenCV+PyAutoGUI). Accessibility/gesture apps: *Touchless* hand gesture control; *Mgestyk* (3D camera gesture kit); *Hands-Free Control* (face/head mouse). Technical notes: MediaPipe Hands landmarks and mapping; smoothing technique. Ergonomics: “Home Zone” concept for arm fatigue. Licensing: MediaPipe & OpenCV (Apache 2.0), PyAutoGUI (BSD) – all free to use. (Camera data is processed locally; no external data use.) Each source is cited above.