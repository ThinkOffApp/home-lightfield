"""
Eye animation sequences - composable behaviors built from expressions.

Each sequence is a generator that yields (left_grid, right_grid, duration_ms) tuples.
The animation engine consumes these to drive the blinders.

Sequences can be:
- One-shot (blink, surprise reaction)
- Looping (idle scanning, breathing)
- Reactive (triggered by camera events)
"""

import time
import math
import random
from grid import Grid
from expressions import (
    eye_open, eye_closed, eye_blink_top, eye_half_closed,
    eye_wide, eye_squint, eye_supernova, eye_spiral,
    eye_heart, eye_x, eye_arrow, look_at_xy,
    eye_ripple, eye_plasma, eye_pinwheel, eye_rain,
    eye_kaleidoscope, eye_breathe, eye_scroll_text, eye_scroll_text_wide,
    _text_to_columns,
    IRIS_COLOR, LOOK_POSITIONS, EYE_SCHEMES,
    THINKOFF_PALETTE, PINK_FUCHSIA,
    TK_CORE, TK_MID, TK_EDGE, TK_MAGENTA, TK_BLUE, TK_INDIGO,
)


def blink(look_x=0.0, look_y=0.5, iris_color=IRIS_COLOR):
    """Single blink animation. ~300ms total."""
    open_frame = eye_open(look_x, look_y, iris_color)
    half = eye_blink_top()
    closed = eye_closed()

    yield (open_frame, open_frame, 50)    # open
    yield (half, half, 60)                 # closing
    yield (closed, closed, 80)             # closed
    yield (half, half, 60)                 # opening
    yield (open_frame, open_frame, 50)     # open


def double_blink(look_x=0.0, look_y=0.5, iris_color=IRIS_COLOR):
    """Double blink - surprised or adjusting."""
    yield from blink(look_x, look_y, iris_color)
    yield (eye_open(look_x, look_y, iris_color),) * 2 + (100,)
    yield from blink(look_x, look_y, iris_color)


def slow_blink(look_x=0.0, look_y=0.5, iris_color=IRIS_COLOR):
    """Slow deliberate blink - sleepy or thoughtful."""
    open_frame = eye_open(look_x, look_y, iris_color)
    half = eye_half_closed(look_x, look_y, iris_color)
    closed = eye_closed()

    yield (open_frame, open_frame, 100)
    yield (half, half, 150)
    yield (closed, closed, 400)  # held closed longer
    yield (half, half, 200)
    yield (open_frame, open_frame, 100)


def look_left_to_right(duration_sec=3.0, iris_color=IRIS_COLOR):
    """Smooth scan from left to right."""
    steps = int(duration_sec * 20)  # 20fps
    frame_ms = int(1000 / 20)

    for i in range(steps):
        t = i / steps
        look_x = -1.0 + 2.0 * t  # -1 to 1
        frame = eye_open(look_x, 0.5, iris_color)
        yield (frame, frame, frame_ms)


def look_right_to_left(duration_sec=3.0, iris_color=IRIS_COLOR):
    """Smooth scan from right to left."""
    steps = int(duration_sec * 20)
    frame_ms = int(1000 / 20)

    for i in range(steps):
        t = i / steps
        look_x = 1.0 - 2.0 * t
        frame = eye_open(look_x, 0.5, iris_color)
        yield (frame, frame, frame_ms)


def track_object(x_start, x_end, y=0.5, duration_sec=2.0, iris_color=IRIS_COLOR):
    """Track an object moving across the field of view."""
    steps = int(duration_sec * 20)
    frame_ms = int(1000 / 20)

    for i in range(steps):
        t = i / steps
        x = x_start + (x_end - x_start) * t
        frame = eye_open(x, y, iris_color)
        yield (frame, frame, frame_ms)


def surprise(look_x=0.0, look_y=0.0, iris_color=IRIS_COLOR):
    """Surprise reaction - eyes go wide."""
    normal = eye_open(look_x, look_y, iris_color)
    wide = eye_wide(look_x, look_y, iris_color)

    yield (normal, normal, 50)
    yield (wide, wide, 800)  # hold wide
    # Settle back
    for i in range(10):
        t = i / 10
        blended = wide.blend(normal, t)
        yield (blended, blended, 50)


