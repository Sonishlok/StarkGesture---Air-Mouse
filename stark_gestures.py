"""Stark Gestures - webcam hand-gesture mouse."""

import sys
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional, Tuple

if sys.version_info[:2] != (3, 12):
    raise SystemExit(
        "Stark Gestures requires Python 3.12. Run: py -3.12 stark_gestures.py"
    )

import cv2
import mediapipe as mp
import pyautogui


# 1. CONFIG ----------------------------------------------------------------
class CONFIG:
    """Every tunable value lives here."""

    CAMERA_INDEX = 0
    FRAME_WIDTH = 640
    FRAME_HEIGHT = 480
    MIRROR = True
    MAX_HANDS = 1
    MODEL_COMPLEXITY = 0
    MIN_DETECT_CONF = 0.7
    MIN_TRACK_CONF = 0.6
    PINCH_ON = 0.25
    PINCH_OFF = 0.40
    PINCH_DEBOUNCE = 0.05
    FIST_HOLD_TIME = 1.0
    THUMBS_DOWN_HOLD = 0.4
    THUMB_DOWN_MIN = 0.5
    MODE_LOCKOUT = 1.0
    CLICK_WINDOW = 0.8
    CLICK_COOLDOWN = 0.3
    ACTIVE_BOX_MARGIN = 0.10
    SMOOTHING_ALPHA = 0.25
    EDGE_PADDING_PX = 5
    MAX_STEP_PX = 150
    WAVE_SPEED = 1.0
    WAVE_DEADZONE = 0.3
    WAVE_WINDOW = 0.2
    SCROLL_AMOUNT = 200
    SCROLL_COOLDOWN = 0.4
    HAND_LOST_GRACE = 0.3
    NO_HAND_TIMEOUT = 2.0
    EXIT_KEY = "q"
    DRY_RUN = False
    SHOW_PREVIEW = True
    MAX_READ_FAILURES = 30
    HELP_PANEL_TIME = 15.0
    CLICK_FLASH_TIME = 0.3
    SCROLL_FLASH_TIME = 0.4


@dataclass
class Facts:
    """Gesture facts for one frame."""

    hand_present: bool = False
    is_fist: bool = False
    is_pinched: bool = False
    is_thumbs_down: bool = False
    wave: str = "NONE"
    pointer_xy: Optional[Tuple[float, float]] = None
    pinch_xy: Optional[Tuple[float, float]] = None
    vy: float = 0.0
    hand_size: float = 0.0
    pinch_ratio: float = 0.0
    curled: Tuple[bool, bool, bool, bool] = (False, False, False, False)


@dataclass
class Action:
    """A single mouse action requested by the state machine."""

    kind: str
    x: int = 0
    y: int = 0
    amount: int = 0


# 2. Camera ----------------------------------------------------------------
class Camera:
    """Open the webcam, return mirrored frames, release on exit."""

    def __init__(self):
        """Open the camera and request the configured resolution."""
        self.cap = cv2.VideoCapture(CONFIG.CAMERA_INDEX, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            self.cap.release()
            raise RuntimeError(
                "Camera not found. Close Zoom/Teams, check Windows camera "
                "privacy, try CAMERA_INDEX = 1"
            )
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CONFIG.FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CONFIG.FRAME_HEIGHT)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def read(self):
        """Return one mirrored BGR frame, or None when the read fails."""
        ok, frame = self.cap.read()
        if not ok:
            return None
        if CONFIG.MIRROR:
            frame = cv2.flip(frame, 1)
        return frame

    def release(self):
        """Release the webcam."""
        self.cap.release()


