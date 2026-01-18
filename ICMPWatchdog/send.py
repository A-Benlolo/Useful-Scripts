import time
import os
import signal
import socket
import struct
import sys
import select

TIMEOUT_SECONDS = 5 * 60
CHECK_INTERVAL = 5
PING_DEST = 'REDACTED' # TODO: Replace with canary IP address
ICMP_ECHO_REQUEST = 8
ICMP_ECHO_REPLY = 0
IDENT = os.getpid() & 0xFFFF
SEQ = 0

def handle_exit(signum, frame):
    sys.exit(0)

def checksum(data):
    s = 0
    for i in range(0, len(data) - 1, 2):
        s += (data[i] << 8) + data[i + 1]
    if len(data) % 2:
        s += data[-1] << 8
    s = (s >> 16) + (s & 0xffff)
    s += s >> 16
    return ~s & 0xffff

def build_packet(seq):
    header = struct.pack('!BBHHH',
        ICMP_ECHO_REQUEST, 0, 0, IDENT, seq)
    payload = b'ping'
    chksum = checksum(header + payload)
    return struct.pack('!BBHHH',
        ICMP_ECHO_REQUEST, 0, chksum, IDENT, seq) + payload

def main():
    # Setup the socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    except PermissionError:
        print('Missing permissions!')
        sys.exit(1)

    sock.setblocking(False)
    addr = socket.gethostbyname(PING_DEST)

    # Listen forever...
    last_reply_time = None
    global SEQ

    while True:
        print('standby')

        # Send an echo request
        packet = build_packet(SEQ)
        SEQ += 1
        sock.sendto(packet, (addr, 1))

        # Drain all existing replies
        reply = None
        start = time.time()
        while time.time() - start < 1:
            r, _, _ = select.select([sock], [], [], 0)
            if not r:
                break
            try:
                reply, _ = sock.recvfrom(65535)
            except:
                break

        # If there was a reply, parse the latest
        if reply is not None:
            icmp_header = reply[20:28]
            icmp_type, _, _, ident, _ = struct.unpack('!BBHHH', icmp_header)
            if icmp_type == ICMP_ECHO_REPLY and ident == IDENT:
                last_reply_time = time.time()
                print('    heard')
            else:
                print('    garbage')
        else:
            print('    nothing')

        # Shutdown if a reply has been seen before but has not been seen in a while
        if last_reply_time is not None:
            if time.time() - last_reply_time > TIMEOUT_SECONDS:
                print('    die!!!')
                time.sleep(CHECK_INTERVAL)
                os.system('shutdown -h now')
            else:
                print(f'    alive ({time.time() - last_reply_time})')
        else:
            print('    uninitialized')

        # Wait before repeating
        time.sleep(CHECK_INTERVAL)

    return

if __name__ == '__main__':
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    main()
