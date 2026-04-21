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

# ThinkOff brand palette (7 colors, from heart logo center outward)
TK_WHITE   = (255, 255, 255)    # innermost core
TK_BLUE    = (96, 165, 250)     # bright blue
TK_INDIGO  = (165, 180, 252)    # indigo accent
TK_MAGENTA = (217, 70, 239)     # magenta accent
TK_CORE    = (212, 165, 233)    # primary brand pink
TK_MID     = (232, 197, 245)    # mid-tone pink
TK_EDGE    = (240, 208, 248)    # palest pink

THINKOFF_PALETTE = [TK_WHITE, TK_BLUE, TK_INDIGO, TK_MAGENTA, TK_CORE, TK_MID, TK_EDGE]

# Pink-fuchsia-purple gradient
PINK_FUCHSIA = [
    (255, 105, 180),   # hot pink
    (255, 0, 255),     # fuchsia
    (217, 70, 239),    # magenta
    (186, 85, 211),    # medium orchid
    (148, 0, 211),     # dark violet
    (128, 0, 128),     # purple
]


def _distance(x1, y1, x2, y2):
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def eye_open(look_x=0.0, look_y=0.5, iris_color=IRIS_COLOR,
             pupil_color=PUPIL_COLOR, white_color=WHITE_COLOR,
             eyelid_color=EYELID_COLOR):
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
                g.set(x, y, pupil_color)
            elif d < 1.5:
                # Iris
                g.set(x, y, iris_color)
            elif d < 2.5:
                # Eye white
                g.set(x, y, white_color)
            else:
                # Outside eye
                g.set(x, y, eyelid_color)

    # Specular highlight - always top-right of pupil
    hx = int(cx + 0.7)
    hy = int(cy - 0.7)
    if 0 <= hx < 5 and 0 <= hy < 5:
        g.set(hx, hy, HIGHLIGHT_COLOR)

    return g


def eye_half_closed(look_x=0.0, look_y=0.5, iris_color=IRIS_COLOR,
                    pupil_color=PUPIL_COLOR, white_color=WHITE_COLOR,
                    eyelid_color=EYELID_COLOR):
    """Half-closed eye (sleepy or suspicious)."""
    g = eye_open(look_x, look_y, iris_color, pupil_color, white_color, eyelid_color)
    # Close top row
    for x in range(5):
        g.set(x, 0, eyelid_color)
    return g


def eye_closed(eyelid_color=EYELID_COLOR):
    """Fully closed eye (blink frame)."""
    g = Grid()
    g.clear(eyelid_color)
    # Single line across the middle - dim lash line
    for x in range(5):
        g.set(x, 2, (30, 30, 30))
    return g


def eye_blink_top(white_color=WHITE_COLOR, eyelid_color=EYELID_COLOR):
    """Eyelid coming down - mid-blink."""
    g = Grid()
    for x in range(5):
        g.set(x, 0, eyelid_color)
        g.set(x, 1, eyelid_color)
        g.set(x, 2, (80, 80, 80))  # lash line
    # Peek of eye below
    for x in range(1, 4):
        g.set(x, 3, white_color)
    return g


def eye_wide(look_x=0.0, look_y=0.0, iris_color=IRIS_COLOR,
             pupil_color=PUPIL_COLOR, white_color=WHITE_COLOR):
    """Wide open surprised eye."""
    g = Grid()

    cx = 2.0 + look_x * 0.8
    cy = 2.0 + look_y * 0.5

    for y in range(5):
        for x in range(5):
            d = _distance(x, y, cx, cy)

            if d < 0.5:
                g.set(x, y, pupil_color)
            elif d < 1.2:
                # Smaller iris = more white visible = surprised
                g.set(x, y, iris_color)
            else:
                # All white - wide open
                g.set(x, y, white_color)

    hx = int(cx + 0.7)
    hy = int(cy - 0.7)
    if 0 <= hx < 5 and 0 <= hy < 5:
        g.set(hx, hy, HIGHLIGHT_COLOR)

    return g


