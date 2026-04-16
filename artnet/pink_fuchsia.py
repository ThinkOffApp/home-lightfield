import socket, struct, time, math

ARTNET_HEADER = b'Art-Net\x00'
OPCODE_OUTPUT = 0x5000

targets = [f'2.0.0.{i}' for i in range(11, 23)] + ['2.0.0.201', '2.0.0.202']

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('2.0.0.5', 0))

DIM = 0.20
GAMMA = 2.5

def gc(v):
    """Gamma correct then dim - apply gamma at full range, THEN scale down"""
    if v <= 0:
        return 0
    corrected = 255 * (v / 255.0) ** GAMMA
    return int(corrected * DIM)

universes = []
for subnet in [0, 1]:
    for uni in range(16):
        universes.append((subnet << 4) | uni)

print(f'Pulsing pink <-> fuchsia, strips gamma-corrected at {int(DIM*100)}%, no blinders')

fps = 20
t = 0
try:
    while True:
        phase = (math.sin(t * 0.5) + 1) / 2

        # Full range colors (0-255)
        r_full = 255
        g_full = int(105 * (1 - phase))
        b_full = int(180 + 75 * phase)

        # Dimmed raw values for spots
        r = int(r_full * DIM)
        g = int(g_full * DIM)
        b = int(b_full * DIM)

        # RGBW for strips: gamma correct at full range then dim
        rg, gg, bg = gc(r_full), gc(g_full), gc(b_full)
        dmx_rgbw = bytearray(512)
        for ch in range(0, 508, 4):
            dmx_rgbw[ch] = rg
            dmx_rgbw[ch+1] = gg
            dmx_rgbw[ch+2] = bg
            dmx_rgbw[ch+3] = 0

        # Blinders: OFF
        dmx_rgb = bytearray(512)

        # Spots: RGBW, raw dimmed values
        dmx_spots = bytearray(512)
        for spot in range(6):
            base = spot * 4
            dmx_spots[base] = r
            dmx_spots[base+1] = g
            dmx_spots[base+2] = b
            dmx_spots[base+3] = 0

        for ub in universes:
            subnet = (ub >> 4) & 0xF
            uni = ub & 0xF

            if subnet == 1 and uni in (14, 15):
                dmx = dmx_rgb  # blinders OFF
            elif subnet == 0 and uni == 13:
                dmx = dmx_spots
            else:
                dmx = dmx_rgbw

            packet = bytearray()
            packet += ARTNET_HEADER
            packet += struct.pack('<H', OPCODE_OUTPUT)
            packet += struct.pack('>H', 14)
            packet += struct.pack('B', 0)
            packet += struct.pack('B', 0)
            packet += struct.pack('<H', ub)
            packet += struct.pack('>H', 512)
            packet += dmx

            for target in targets:
                sock.sendto(packet, (target, 6454))

        t += 1.0 / fps
        time.sleep(1.0 / fps)

except KeyboardInterrupt:
    print('\nBlackout...')
    dmx_off = bytearray(512)
    for ub in universes:
        packet = bytearray()
        packet += ARTNET_HEADER
        packet += struct.pack('<H', OPCODE_OUTPUT)
        packet += struct.pack('>H', 14)
        packet += struct.pack('B', 0)
        packet += struct.pack('B', 0)
        packet += struct.pack('<H', ub)
        packet += struct.pack('>H', 512)
        packet += dmx_off
        for target in targets:
            sock.sendto(packet, (target, 6454))
    print('Done')

sock.close()
