import socket, struct, time

ARTNET_HEADER = b'Art-Net\x00'
OPCODE_OUTPUT = 0x5000

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.bind(('', 0))

targets = ['255.255.255.255']

print('Setting BOTH blinders to steady pink based on engine.py offsets...')

def make_packet(universe, dimmer_offset, pixel_offset, num_dimmers):
    dmx = bytearray(512)
    # Set dimmer/mode channels to full 255 to enable output
    for i in range(num_dimmers):
        dmx[dimmer_offset + i] = 255
    
    # Set 25 RGB pixels to steady pink
    for i in range(25):
        idx = pixel_offset + i * 3
        dmx[idx]     = 255 # R
        dmx[idx + 1] = 105 # G
        dmx[idx + 2] = 180 # B
        
    packet = bytearray()
    packet += ARTNET_HEADER
    packet += struct.pack('<H', OPCODE_OUTPUT)
    packet += struct.pack('>H', 14)
    packet += struct.pack('B', 0)
    packet += struct.pack('B', 0)
    packet += struct.pack('<H', universe)
    packet += struct.pack('>H', 512)
    packet += dmx
    return packet

# Match engine.py config:
# Right blinder: Universe 14, dimmers at 0-2, pixels at 3-77
right_packet = make_packet((1 << 4) | 14, 0, 3, 3)

# Left blinder (Pixel Octo): Universe 1, dimmers at 100-101, pixels at 103-177
left_packet  = make_packet((1 << 4) | 1, 100, 103, 2)

try:
    while True:
        for target in targets:
            sock.sendto(right_packet, (target, 6454))
            sock.sendto(left_packet, (target, 6454))
        time.sleep(1.0 / 40.0)
except KeyboardInterrupt:
    pass