def eye_squint(look_x=0.0, iris_color=IRIS_COLOR,
               pupil_color=PUPIL_COLOR, white_color=WHITE_COLOR,
               eyelid_color=EYELID_COLOR):
    """Squinting eye (bright light or suspicious)."""
    g = Grid()
    # Top two and bottom two rows closed
    for x in range(5):
        g.set(x, 0, eyelid_color)
        g.set(x, 1, eyelid_color)
        g.set(x, 3, eyelid_color)
        g.set(x, 4, eyelid_color)
    # Only middle row visible
    cx = 2.0 + look_x * 1.0
    for x in range(5):
        d = abs(x - cx)
        if d < 0.6:
            g.set(x, 2, pupil_color)
        elif d < 1.5:
            g.set(x, 2, iris_color)
        else:
            g.set(x, 2, white_color)
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


def eye_heart(heart_color=(255, 20, 60), eyelid_color=EYELID_COLOR):
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
                g.set(x, y, heart_color)
            else:
                g.set(x, y, eyelid_color)

    return g


def eye_x(x_color=WHITE_COLOR, eyelid_color=EYELID_COLOR):
    """X marks - dead/stunned eyes."""
    g = Grid()
    g.clear(eyelid_color)

    for i in range(5):
        g.set(i, i, x_color)
        g.set(4 - i, i, x_color)

    return g


def eye_arrow(direction='left', arrow_color=WHITE_COLOR, eyelid_color=EYELID_COLOR):
    """Arrow pointing in a direction (indicating where to look)."""
    g = Grid()
    g.clear(eyelid_color)

    if direction == 'left':
        points = [(2, 0), (1, 1), (0, 2), (1, 3), (2, 4), (2, 2), (3, 2), (4, 2)]
    elif direction == 'right':
        points = [(2, 0), (3, 1), (4, 2), (3, 3), (2, 4), (2, 2), (1, 2), (0, 2)]
    else:
        points = []

    for x, y in points:
        g.set(x, y, arrow_color)

    return g


def eye_ripple(phase, colors=THINKOFF_PALETTE):
    """Concentric ripple rings radiating from center with dark gaps.
    phase: 0.0 to 1.0 (animation progress)."""
    g = Grid()
    n = len(colors)
    for y in range(5):
        for x in range(5):
            d = _distance(x, y, 2, 2)
            wave = math.sin((d - phase * 4) * 2.0)
            if wave < 0:
                g.set(x, y, (0, 0, 0))
            else:
                idx = int((d - phase * 4) * 1.5) % n
                cr, cg, cb = colors[idx]
                g.set(x, y, (int(cr * wave), int(cg * wave), int(cb * wave)))
    return g


def eye_plasma(phase, colors=THINKOFF_PALETTE):
    """Plasma-style interference with dark regions like spiral.
    phase: 0.0 to 1.0 (animation progress)."""
    g = Grid()
    n = len(colors)
    t = phase * math.pi * 2
    for y in range(5):
        for x in range(5):
            v1 = math.sin(x * 1.2 + t)
            v2 = math.sin(y * 1.4 + t * 0.7)
            v3 = math.sin(_distance(x, y, 2, 2) * 1.5 - t)
            v = (v1 + v2 + v3) / 3.0  # -1 to 1
            intensity = max(0, v)  # negative = dark
            idx = int(abs(v) * (n - 1) + 0.5) % n
            cr, cg, cb = colors[min(idx, n - 1)]
            g.set(x, y, (int(cr * intensity), int(cg * intensity), int(cb * intensity)))
    return g


def eye_pinwheel(phase, colors=THINKOFF_PALETTE, arms=3):
    """Spinning pinwheel with dark gaps between arms.
    phase: 0.0 to 1.0 (rotation), arms: number of pinwheel arms."""
    g = Grid()
    n = len(colors)
    t = phase * math.pi * 2
    for y in range(5):
        for x in range(5):
            dx = x - 2.0
            dy = y - 2.0
            angle = math.atan2(dy, dx) + t
            wave = math.sin(angle * arms)
            if wave < 0:
                g.set(x, y, (0, 0, 0))
            else:
                d = _distance(x, y, 2, 2)
                idx = int(d * 1.2) % n
                cr, cg, cb = colors[idx]
                g.set(x, y, (int(cr * wave), int(cg * wave), int(cb * wave)))
    return g


def eye_rain(phase, colors=THINKOFF_PALETTE):
    """Color rain drops falling with dark background.
    phase: 0.0 to 1.0 (animation progress)."""
    g = Grid()
    n = len(colors)
    for y in range(5):
        for x in range(5):
            wave = math.sin(y * 1.5 + x * 0.7 + phase * 8)
            if wave < 0.3:
                g.set(x, y, (0, 0, 0))
            else:
                intensity = (wave - 0.3) / 0.7
                idx = int(y + x * 0.7 + phase * 8) % n
                cr, cg, cb = colors[idx]
                g.set(x, y, (int(cr * intensity), int(cg * intensity), int(cb * intensity)))
    return g


