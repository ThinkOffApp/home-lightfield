"""
Eye expressions for 5x5 pixel blinders.

Each expression is a function that returns a Grid with the eye drawn.
The eye has: iris (colored circle), pupil (dark center), eyelids (top/bottom).

Coordinate system:
- (0,0) = top-left
- (4,4) = bottom-right
- Center of eye = (2, 2)
- Look direction offsets the pupil/iris

Since the windows overlook a park from above, the default gaze
is slightly downward (y offset +0.5) and can sweep left-right.
"""

from grid import Grid
import math


# Color palette
IRIS_COLOR = (0, 140, 255)       # bright blue iris
PUPIL_COLOR = (0, 0, 0)          # black pupil
WHITE_COLOR = (255, 255, 255)    # eye white
EYELID_COLOR = (0, 0, 0)        # closed eyelid (black/off)
HIGHLIGHT_COLOR = (255, 255, 255)  # specular highlight


def _distance(x1, y1, x2, y2):
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def eye_open(look_x=0.0, look_y=0.5, iris_color=IRIS_COLOR):
    """
    Open eye looking in a direction.

    look_x: -1.0 (far left) to 1.0 (far right), 0 = center
    look_y: -1.0 (up) to 1.0 (down), 0.5 = slightly down (default, overlooking park)
    """
    g = Grid()

    # Eye center with look offset
    cx = 2.0 + look_x * 1.2
    cy = 2.0 + look_y * 0.8

    for y in range(5):
        for x in range(5):
            d = _distance(x, y, cx, cy)

            if d < 0.6:
                # Pupil
                g.set(x, y, PUPIL_COLOR)
            elif d < 1.5:
                # Iris
                g.set(x, y, iris_color)
            elif d < 2.5:
                # Eye white
                g.set(x, y, WHITE_COLOR)
            else:
                # Outside eye
                g.set(x, y, EYELID_COLOR)

    # Specular highlight - always top-right of pupil
    hx = int(cx + 0.7)
    hy = int(cy - 0.7)
    if 0 <= hx < 5 and 0 <= hy < 5:
        g.set(hx, hy, HIGHLIGHT_COLOR)

    return g


def eye_half_closed(look_x=0.0, look_y=0.5, iris_color=IRIS_COLOR):
    """Half-closed eye (sleepy or suspicious)."""
    g = eye_open(look_x, look_y, iris_color)
    # Close top row
    for x in range(5):
        g.set(x, 0, EYELID_COLOR)
    return g


def eye_closed():
    """Fully closed eye (blink frame)."""
    g = Grid()
    # Single line across the middle
    for x in range(5):
        g.set(x, 2, (30, 30, 30))
    return g


def eye_blink_top():
    """Eyelid coming down - mid-blink."""
    g = Grid()
    for x in range(5):
        g.set(x, 0, EYELID_COLOR)
        g.set(x, 1, EYELID_COLOR)
        g.set(x, 2, (80, 80, 80))  # lash line
    # Peek of eye below
    for x in range(1, 4):
        g.set(x, 3, WHITE_COLOR)
    return g


def eye_wide(look_x=0.0, look_y=0.0, iris_color=IRIS_COLOR):
    """Wide open surprised eye."""
    g = Grid()

    cx = 2.0 + look_x * 0.8
    cy = 2.0 + look_y * 0.5

    for y in range(5):
        for x in range(5):
            d = _distance(x, y, cx, cy)

            if d < 0.5:
                g.set(x, y, PUPIL_COLOR)
            elif d < 1.2:
                # Smaller iris = more white visible = surprised
                g.set(x, y, iris_color)
            else:
                # All white - wide open
                g.set(x, y, WHITE_COLOR)

    hx = int(cx + 0.7)
    hy = int(cy - 0.7)
    if 0 <= hx < 5 and 0 <= hy < 5:
        g.set(hx, hy, HIGHLIGHT_COLOR)

    return g


def eye_squint(look_x=0.0, iris_color=IRIS_COLOR):
    """Squinting eye (bright light or suspicious)."""
    g = Grid()
    # Top two and bottom two rows closed
    for x in range(5):
        g.set(x, 0, EYELID_COLOR)
        g.set(x, 1, EYELID_COLOR)
        g.set(x, 3, EYELID_COLOR)
        g.set(x, 4, EYELID_COLOR)
    # Only middle row visible
    cx = 2.0 + look_x * 1.0
    for x in range(5):
        d = abs(x - cx)
        if d < 0.6:
            g.set(x, 2, PUPIL_COLOR)
        elif d < 1.5:
            g.set(x, 2, iris_color)
        else:
            g.set(x, 2, WHITE_COLOR)
    return g


