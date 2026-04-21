"""
Eye animation engine - plays sequences on the blinders via Art-Net.

Usage:
    python engine.py                    # idle scan mode
    python engine.py --demo             # demo all expressions
    python engine.py --expression blink # play single expression

Both blinders receive data via unicast AND broadcast to ensure delivery.
The left blinder's ODE node may sit on a 169.254.x.x link-local address
and can only be reached via broadcast on the physical LAN segment.
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
# Default bind: Dell's Art-Net NIC. Use 0.0.0.0 to bind on any machine.
BIND_IP = os.environ.get('ARTNET_BIND', '0.0.0.0')

# Right blinder: ODE Mk2 at 2.0.0.202, subnet 1 universe 14
RIGHT_NODE = '2.0.0.202'
RIGHT_UNIVERSE = (1 << 4) | 14    # 0x1E

# Left blinder: ODE Mk2 at 2.0.0.201, subnet 1 universe 15
LEFT_NODE = '2.0.0.201'
LEFT_UNIVERSE = (1 << 4) | 15     # 0x1F

# Broadcast address - reaches ALL nodes on the physical LAN regardless of IP subnet
# This is critical for the left blinder whose node may be at 169.254.x.x
BROADCAST_ADDR = '2.255.255.255'

BRIGHTNESS = float(os.environ.get('ARTNET_BRIGHTNESS', '0.01'))  # 1% default

# Frame rate - higher = steadier output, prevents Art-Net timeout blinking
FPS = int(os.environ.get('ARTNET_FPS', '25'))

# Sequence counter for Art-Net packets (wraps at 256)
_seq = 0


def _next_seq():
    global _seq
    _seq = (_seq + 1) % 256
    return _seq


def _build_artnet_packet(universe, dmx_data):
    """Build a single Art-Net DMX512 packet."""
    seq = _next_seq()
    packet = bytearray()
    packet += ARTNET_HEADER
    packet += struct.pack('<H', OPCODE_OUTPUT)
    packet += struct.pack('>H', 14)       # protocol version
    packet += struct.pack('BB', seq, 0)   # sequence, physical
    packet += struct.pack('<H', universe)
    packet += struct.pack('>H', len(dmx_data))
    packet += dmx_data
    return bytes(packet)


def build_dmx_frames(left_grid, right_grid, brightness=None):
    """Build a shared 512-byte DMX frame with BOTH blinders.

    Layout (matching Resolume/artnet_eyes_final.py):
      ch 1-3:    right blinder dimmer (255, 255, 255)
      ch 4-78:   right blinder 25 RGB pixels (75 bytes)
      ch 101-102: left blinder dimmer (255, 255)
      ch 104-178: left blinder 25 RGB pixels (75 bytes)
      All other channels zero (spots stay off).

    Returns (shared_frame, shared_frame) for API compat — same frame
    is sent on both uni14 and uni15.
    """
    if brightness is None:
        brightness = BRIGHTNESS

    right_px = right_grid.to_dmx()  # 75 bytes, linear order
    left_px = left_grid.to_dmx()

    dmx = bytearray(512)

    # Right blinder: ch 1-3 dimmer, ch 4-78 pixels
    dmx[0] = 255
    dmx[1] = 255
    dmx[2] = 255
    for i in range(75):
        dmx[3 + i] = int(right_px[i] * brightness)

    # Left blinder: ch 101-102 dimmer, ch 104-178 pixels
    dmx[100] = 255
    dmx[101] = 255
    for i in range(75):
        dmx[103 + i] = int(left_px[i] * brightness)

    return dmx, dmx  # same frame for both universes


# Keepalive for DMX chain node (Pixel Octo 19)
_CHAIN_NODE = '2.0.0.19'
_CHAIN_UNIVERSES = [0x0F, 0x10]  # sub0/uni15 + sub1/uni0
_empty = bytearray(512)


_DELL_RELAY = os.environ.get('ARTNET_RELAY', '192.168.50.217')
_DELL_RELAY_PORT = 6455
_relay_fail_count = 0


def send_frame(sock, left_dmx, right_dmx):
    """Send Art-Net DMX to both blinders via uni14 only.

    Both blinders share ONE 512-byte frame (right at ch 1-78, left at ch 101-178).
    Spots are on uni15 — we never send there, so they stay off.

    left_dmx and right_dmx are the same shared frame (see build_dmx_frames).
    """
    global _relay_fail_count
    # Only uni14 - shared frame for both blinders. Uni15 is spots, leave alone.
    pkt = _build_artnet_packet(RIGHT_UNIVERSE, right_dmx)
    try:
        sock.sendto(pkt, (_DELL_RELAY, _DELL_RELAY_PORT))
        _relay_fail_count = 0
    except OSError as e:
        _relay_fail_count += 1
        if _relay_fail_count == 1 or _relay_fail_count % 500 == 0:
            print(f'Art-Net relay send failed ({_relay_fail_count}x): {e}')


def play_sequence(sock, sequence, brightness=None):
    """Play an animation sequence on the blinders."""
    if brightness is None:
        brightness = BRIGHTNESS
    for left_grid, right_grid, duration_ms in sequence:
        left_dmx, right_dmx = build_dmx_frames(left_grid, right_grid, brightness)

        # Send multiple times within the frame duration to prevent timeout
        frame_time = duration_ms / 1000.0
        send_interval = 1.0 / FPS
        elapsed = 0
        while elapsed < frame_time:
            send_frame(sock, left_dmx, right_dmx)
            sleep_time = min(send_interval, frame_time - elapsed)
            time.sleep(sleep_time)
            elapsed += send_interval


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
        time.sleep(0.3)

    print("\n=== Demo complete ===")


def blackout(sock):
    """Turn off blinders."""
    dmx = bytearray(512)
    # Send blackout several times to ensure delivery
    for _ in range(10):
        send_frame(sock, dmx, dmx)
        time.sleep(0.05)


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    try:
        sock.bind((BIND_IP, 6454))
        print(f"Bound to {BIND_IP}:6454")
    except OSError as e:
        # If binding to 6454 fails (port in use), use any port
        # Art-Net source port doesn't need to be 6454
        sock.bind((BIND_IP, 0))
        port = sock.getsockname()[1]
        print(f"Port 6454 in use, bound to {BIND_IP}:{port}")

    print(f"Brightness: {BRIGHTNESS*100:.1f}%  FPS: {FPS}")
    print(f"Right: {RIGHT_NODE} uni {RIGHT_UNIVERSE:#04x}")
    print(f"Left:  {LEFT_NODE} uni {LEFT_UNIVERSE:#04x}")
    print(f"Broadcast: {BROADCAST_ADDR}")
    print()

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
                'ripple': lambda: ripple(5.0),
                'plasma': lambda: plasma(5.0),
                'pinwheel': lambda: pinwheel(5.0),
                'rain': lambda: color_rain(5.0),
                'kaleidoscope': lambda: kaleidoscope(5.0),
                'breathe': lambda: breathe(5.0),
                'tk_ripple': lambda: thinkoff_ripple(5.0),
                'tk_plasma': lambda: thinkoff_plasma(5.0),
                'tk_pinwheel': lambda: thinkoff_pinwheel(5.0),
                'tk_kaleidoscope': lambda: thinkoff_kaleidoscope(5.0),
                'tk_spiral': lambda: thinkoff_spiral(5.0),
                'pf_ripple': lambda: pink_fuchsia_ripple(5.0),
                'pf_plasma': lambda: pink_fuchsia_plasma(5.0),
                'pf_spiral': lambda: pink_fuchsia_spiral(5.0),
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
        elif '--test' in sys.argv:
            # Quick test: all white on both blinders for 5 seconds
            print("TEST: All white on both blinders for 5 seconds...")
            g = Grid()
            g.clear((255, 255, 255))
            left_dmx, right_dmx = build_dmx_frames(g, g)
            start = time.time()
            while time.time() - start < 5:
                send_frame(sock, left_dmx, right_dmx)
                time.sleep(1.0 / FPS)
            print("Test complete.")
        else:
            print("Eye animation engine")
            print("  --demo          Run all expressions")
            print("  --expression X  Play single expression")
            print("  --idle          Idle scanning loop")
            print("  --test          White test pattern (5s)")
            print()
            print("Environment variables:")
            print("  ARTNET_BIND=0.0.0.0     Bind address")
            print("  ARTNET_BRIGHTNESS=0.01  Brightness (0-1)")
            print("  ARTNET_FPS=25           Frame rate")
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        blackout(sock)
        sock.close()


if __name__ == '__main__':
    main()