def eye_kaleidoscope(phase, colors=THINKOFF_PALETTE):
    """Kaleidoscope mirror pattern with dark gaps.
    phase: 0.0 to 1.0 (rotation)."""
    g = Grid()
    n = len(colors)
    t = phase * math.pi * 2
    for y in range(5):
        for x in range(5):
            mx = abs(x - 2)
            my = abs(y - 2)
            angle = math.atan2(my, mx) + t
            dist = _distance(mx, my, 0, 0)
            v = math.sin(angle * 3 + dist * 2)
            intensity = max(0, v)  # half the time is dark
            idx = int((abs(v)) * (n - 1) + 0.5)
            cr, cg, cb = colors[min(idx, n - 1)]
            g.set(x, y, (int(cr * intensity), int(cg * intensity), int(cb * intensity)))
    return g


def eye_breathe(phase, color_a=TK_CORE, color_b=TK_MAGENTA):
    """Whole grid slowly crossfades between color_a and color_b.
    Never goes to black — smooth color breathing, no strobe.
    phase: 0.0 to 1.0 (breath cycle)."""
    g = Grid()
    t = (math.sin(phase * math.pi * 2) + 1) / 2  # 0 to 1 smooth
    # Crossfade between the two colors, held at ~60% minimum brightness
    r = int(color_a[0] * t + color_b[0] * (1 - t))
    gv = int(color_a[1] * t + color_b[1] * (1 - t))
    b = int(color_a[2] * t + color_b[2] * (1 - t))
    for y in range(5):
        for x in range(5):
            g.set(x, y, (r, gv, b))
    return g


# 5-pixel tall font for scrolling text (each char is 3-5 cols wide + 1 gap)
FONT_5X = {
    'A': [[0,1,0],[1,0,1],[1,1,1],[1,0,1],[1,0,1]],
    'B': [[1,1,0],[1,0,1],[1,1,0],[1,0,1],[1,1,0]],
    'C': [[0,1,1],[1,0,0],[1,0,0],[1,0,0],[0,1,1]],
    'D': [[1,1,0],[1,0,1],[1,0,1],[1,0,1],[1,1,0]],
    'E': [[1,1,1],[1,0,0],[1,1,0],[1,0,0],[1,1,1]],
    'F': [[1,1,1],[1,0,0],[1,1,0],[1,0,0],[1,0,0]],
    'G': [[0,1,1],[1,0,0],[1,0,1],[1,0,1],[0,1,1]],
    'H': [[1,0,1],[1,0,1],[1,1,1],[1,0,1],[1,0,1]],
    'I': [[1,1,1],[0,1,0],[0,1,0],[0,1,0],[1,1,1]],
    'J': [[0,0,1],[0,0,1],[0,0,1],[1,0,1],[0,1,0]],
    'K': [[1,0,1],[1,1,0],[1,0,0],[1,1,0],[1,0,1]],
    'L': [[1,0,0],[1,0,0],[1,0,0],[1,0,0],[1,1,1]],
    'M': [[1,0,0,0,1],[1,1,0,1,1],[1,0,1,0,1],[1,0,0,0,1],[1,0,0,0,1]],
    'N': [[1,0,0,1],[1,1,0,1],[1,0,1,1],[1,0,0,1],[1,0,0,1]],
    'O': [[0,1,0],[1,0,1],[1,0,1],[1,0,1],[0,1,0]],
    'P': [[1,1,0],[1,0,1],[1,1,0],[1,0,0],[1,0,0]],
    'Q': [[0,1,0],[1,0,1],[1,0,1],[1,1,0],[0,1,1]],
    'R': [[1,1,0],[1,0,1],[1,1,0],[1,0,1],[1,0,1]],
    'S': [[0,1,1],[1,0,0],[0,1,0],[0,0,1],[1,1,0]],
    'T': [[1,1,1],[0,1,0],[0,1,0],[0,1,0],[0,1,0]],
    'U': [[1,0,1],[1,0,1],[1,0,1],[1,0,1],[0,1,0]],
    'V': [[1,0,1],[1,0,1],[1,0,1],[0,1,0],[0,1,0]],
    'W': [[1,0,0,0,1],[1,0,0,0,1],[1,0,1,0,1],[1,1,0,1,1],[1,0,0,0,1]],
    'X': [[1,0,1],[0,1,0],[0,1,0],[0,1,0],[1,0,1]],
    'Y': [[1,0,1],[1,0,1],[0,1,0],[0,1,0],[0,1,0]],
    'Z': [[1,1,1],[0,0,1],[0,1,0],[1,0,0],[1,1,1]],
    '0': [[0,1,0],[1,0,1],[1,0,1],[1,0,1],[0,1,0]],
    '1': [[0,1,0],[1,1,0],[0,1,0],[0,1,0],[1,1,1]],
    '2': [[1,1,0],[0,0,1],[0,1,0],[1,0,0],[1,1,1]],
    '3': [[1,1,0],[0,0,1],[0,1,0],[0,0,1],[1,1,0]],
    '4': [[1,0,1],[1,0,1],[1,1,1],[0,0,1],[0,0,1]],
    '5': [[1,1,1],[1,0,0],[1,1,0],[0,0,1],[1,1,0]],
    '6': [[0,1,1],[1,0,0],[1,1,0],[1,0,1],[0,1,0]],
    '7': [[1,1,1],[0,0,1],[0,1,0],[0,1,0],[0,1,0]],
    '8': [[0,1,0],[1,0,1],[0,1,0],[1,0,1],[0,1,0]],
    '9': [[0,1,0],[1,0,1],[0,1,1],[0,0,1],[1,1,0]],
    ' ': [[0,0],[0,0],[0,0],[0,0],[0,0]],
    '!': [[1],[1],[1],[0],[1]],
    '?': [[1,1,0],[0,0,1],[0,1,0],[0,0,0],[0,1,0]],
    '.': [[0],[0],[0],[0],[1]],
    '-': [[0,0,0],[0,0,0],[1,1,1],[0,0,0],[0,0,0]],
    ':': [[0],[0],[1],[0],[1]],
    '+': [[0,0,0],[0,1,0],[1,1,1],[0,1,0],[0,0,0]],
}


