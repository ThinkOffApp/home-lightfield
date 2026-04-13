"""
Eye animation engine - plays sequences on the blinders via Art-Net.

Usage:
    python engine.py                    # idle scan mode
    python engine.py --demo             # demo all expressions
    python engine.py --expression blink # play single expression
"""

import socket
import struct
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from grid import Grid
from expressions import *
from sequences import *

ARTNET_HEADER = b'Art-Net\x00'
OPCODE_OUTPUT = 0x5000

# Art-Net config
BIND_IP = '2.0.0.5'
TARGETS = [f'2.0.0.{i}' for i in range(11, 23)] + ['2.0.0.201', '2.0.0.202']
BLINDER_UNIVERSE = (1 << 4) | 14  # subnet 1, universe 14

# DMX channel mapping from Resolume:
# Right blinder: channels 4-78 (25 px × 3 ch)
# Left blinder: channels 101-175 (25 px × 3 ch)
RIGHT_BLINDER_OFFSET = 3   # 0-indexed start (channel 4)
LEFT_BLINDER_OFFSET = 100  # 0-indexed start (channel 101)

BRIGHTNESS = 0.8  # default brightness


def build_dmx_frame(left_grid, right_grid, brightness=BRIGHTNESS):
    """Build a 512-byte DMX frame from two 5x5 grids."""
    dmx = bytearray(512)

    # Channels 1-3: dimmer (set to full, brightness handled per-pixel)
    dmx[0] = 255
    dmx[1] = 255
    dmx[2] = 255

    # Right blinder
    right_data = right_grid.to_dmx()
    for i, val in enumerate(right_data):
        dmx[RIGHT_BLINDER_OFFSET + i] = int(val * brightness)

    # Left blinder
    left_data = left_grid.to_dmx()
    for i, val in enumerate(left_data):
        dmx[LEFT_BLINDER_OFFSET + i] = int(val * brightness)

    return dmx


def send_frame(sock, dmx):
    """Send a DMX frame via Art-Net.
    Sends on the blinder universe plus extra universes to ensure
    the left blinder's node (which needs broadcast-style flooding) receives data."""
    # Send on the primary blinder universe and a few extras
    # The left blinder only responds when all nodes get data on multiple universes
    universes_to_send = [
        BLINDER_UNIVERSE,           # subnet 1, uni 14 (primary)
        (0 << 4) | 14,             # subnet 0, uni 14
        (1 << 4) | 15,             # subnet 1, uni 15
    ]

    for uni in universes_to_send:
        packet = bytearray()
        packet += ARTNET_HEADER
        packet += struct.pack('<H', OPCODE_OUTPUT)
        packet += struct.pack('>H', 14)   # protocol version
        packet += struct.pack('B', 0)     # sequence
        packet += struct.pack('B', 0)     # physical
        packet += struct.pack('<H', uni)
        packet += struct.pack('>H', 512)
        packet += dmx

        for target in TARGETS:
            sock.sendto(packet, (target, 6454))


def play_sequence(sock, sequence, brightness=BRIGHTNESS):
    """Play an animation sequence on the blinders."""
    for left_grid, right_grid, duration_ms in sequence:
        dmx = build_dmx_frame(left_grid, right_grid, brightness)
        send_frame(sock, dmx)
        time.sleep(duration_ms / 1000.0)


def demo_all(sock):
    """Demo all expressions and sequences."""
    print("=== Eye Animation Demo ===\n")

    demos = [
        ("Open - center",      lambda: [(eye_open(), eye_open(), 1500)]),
        ("Open - look left",   lambda: [(eye_open(-1, 0.5), eye_open(-1, 0.5), 1500)]),
        ("Open - look right",  lambda: [(eye_open(1, 0.5), eye_open(1, 0.5), 1500)]),
        ("Open - look down",   lambda: [(eye_open(0, 1), eye_open(0, 1), 1500)]),
        ("Blink",              lambda: blink()),
        ("Double blink",       lambda: double_blink()),
        ("Slow blink",         lambda: slow_blink()),
        ("Wide/surprised",     lambda: surprise()),
        ("Squint left",        lambda: suspicious('left')),
        ("Scan L to R",        lambda: look_left_to_right(2.0)),
        ("Scan R to L",        lambda: look_right_to_left(2.0)),
        ("Supernova",          lambda: supernova_burst()),
        ("Hypnotize",          lambda: hypnotize(3.0)),
        ("Heart eyes",         lambda: love()),
        ("Dead eyes",          lambda: death()),
        ("Wink right",         lambda: wink('right')),
        ("Independent look",   lambda: independent_look((-0.8, 0.5), (0.8, 0.5))),
    ]

    for name, seq_fn in demos:
        print(f"  Playing: {name}")
        play_sequence(sock, seq_fn())
        time.sleep(0.5)

    print("\n=== Demo complete ===")


def blackout(sock):
    """Turn off blinders."""
    dmx = bytearray(512)
    send_frame(sock, dmx)


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((BIND_IP, 0))

    try:
        if '--demo' in sys.argv:
            demo_all(sock)
        elif '--expression' in sys.argv:
            idx = sys.argv.index('--expression')
            name = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else 'blink'
            seq_map = {
                'blink': blink,
                'double_blink': double_blink,
                'slow_blink': slow_blink,
                'surprise': surprise,
                'supernova': supernova_burst,
                'hypnotize': lambda: hypnotize(5.0),
                'love': love,
                'death': death,
                'idle': lambda: idle_scan(60.0),
                'scan_lr': look_left_to_right,
                'scan_rl': look_right_to_left,
            }
            if name in seq_map:
                print(f"Playing: {name}")
                play_sequence(sock, seq_map[name]())
            else:
                print(f"Unknown expression: {name}")
                print(f"Available: {', '.join(seq_map.keys())}")
        elif '--idle' in sys.argv:
            print("Idle eye scan mode... Ctrl+C to stop")
            while True:
                play_sequence(sock, idle_scan(30.0))
        else:
            print("Eye animation engine")
            print("  --demo          Run all expressions")
            print("  --expression X  Play single expression")
            print("  --idle          Idle scanning loop")
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        blackout(sock)
        sock.close()


if __name__ == '__main__':
    main()