def suspicious(direction='left', iris_color=IRIS_COLOR):
    """Suspicious squint in a direction."""
    normal = eye_open(0, 0.5, iris_color)
    look_x = -0.8 if direction == 'left' else 0.8
    squint = eye_squint(look_x, iris_color)

    # Slow transition to squint
    for i in range(15):
        t = i / 15
        blended = normal.blend(squint, t)
        yield (blended, blended, 60)

    yield (squint, squint, 1000)  # hold suspicion

    # Back to normal
    for i in range(15):
        t = i / 15
        blended = squint.blend(normal, t)
        yield (blended, blended, 60)


def supernova_burst(iris_color=IRIS_COLOR):
    """Internal supernova explosion effect."""
    steps = 40  # 2 seconds at 20fps
    for i in range(steps):
        phase = i / steps
        frame = eye_supernova(phase, iris_color)
        yield (frame, frame, 50)

    # Fade back to normal eye
    final_nova = eye_supernova(1.0, iris_color)
    normal = eye_open(0, 0.5, iris_color)
    for i in range(20):
        t = i / 20
        blended = final_nova.blend(normal, t)
        yield (blended, blended, 50)


def hypnotize(duration_sec=5.0, iris_color=IRIS_COLOR):
    """Hypnotic spiral."""
    steps = int(duration_sec * 20)
    for i in range(steps):
        phase = (i / steps) % 1.0
        frame = eye_spiral(phase, iris_color)
        yield (frame, frame, 50)


def love():
    """Heart eyes."""
    normal = eye_open(0, 0.5)
    heart = eye_heart()

    # Pop to hearts
    yield (heart, heart, 1500)

    # Back to normal
    for i in range(10):
        t = i / 10
        blended = heart.blend(normal, t)
        yield (blended, blended, 50)


def death():
    """X eyes - stunned/dead."""
    x = eye_x()
    yield (x, x, 2000)


def idle_scan(duration_sec=30.0, iris_color=IRIS_COLOR):
    """
    Idle behavior: eyes slowly scan the scene with occasional blinks.
    Good default loop when no camera events are happening.
    """
    start = time.time()

    while time.time() - start < duration_sec:
        # Pick a random look target
        target_x = random.uniform(-0.8, 0.8)
        target_y = random.uniform(0.2, 0.8)
        hold_time = random.uniform(1.5, 4.0)

        # Smooth move to target
        current = eye_open(0, 0.5, iris_color)
        steps = 15
        for i in range(steps):
            t = i / steps
            x = t * target_x
            y = 0.5 + t * (target_y - 0.5)
            frame = eye_open(x, y, iris_color)
            yield (frame, frame, 40)

        # Hold position
        frame = eye_open(target_x, target_y, iris_color)
        hold_frames = int(hold_time * 20)
        for _ in range(hold_frames):
            yield (frame, frame, 50)

        # Maybe blink
        if random.random() < 0.4:
            yield from blink(target_x, target_y, iris_color)

        # Small chance of double blink
        if random.random() < 0.1:
            yield from double_blink(target_x, target_y, iris_color)


def wink(side='right', look_x=0.0, look_y=0.5, iris_color=IRIS_COLOR):
    """Wink one eye."""
    open_frame = eye_open(look_x, look_y, iris_color)
    closed = eye_closed()

    if side == 'right':
        yield (open_frame, open_frame, 50)
        yield (open_frame, closed, 200)
        yield (open_frame, open_frame, 50)
    else:
        yield (open_frame, open_frame, 50)
        yield (closed, open_frame, 200)
        yield (open_frame, open_frame, 50)


def independent_look(left_target, right_target, iris_color=IRIS_COLOR):
    """Eyes look in different directions (goofy/chameleon)."""
    lx, ly = left_target
    rx, ry = right_target
    left = eye_open(lx, ly, iris_color)
    right = eye_open(rx, ry, iris_color)
    yield (left, right, 1000)


def ripple(duration_sec=5.0, colors=THINKOFF_PALETTE):
    """Concentric color ripples radiating from center."""
    steps = int(duration_sec * 20)
    for i in range(steps):
        phase = (i / steps) % 1.0
        frame = eye_ripple(phase, colors)
        yield (frame, frame, 50)


def plasma(duration_sec=5.0, colors=THINKOFF_PALETTE):
    """Plasma interference pattern."""
    steps = int(duration_sec * 20)
    for i in range(steps):
        phase = (i / steps) % 1.0
        frame = eye_plasma(phase, colors)
        yield (frame, frame, 50)