# 3. HandTracker -----------------------------------------------------------
class HandTracker:
    """Run MediaPipe Hands and return 21 normalized landmark points."""

    CONNECTIONS = mp.solutions.hands.HAND_CONNECTIONS

    def __init__(self):
        """Create the MediaPipe Hands graph."""
        self.hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=CONFIG.MAX_HANDS,
            model_complexity=CONFIG.MODEL_COMPLEXITY,
            min_detection_confidence=CONFIG.MIN_DETECT_CONF,
            min_tracking_confidence=CONFIG.MIN_TRACK_CONF,
        )

    def process(self, frame):
        """Return (x, y) landmarks, or None when no hand is found."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = self.hands.process(rgb)
        if not results.multi_hand_landmarks:
            return None
        return [(lm.x, lm.y) for lm in results.multi_hand_landmarks[0].landmark]

    def close(self):
        """Release the MediaPipe graph."""
        self.hands.close()


# 4. GestureDetector -------------------------------------------------------
class GestureDetector:
    """Turn landmarks into gesture facts; make no decisions here."""

    FINGERS = ((8, 7), (12, 11), (16, 15), (20, 19))

    def __init__(self):
        """Start with no pinch and an empty wave history."""
        self.pinched = False
        self.palm_history = deque()

    @staticmethod
    def _distance(a, b):
        """Return the straight-line distance between two points."""
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    def _is_curled(self, points, tip, pip):
        """True when a fingertip is closer to the wrist than its joint."""
        return self._distance(points[tip], points[0]) < self._distance(
            points[pip], points[0]
        )

    def detect(self, landmarks, now):
        """Return the current facts for one frame."""
        if landmarks is None:
            self.pinched = False
            self.palm_history.clear()
            return Facts()

        hand_size = self._distance(landmarks[0], landmarks[9])
        if hand_size <= 0.0:
            return Facts(hand_present=True)

        curled = tuple(
            self._is_curled(landmarks, tip, pip) for tip, pip in self.FINGERS
        )
        all_curled = all(curled)
        thumb_dy = (landmarks[4][1] - landmarks[2][1]) / hand_size
        thumb_vertical = abs(landmarks[4][1] - landmarks[2][1]) > abs(
            landmarks[4][0] - landmarks[2][0]
        )
        thumbs_down = (
            all_curled and thumb_dy > CONFIG.THUMB_DOWN_MIN and thumb_vertical
        )
        fist = all_curled and not thumbs_down

        guard = not all(curled[1:])
        pinch_ratio = self._distance(landmarks[4], landmarks[8]) / hand_size
        if self.pinched:
            if pinch_ratio > CONFIG.PINCH_OFF or not guard:
                self.pinched = False
        elif pinch_ratio < CONFIG.PINCH_ON and guard:
            self.pinched = True

        self.palm_history.append((now, landmarks[9][0], landmarks[9][1]))
        while (
            self.palm_history
            and now - self.palm_history[0][0] > CONFIG.WAVE_WINDOW
        ):
            self.palm_history.popleft()
        vx = 0.0
        vy = 0.0
        if len(self.palm_history) >= 2:
            t0, x0, y0 = self.palm_history[0]
            t1, x1, y1 = self.palm_history[-1]
            elapsed = t1 - t0
            if elapsed > 0.0:
                vx = (x1 - x0) / elapsed
                vy = (y1 - y0) / elapsed
        wave = "NONE"
        if abs(vy) > abs(vx):
            if vy < -CONFIG.WAVE_SPEED:
                wave = "UP"
            elif vy > CONFIG.WAVE_SPEED:
                wave = "DOWN"

        pinch_xy = (
            (landmarks[4][0] + landmarks[8][0]) / 2.0,
            (landmarks[4][1] + landmarks[8][1]) / 2.0,
        )
        return Facts(
            hand_present=True,
            is_fist=fist,
            is_pinched=self.pinched,
            is_thumbs_down=thumbs_down,
            wave=wave,
            pointer_xy=landmarks[9],
            pinch_xy=pinch_xy,
            vy=vy,
            hand_size=hand_size,
            pinch_ratio=pinch_ratio,
            curled=curled,
        )


# 5. StateMachine ----------------------------------------------------------
class StateMachine:
    """Own the mode, timers and cooldowns; return actions only."""

    def __init__(self):
        """Start in NORMAL with every timer clear."""
        self.mode = "NORMAL"
        self.cursor_state = "IDLE"
        self.fist_start = None
        self.thumbs_start = None
        self.pinch_start = None
        self.pinch_candidate = None
        self.release_candidate = None
        self.last_click_time = -1e9
        self.mode_change_time = -1e9
        self.fist_rearmed = True
        self.no_hand_start = None
        self.hand_lost_start = None
        self.scroll_state = "ARMED"
        self.last_scroll_time = -1e9
        self.fist_progress = 0.0
        self.pinch_elapsed = 0.0
        self.moving = False

    def _cancel_pinch(self):
        """Cancel any pinch without clicking or moving."""
        self.cursor_state = "IDLE"
        self.pinch_start = None
        self.pinch_candidate = None
        self.release_candidate = None
        self.pinch_elapsed = 0.0
        self.moving = False

    def _set_mode(self, mode, now):
        """Switch mode and start the lockout/re-arm rules."""
        self.mode = mode
        self.mode_change_time = now
        self.fist_start = None
        self.fist_progress = 0.0
        self.thumbs_start = None
        self.fist_rearmed = False
        self.no_hand_start = None
        self.hand_lost_start = None
        self.scroll_state = "ARMED"
        self._cancel_pinch()

    def update(self, facts, now):
        """Update internal state and return the actions for this frame."""
        actions = []
        lockout = (now - self.mode_change_time) < CONFIG.MODE_LOCKOUT

        if facts.hand_present:
            self.no_hand_start = None
        elif self.no_hand_start is None:
            self.no_hand_start = now

        if self.mode == "NORMAL":
            if facts.is_fist:
                if self.fist_rearmed and not lockout:
                    if self.fist_start is None:
                        self.fist_start = now
                    self.fist_progress = min(
                        1.0, (now - self.fist_start) / CONFIG.FIST_HOLD_TIME
                    )
                    if now - self.fist_start >= CONFIG.FIST_HOLD_TIME:
                        self._set_mode("CURSOR", now)
                else:
                    self.fist_start = None
                    self.fist_progress = 0.0
            else:
                self.fist_start = None
                self.fist_progress = 0.0
                if facts.hand_present:
                    self.fist_rearmed = True
            return actions

        if not facts.hand_present:
            self.moving = False
            if self.cursor_state == "PINCHING":
                if self.hand_lost_start is None:
                    self.hand_lost_start = now
                elif now - self.hand_lost_start >= CONFIG.HAND_LOST_GRACE:
                    self._cancel_pinch()
            if (
                self.no_hand_start is not None
                and now - self.no_hand_start >= CONFIG.NO_HAND_TIMEOUT
            ):
                self._set_mode("NORMAL", now)
            return actions

        self.hand_lost_start = None

        if facts.is_thumbs_down and not lockout:
            if self.thumbs_start is None:
                self.thumbs_start = now
            if now - self.thumbs_start >= CONFIG.THUMBS_DOWN_HOLD:
                self._set_mode("NORMAL", now)
                return actions
        else:
            self.thumbs_start = None

        if self.cursor_state == "PINCHING":
            self.pinch_elapsed = now - self.pinch_start
            if facts.is_pinched:
                self.release_candidate = None
                if self.pinch_elapsed > CONFIG.CLICK_WINDOW:
                    self.moving = True
                    if facts.pointer_xy is not None:
                        actions.append(
                            Action("MOVE", facts.pointer_xy[0], facts.pointer_xy[1])
                        )
                else:
                    self.moving = False
            else:
                self.moving = False
                if self.release_candidate is None:
                    self.release_candidate = now
                elif now - self.release_candidate >= CONFIG.PINCH_DEBOUNCE:
                    duration = self.release_candidate - self.pinch_start
                    if (
                        duration <= CONFIG.CLICK_WINDOW
                        and not facts.is_thumbs_down
                        and now - self.last_click_time >= CONFIG.CLICK_COOLDOWN
                    ):
                        actions.append(Action("CLICK"))
                        self.last_click_time = now
                    self._cancel_pinch()
            return actions

        self.moving = False
        self.pinch_elapsed = 0.0
        if facts.is_pinched:
            if self.pinch_candidate is None:
                self.pinch_candidate = now
            elif now - self.pinch_candidate >= CONFIG.PINCH_DEBOUNCE:
                self.cursor_state = "PINCHING"
                self.pinch_start = now
                self.pinch_candidate = None
                self.release_candidate = None
                self.pinch_elapsed = 0.0
                return actions
        else:
            self.pinch_candidate = None

        if self.scroll_state == "WAITING_FOR_CALM" and (
            abs(facts.vy) < CONFIG.WAVE_DEADZONE
        ):
            self.scroll_state = "ARMED"
        if (
            self.scroll_state == "ARMED"
            and facts.wave != "NONE"
            and not facts.is_pinched
            and now - self.last_scroll_time >= CONFIG.SCROLL_COOLDOWN
        ):
            amount = (
                CONFIG.SCROLL_AMOUNT
                if facts.wave == "UP"
                else -CONFIG.SCROLL_AMOUNT
            )
            actions.append(Action("SCROLL", amount=amount))
            self.last_scroll_time = now
            self.scroll_state = "WAITING_FOR_CALM"

        return actions


# 6. CursorMapper ----------------------------------------------------------
class CursorMapper:
    """Map a camera point into the active box, smooth it, cap the step."""

    def __init__(self, screen_width, screen_height):
        """Store the primary screen size and clear the smoothing state."""
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)
        self.smooth_x = None
        self.smooth_y = None
        self.out_x = None
        self.out_y = None

    def begin_move(self, current_pos):
        """Start a move phase from the real cursor position."""
        self.smooth_x = float(current_pos[0])
        self.smooth_y = float(current_pos[1])
        self.out_x = int(current_pos[0])
        self.out_y = int(current_pos[1])

    def map(self, point):
        """Return the smoothed, capped screen point for a camera point."""
        margin = CONFIG.ACTIVE_BOX_MARGIN
        nx = min(max((point[0] - margin) / (1.0 - 2.0 * margin), 0.0), 1.0)
        ny = min(max((point[1] - margin) / (1.0 - 2.0 * margin), 0.0), 1.0)
        target_x = nx * (self.screen_width - 1)
        target_y = ny * (self.screen_height - 1)

        if self.smooth_x is None:
            self.smooth_x = target_x
            self.smooth_y = target_y
        else:
            alpha = CONFIG.SMOOTHING_ALPHA
            self.smooth_x = alpha * target_x + (1.0 - alpha) * self.smooth_x
            self.smooth_y = alpha * target_y + (1.0 - alpha) * self.smooth_y

        x = int(self.smooth_x)
        y = int(self.smooth_y)
        if self.out_x is not None:
            x = min(max(x, self.out_x - CONFIG.MAX_STEP_PX), self.out_x + CONFIG.MAX_STEP_PX)
            y = min(max(y, self.out_y - CONFIG.MAX_STEP_PX), self.out_y + CONFIG.MAX_STEP_PX)

        x = min(
            max(x, CONFIG.EDGE_PADDING_PX),
            self.screen_width - 1 - CONFIG.EDGE_PADDING_PX,
        )
        y = min(
            max(y, CONFIG.EDGE_PADDING_PX),
            self.screen_height - 1 - CONFIG.EDGE_PADDING_PX,
        )
        self.out_x = x
        self.out_y = y
        return x, y


# 7. ActionExecutor --------------------------------------------------------
class ActionExecutor:
    """The only class allowed to call PyAutoGUI."""

    def __init__(self):
        """Turn on the fail-safe and remove PyAutoGUI's default pause."""
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0

    def screen_size(self):
        """Return the primary screen size."""
        return pyautogui.size()

    def cursor_position(self):
        """Return the current real cursor position."""
        return pyautogui.position()

    def execute(self, action):
        """Perform one action, or print it when DRY_RUN is on."""
        if action.kind == "MOVE":
            if CONFIG.DRY_RUN:
                print(f"DRY RUN MOVE {action.x},{action.y}")
            else:
                pyautogui.moveTo(action.x, action.y)
        elif action.kind == "CLICK":
            if CONFIG.DRY_RUN:
                print("DRY RUN CLICK")
            else:
                pyautogui.click()
        elif action.kind == "SCROLL":
            if CONFIG.DRY_RUN:
                print(f"DRY RUN SCROLL {action.amount}")
            else:
                pyautogui.scroll(action.amount)


