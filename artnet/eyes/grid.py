"""
5x5 RGB pixel grid abstraction for Cameo Matrix 300 blinders.

Each blinder is a 5x5 grid of RGB pixels.
Layout (looking at the blinder from outside):

  (0,0) (1,0) (2,0) (3,0) (4,0)
  (0,1) (1,1) (2,1) (3,1) (4,1)
  (0,2) (1,2) (2,2) (3,2) (4,2)
  (0,3) (1,3) (2,3) (3,3) (4,3)
  (0,4) (1,4) (2,4) (3,4) (4,4)

Distribution mode 170 = snake/zigzag pattern.
Row 0: left to right (0,1,2,3,4)
Row 1: right to left (4,3,2,1,0)
Row 2: left to right ...
"""

class Grid:
    """5x5 RGB pixel grid"""

    def __init__(self):
        self.pixels = [[(0, 0, 0) for _ in range(5)] for _ in range(5)]

    def clear(self, color=(0, 0, 0)):
        for y in range(5):
            for x in range(5):
                self.pixels[y][x] = color

    def set(self, x, y, color):
        if 0 <= x < 5 and 0 <= y < 5:
            self.pixels[y][x] = color

    def get(self, x, y):
        if 0 <= x < 5 and 0 <= y < 5:
            return self.pixels[y][x]
        return (0, 0, 0)

    def set_brightness(self, brightness):
        """Scale all pixels by brightness (0.0 - 1.0)"""
        for y in range(5):
            for x in range(5):
                r, g, b = self.pixels[y][x]
                self.pixels[y][x] = (
                    int(r * brightness),
                    int(g * brightness),
                    int(b * brightness)
                )

    def blend(self, other, factor):
        """Blend with another grid. factor=0 means self, factor=1 means other."""
        result = Grid()
        for y in range(5):
            for x in range(5):
                r1, g1, b1 = self.pixels[y][x]
                r2, g2, b2 = other.pixels[y][x]
                result.pixels[y][x] = (
                    int(r1 * (1 - factor) + r2 * factor),
                    int(g1 * (1 - factor) + g2 * factor),
                    int(b1 * (1 - factor) + b2 * factor)
                )
        return result

    def to_dmx(self):
        """Convert to 75-byte DMX data (25 pixels × 3 channels RGB).
        Linear order: left to right, top to bottom (no snake).
        This matches the Resolume/artnet_eyes_final.py layout."""
        data = bytearray(75)
        for y in range(5):
            for x in range(5):
                idx = (y * 5 + x) * 3
                r, g, b = self.pixels[y][x]
                data[idx] = min(255, max(0, r))
                data[idx + 1] = min(255, max(0, g))
                data[idx + 2] = min(255, max(0, b))
        return data

    def __repr__(self):
        lines = []
        for y in range(5):
            row = []
            for x in range(5):
                r, g, b = self.pixels[y][x]
                if r + g + b == 0:
                    row.append('  .  ')
                else:
                    row.append(f'{r:02x}{g:02x}{b:02x}')
            lines.append(' '.join(row))
        return '\n'.join(lines)