def pinwheel(duration_sec=5.0, colors=THINKOFF_PALETTE, arms=3):
    """Spinning pinwheel/starburst."""
    steps = int(duration_sec * 20)
    for i in range(steps):
        phase = (i / steps) % 1.0
        frame = eye_pinwheel(phase, colors, arms)
        yield (frame, frame, 50)


def color_rain(duration_sec=5.0, colors=THINKOFF_PALETTE):
    """Color rain cascading down."""
    steps = int(duration_sec * 20)
    for i in range(steps):
        phase = (i / steps) % 1.0
        frame = eye_rain(phase, colors)
        yield (frame, frame, 50)


def kaleidoscope(duration_sec=5.0, colors=THINKOFF_PALETTE):
    """Kaleidoscope mirror pattern."""
    steps = int(duration_sec * 20)
    for i in range(steps):
        phase = (i / steps) % 1.0
        frame = eye_kaleidoscope(phase, colors)
        yield (frame, frame, 50)


def breathe(duration_sec=5.0, color_a=TK_CORE, color_b=TK_MAGENTA):
    """Slow breathe between two colors."""
    steps = int(duration_sec * 20)
    for i in range(steps):
        phase = (i / steps) % 1.0
        frame = eye_breathe(phase, color_a, color_b)
        yield (frame, frame, 50)


def pink_fuchsia_spiral(duration_sec=5.0):
    """Hypnotic spiral in pink-fuchsia-purple shades."""
    yield from hypnotize(duration_sec, PINK_FUCHSIA[0])


def pink_fuchsia_ripple(duration_sec=5.0):
    """Concentric ripples in pink-fuchsia-purple."""
    yield from ripple(duration_sec, PINK_FUCHSIA)


def pink_fuchsia_plasma(duration_sec=5.0):
    """Plasma in pink-fuchsia-purple."""
    yield from plasma(duration_sec, PINK_FUCHSIA)


def thinkoff_spiral(duration_sec=5.0):
    """Hypnotic spiral using TK_CORE brand pink."""
    yield from hypnotize(duration_sec, TK_CORE)


def thinkoff_ripple(duration_sec=5.0):
    """Ripples in full ThinkOff 7-color palette."""
    yield from ripple(duration_sec, THINKOFF_PALETTE)


def thinkoff_plasma(duration_sec=5.0):
    """Plasma in full ThinkOff 7-color palette."""
    yield from plasma(duration_sec, THINKOFF_PALETTE)


def thinkoff_pinwheel(duration_sec=5.0):
    """Pinwheel in full ThinkOff 7-color palette."""
    yield from pinwheel(duration_sec, THINKOFF_PALETTE)


def thinkoff_kaleidoscope(duration_sec=5.0):
    """Kaleidoscope in full ThinkOff 7-color palette."""
    yield from kaleidoscope(duration_sec, THINKOFF_PALETTE)


def scroll_text(text, color=TK_CORE, speed_ms=150, loops=2):
    """Scroll text across both blinders (10 columns wide). Each frame shifts one column left."""
    columns = _text_to_columns(text)
    total = len(columns)
    if total == 0:
        return
    for loop in range(loops):
        for offset in range(total):
            left, right = eye_scroll_text_wide(text, offset, color)
            yield (left, right, speed_ms)


# --- Lively eye tracking ---

# Persistent state across calls so the track-lively animation builds a coherent
# stream of events rather than restarting every few seconds.
_lively_state = {
    'scheme_idx': 0,
    'left_scheme_idx': 0,   # independent color per eye, for extra variety
    'frames_since_scheme_change': 0,
    'frames_since_blink': 0,
    'next_blink_at': 90,   # ~4.5s at 20fps
    'next_wink_at': 400,   # ~20s at 20fps
    'frames_since_wink': 0,
    'wink_side': 'right',
}


def _scheme_colors(idx):
    scheme = EYE_SCHEMES[idx % len(EYE_SCHEMES)]
    return scheme  # (iris, pupil, white, eyelid)


def _eye_with_scheme(look_x, look_y, scheme):
    iris, pupil, eyeball, eyelid = scheme
    return eye_open(look_x, look_y, iris, pupil, eyeball, eyelid)


