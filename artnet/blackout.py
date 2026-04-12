import socket, struct, time
ARTNET_HEADER = b'Art-Net\x00'
OPCODE_OUTPUT = 0x5000
dmx_data = bytearray(512)
targets = [f'2.0.0.{i}' for i in range(11, 23)] + ['2.0.0.201', '2.0.0.202']
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('2.0.0.5', 0))
for _ in range(10):
    for subnet in [0, 1]:
        for uni in range(16):
            ub = (subnet << 4) | uni
            packet = bytearray()
            packet += ARTNET_HEADER
            packet += struct.pack('<H', OPCODE_OUTPUT)
            packet += struct.pack('>H', 14)
            packet += struct.pack('B', 0)
            packet += struct.pack('B', 0)
            packet += struct.pack('<H', ub)
            packet += struct.pack('>H', 512)
            packet += dmx_data
            for target in targets:
                sock.sendto(packet, (target, 6454))
    time.sleep(0.1)
print('All DMX blackout')
sock.close()