def eye_supernova(phase, iris_color=IRIS_COLOR):
    """
    Internal supernova - eye pulses with energy radiating from center.
    phase: 0.0 to 1.0 (animation progress)
    """
    g = Grid()

    # Expanding ring of light
    ring_radius = phase * 3.5
    ring_width = 0.8

    for y in range(5):
        for x in range(5):
            d = _distance(x, y, 2, 2)

            # Core glow
            core_intensity = max(0, 1.0 - d * 0.4) * (1.0 - phase * 0.5)

            # Ring
            ring_dist = abs(d - ring_radius)
            ring_intensity = max(0, 1.0 - ring_dist / ring_width) if ring_radius > 0.5 else 0

            intensity = min(1.0, core_intensity + ring_intensity)

            # Color shifts from iris color to white at peak
            cr, cg, cb = iris_color
            r = int(cr + (255 - cr) * intensity)
            g_val = int(cg + (255 - cg) * intensity * 0.8)
            b = int(cb + (255 - cb) * intensity * 0.6)

            g.set(x, y, (min(255, r), min(255, g_val), min(255, b)))

    return g


def eye_spiral(phase, iris_color=IRIS_COLOR):
    """Hypnotic spiral pattern. phase: 0.0 to 1.0 (rotation)."""
    g = Grid()

    for y in range(5):
        for x in range(5):
            dx = x - 2.0
            dy = y - 2.0
            angle = math.atan2(dy, dx)
            dist = _distance(x, y, 2, 2)

            spiral = math.sin(angle * 2 + dist * 2 - phase * math.pi * 4)
            intensity = (spiral + 1) / 2

            cr, cg, cb = iris_color
            r = int(cr * intensity)
            g_val = int(cg * intensity)
            b = int(cb * intensity)

            g.set(x, y, (r, g_val, b))

    return g


def eye_heart():
    """Heart shape in the eye (love/affection)."""
    g = Grid()

    heart = [
        [0, 1, 0, 1, 0],
        [1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1],
        [0, 1, 1, 1, 0],
        [0, 0, 1, 0, 0],
    ]

    for y in range(5):
        for x in range(5):
            if heart[y][x]:
                g.set(x, y, (255, 20, 60))  # crimson red
            else:
                g.set(x, y, EYELID_COLOR)

    return g


def eye_x():
    """X marks - dead/stunned eyes."""
    g = Grid()

    for i in range(5):
        g.set(i, i, WHITE_COLOR)
        g.set(4 - i, i, WHITE_COLOR)

    return g


def eye_arrow(direction='left'):
    """Arrow pointing in a direction (indicating where to look)."""
    g = Grid()

    if direction == 'left':
        points = [(2, 0), (1, 1), (0, 2), (1, 3), (2, 4), (2, 2), (3, 2), (4, 2)]
    elif direction == 'right':
        points = [(2, 0), (3, 1), (4, 2), (3, 3), (2, 4), (2, 2), (1, 2), (0, 2)]
    else:
        points = []

    for x, y in points:
        g.set(x, y, WHITE_COLOR)

    return g


# Pre-built look directions for camera tracking
# Windows overlook park from high up, so default gaze is down
LOOK_POSITIONS = {
    'far_left':     (-1.0,  0.5),
    'left':         (-0.5,  0.5),
    'center':       ( 0.0,  0.5),
    'right':        ( 0.5,  0.5),
    'far_right':    ( 1.0,  0.5),
    'up_left':      (-0.5, -0.3),
    'up':           ( 0.0, -0.5),
    'up_right':     ( 0.5, -0.3),
    'down_left':    (-0.5,  1.0),
    'down':         ( 0.0,  1.0),
    'down_right':   ( 0.5,  1.0),
}


def look_at(position_name, iris_color=IRIS_COLOR):
    """Look at a named position."""
    x, y = LOOK_POSITIONS.get(position_name, (0.0, 0.5))
    return eye_open(x, y, iris_color)


def look_at_xy(x_norm, y_norm, iris_color=IRIS_COLOR):
    """
    Look at normalized coordinates from camera input.
    x_norm: 0.0 (left edge of frame) to 1.0 (right edge)
    y_norm: 0.0 (top) to 1.0 (bottom)

    Maps camera coordinates to eye look direction.
    Since windows are high up overlooking a park,
    most action is below and in front.
    """
    look_x = (x_norm - 0.5) * 2.0   # -1 to 1
    look_y = (y_norm - 0.3) * 1.5   # slightly biased down
    look_y = max(-0.5, min(1.0, look_y))
    return eye_open(look_x, look_y, iris_color)