# 8. Display ---------------------------------------------------------------
class Display:
    """Draw the preview, overlays and help panel; return pressed keys."""

    WINDOW_NAME = "Stark Gestures"
    RING_RADIUS_PX = 40

    def __init__(self):
        """Start the help-panel timer and clear the flash effects."""
        self.start_time = time.monotonic()
        self.help_hidden = False
        self.click_flash_until = 0.0
        self.click_flash_pos = None
        self.scroll_flash_until = 0.0
        self.scroll_flash_pos = None
        self.scroll_flash_dir = "NONE"

    @staticmethod
    def _to_px(point, frame):
        """Convert a normalized point to frame pixels."""
        height, width = frame.shape[:2]
        return int(point[0] * width), int(point[1] * height)

    def trigger_click(self, point, now):
        """Start the white CLICK flash at the pinch point."""
        if point is not None:
            self.click_flash_pos = point
            self.click_flash_until = now + CONFIG.CLICK_FLASH_TIME

    def trigger_scroll(self, direction, point, now):
        """Start the cyan scroll arrow beside the hand."""
        if point is not None:
            self.scroll_flash_pos = point
            self.scroll_flash_dir = direction
            self.scroll_flash_until = now + CONFIG.SCROLL_FLASH_TIME

    def show(self, frame, landmarks, mode, facts, state, now):
        """Draw one frame, show it, and return the pressed key."""
        if CONFIG.SHOW_PREVIEW:
            self._draw(frame, landmarks, mode, facts, state, now)
            cv2.imshow(self.WINDOW_NAME, frame)
        return cv2.waitKey(1) & 0xFF

    def _draw(self, frame, landmarks, mode, facts, state, now):
        """Draw every overlay for this frame."""
        height, width = frame.shape[:2]

        if landmarks:
            for start, end in HandTracker.CONNECTIONS:
                cv2.line(
                    frame,
                    self._to_px(landmarks[start], frame),
                    self._to_px(landmarks[end], frame),
                    (0, 200, 0),
                    1,
                )
            for point in landmarks:
                cv2.circle(frame, self._to_px(point, frame), 3, (255, 255, 255), -1)

        mode_color = (0, 200, 0) if mode == "CURSOR" else (160, 160, 160)
        cv2.putText(
            frame, mode, (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.2, mode_color, 3
        )

        if (
            mode == "NORMAL"
            and facts.is_fist
            and state.fist_progress > 0.0
            and landmarks
        ):
            center = self._to_px(landmarks[0], frame)
            end_angle = -90 + int(360.0 * state.fist_progress)
            cv2.ellipse(
                frame,
                center,
                (self.RING_RADIUS_PX, self.RING_RADIUS_PX),
                0,
                -90,
                end_angle,
                (0, 255, 255),
                3,
            )

        if (
            mode == "CURSOR"
            and state.cursor_state == "PINCHING"
            and facts.pinch_xy is not None
        ):
            point = self._to_px(facts.pinch_xy, frame)
            if state.pinch_elapsed > CONFIG.CLICK_WINDOW:
                cv2.circle(frame, point, 10, (0, 200, 0), -1)
                cv2.putText(
                    frame,
                    "MOVING",
                    (point[0] + 14, point[1] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 200, 0),
                    2,
                )
            else:
                cv2.circle(frame, point, 10, (0, 165, 255), -1)
                cv2.putText(
                    frame,
                    "PINCH",
                    (point[0] + 14, point[1] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 165, 255),
                    2,
                )

        if now < self.click_flash_until and self.click_flash_pos is not None:
            point = self._to_px(self.click_flash_pos, frame)
            cv2.circle(frame, point, 30, (255, 255, 255), 3)
            cv2.putText(
                frame,
                "CLICK",
                (point[0] + 16, point[1] + 34),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
            )

        if now < self.scroll_flash_until and self.scroll_flash_pos is not None:
            point = self._to_px(self.scroll_flash_pos, frame)
            if self.scroll_flash_dir == "UP":
                cv2.arrowedLine(
                    frame,
                    (point[0] + 35, point[1] + 30),
                    (point[0] + 35, point[1] - 30),
                    (255, 255, 0),
                    3,
                    tipLength=0.4,
                )
            else:
                cv2.arrowedLine(
                    frame,
                    (point[0] + 35, point[1] - 30),
                    (point[0] + 35, point[1] + 30),
                    (255, 255, 0),
                    3,
                    tipLength=0.4,
                )

        if not facts.hand_present:
            cv2.putText(
                frame,
                "No hand",
                (15, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 0, 255),
                2,
            )

        if mode == "CURSOR":
            self.help_hidden = True
        if not self.help_hidden and now - self.start_time < CONFIG.HELP_PANEL_TIME:
            self._draw_help(frame, width)

        if CONFIG.DRY_RUN:
            text = "DRY RUN: mouse not moving"
            (text_w, _), _ = cv2.getTextSize(
                text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1
            )
            cv2.rectangle(frame, (10, height - 35), (20 + text_w, height - 10), (0, 0, 255), -1)
            cv2.putText(
                frame,
                text,
                (15, height - 17),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                1,
            )

    def _draw_help(self, frame, width):
        """Draw the first-run gesture panel."""
        lines = [
            "FIST hold 1 s   -> CURSOR",
            "QUICK PINCH     -> click",
            "PINCH hold      -> move cursor",
            "WAVE up / down  -> scroll",
            "THUMBS DOWN     -> NORMAL",
            "Quit: q or Ctrl+C",
        ]
        x = max(10, width - 280)
        y = 10
        line_height = 24
        box_height = line_height * len(lines) + 16
        overlay = frame.copy()
        cv2.rectangle(
            overlay, (x, y), (x + 265, y + box_height), (0, 0, 0), -1
        )
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
        for index, line in enumerate(lines):
            cv2.putText(
                frame,
                line,
                (x + 10, y + 24 + index * line_height),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
            )

    def close(self):
        """Close every OpenCV window."""
        cv2.destroyAllWindows()


# 9. main ------------------------------------------------------------------
def main():
    """Run the full gesture mouse loop with a safe exit."""
    camera = None
    tracker = None
    display = Display()
    try:
        camera = Camera()
        print(
            "STARK GESTURES: hand gesture mouse\n"
            "  1. FIST, hold 1 sec ........ turn ON (CURSOR mode)\n"
            "  2. PINCH, quick ............ left click\n"
            "  3. PINCH, hold ............. move the cursor\n"
            "  4. WAVE up / down .......... scroll\n"
            "  5. THUMBS DOWN ............. turn OFF (NORMAL mode)\n"
            "  Quit: click the camera window, press q   (or Ctrl+C here)\n"
            "  Tip: rest your elbow on the desk. Keep the other hand out of view."
        )
        if CONFIG.DRY_RUN:
            print("DRY RUN: actions are printed; the real mouse is not moved.")

        tracker = HandTracker()
        detector = GestureDetector()
        state = StateMachine()
        executor = ActionExecutor()
        screen_width, screen_height = executor.screen_size()
        mapper = CursorMapper(screen_width, screen_height)

        read_failures = 0
        was_moving = False
        while True:
            frame = camera.read()
            now = time.monotonic()
            if frame is None:
                read_failures += 1
                if read_failures >= CONFIG.MAX_READ_FAILURES:
                    print("Camera stopped responding. Exiting cleanly.")
                    break
                continue
            read_failures = 0

            landmarks = tracker.process(frame)
            facts = detector.detect(landmarks, now)
            actions = state.update(facts, now)

            moving_this_frame = False
            for action in actions:
                if action.kind == "MOVE":
                    if not was_moving and not moving_this_frame:
                        mapper.begin_move(executor.cursor_position())
                    screen_x, screen_y = mapper.map((action.x, action.y))
                    executor.execute(Action("MOVE", screen_x, screen_y))
                    moving_this_frame = True
                elif action.kind == "CLICK":
                    executor.execute(action)
                    display.trigger_click(facts.pinch_xy, now)
                elif action.kind == "SCROLL":
                    executor.execute(action)
                    direction = "UP" if action.amount > 0 else "DOWN"
                    display.trigger_scroll(direction, facts.pointer_xy, now)
            was_moving = moving_this_frame

            key = display.show(frame, landmarks, state.mode, facts, state, now)
            if key == ord(CONFIG.EXIT_KEY):
                break
    except pyautogui.FailSafeException:
        print("PyAutoGUI fail-safe triggered. Exiting cleanly.")
    except RuntimeError as error:
        print(error)
    except KeyboardInterrupt:
        pass
    finally:
        if tracker is not None:
            tracker.close()
        if camera is not None:
            camera.release()
        display.close()
    print("Stopped.")


if __name__ == "__main__":
    main()