def _text_to_columns(text):
    """Convert text string to list of pixel columns (each col is 5 pixels tall)."""
    columns = []
    for ch in text.upper():
        glyph = FONT_5X.get(ch, FONT_5X.get(' '))
        if glyph:
            char_cols = len(glyph[0])
            for col in range(char_cols):
                columns.append([glyph[row][col] for row in range(5)])
            columns.append([0, 0, 0, 0, 0])  # gap between chars
    return columns


def eye_scroll_text(text, offset, color=TK_CORE):
    """Render scrolling text at given column offset.
    offset: integer, scrolls right to left as offset increases."""
    g = Grid()
    columns = _text_to_columns(text)
    total = len(columns)
    for x in range(5):
        col_idx = (offset + x) % total if total > 0 else 0
        if col_idx < total:
            col = columns[col_idx]
            for y in range(5):
                if col[y]:
                    g.set(x, y, color)
    return g


def eye_scroll_text_wide(text, offset, color=TK_CORE):
    """Render scrolling text across both blinders (10 columns wide).
    Returns (left_grid, right_grid) tuple.
    offset: integer, scrolls right to left as offset increases."""
    left = Grid()
    right = Grid()
    columns = _text_to_columns(text)
    total = len(columns)
    if total == 0:
        return left, right
    for x in range(10):
        col_idx = (offset + x) % total
        col = columns[col_idx]
        for y in range(5):
            if col[y]:
                if x < 5:
                    left.set(x, y, color)
                else:
                    right.set(x - 5, y, color)
    return left, right


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


def look_at(position_name, iris_color=IRIS_COLOR,
            pupil_color=PUPIL_COLOR, white_color=WHITE_COLOR,
            eyelid_color=EYELID_COLOR):
    """Look at a named position."""
    x, y = LOOK_POSITIONS.get(position_name, (0.0, 0.5))
    return eye_open(x, y, iris_color, pupil_color, white_color, eyelid_color)


def look_at_xy(x_norm, y_norm, iris_color=IRIS_COLOR,
               pupil_color=PUPIL_COLOR, white_color=WHITE_COLOR,
               eyelid_color=EYELID_COLOR):
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
    return eye_open(look_x, look_y, iris_color, pupil_color, white_color, eyelid_color)