def eye_track_lively(look_x=0.0, look_y=0.5, duration_sec=3.0):
    """Lively eye tracking — position follows look coords, with slow color
    cycling, occasional blinks, and rare winks. Generates N frames of
    animation at 20fps."""
    import random as _random
    s = _lively_state
    frames = int(duration_sec * 20)  # 20fps
    frame_ms = 50

    for _ in range(frames):
        s['frames_since_scheme_change'] += 1
        s['frames_since_blink'] += 1
        s['frames_since_wink'] += 1

        # Slow color scheme crossfade every ~25-45 seconds
        if s['frames_since_scheme_change'] > _random.randint(500, 900):
            s['scheme_idx'] = (s['scheme_idx'] + 1) % len(EYE_SCHEMES)
            # Sometimes change the left eye independently for a mismatched look
            if _random.random() < 0.4:
                s['left_scheme_idx'] = (s['scheme_idx']
                                        + _random.randint(1, 3)) % len(EYE_SCHEMES)
            else:
                s['left_scheme_idx'] = s['scheme_idx']
            s['frames_since_scheme_change'] = 0

        right_scheme = _scheme_colors(s['scheme_idx'])
        left_scheme = _scheme_colors(s['left_scheme_idx'])

        # Blink occasionally (every 4-9 seconds)
        if s['frames_since_blink'] >= s['next_blink_at']:
            s['frames_since_blink'] = 0
            s['next_blink_at'] = _random.randint(80, 180)
            # Short blink: open -> blink_mid -> closed -> blink_mid -> open
            blink_seq = [
                (None, 40),            # last open frame (placeholder)
                ('blink_mid', 60),
                ('closed', 80),
                ('blink_mid', 60),
                (None, 20),
            ]
            for kind, ms in blink_seq:
                if kind is None:
                    right = _eye_with_scheme(look_x, look_y, right_scheme)
                    left = _eye_with_scheme(look_x, look_y, left_scheme)
                elif kind == 'closed':
                    right = eye_closed(right_scheme[3], right_scheme[2])
                    left = eye_closed(left_scheme[3], left_scheme[2])
                else:
                    right = eye_blink_top(right_scheme[2], right_scheme[3])
                    left = eye_blink_top(left_scheme[2], left_scheme[3])
                yield (left, right, ms)
            continue

        # Wink occasionally (every 15-40 seconds)
        if s['frames_since_wink'] >= s['next_wink_at']:
            s['frames_since_wink'] = 0
            s['next_wink_at'] = _random.randint(300, 800)
            s['wink_side'] = 'right' if _random.random() < 0.5 else 'left'
            open_right = _eye_with_scheme(look_x, look_y, right_scheme)
            open_left = _eye_with_scheme(look_x, look_y, left_scheme)
            closed_right = eye_closed(right_scheme[3], right_scheme[2])
            closed_left = eye_closed(left_scheme[3], left_scheme[2])
            wink_seq = [(60, 'open'), (50, 'half'), (180, 'full'),
                        (50, 'half'), (40, 'open')]
            for ms, stage in wink_seq:
                if s['wink_side'] == 'right':
                    left = open_left
                    if stage == 'full': right = closed_right
                    elif stage == 'half': right = eye_blink_top(right_scheme[2], right_scheme[3])
                    else: right = open_right
                else:
                    right = open_right
                    if stage == 'full': left = closed_left
                    elif stage == 'half': left = eye_blink_top(left_scheme[2], left_scheme[3])
                    else: left = open_left
                yield (left, right, ms)
            continue

        # Normal frame — just the eye tracking
        right = _eye_with_scheme(look_x, look_y, right_scheme)
        left = _eye_with_scheme(look_x, look_y, left_scheme)
        yield (left, right, frame_ms)


def idle_lively(duration_sec=30.0):
    """Idle mode with lively eyes: slow scanning, blinks, winks, color cycling."""
    import random as _random
    start = time.time()
    target_x = 0.0
    target_y = 0.5
    while time.time() - start < duration_sec:
        # Pick a new random target every 2-5 seconds, smooth-scan to it
        new_x = _random.uniform(-0.8, 0.8)
        new_y = _random.uniform(0.2, 0.8)
        hold = _random.uniform(2.0, 5.0)

        # Smooth-interpolate for ~500ms
        steps = 10
        for i in range(steps):
            t = (i + 1) / steps
            x = target_x + (new_x - target_x) * t
            y = target_y + (new_y - target_y) * t
            yield from eye_track_lively(x, y, duration_sec=0.05)

        target_x, target_y = new_x, new_y

        # Hold at target with blinks/color cycling
        yield from eye_track_lively(target_x, target_y, duration_sec=hold)
