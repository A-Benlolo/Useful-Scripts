import time
import os
import signal
import socket
import struct
import sys

TIMEOUT_SECONDS = 5 * 60
CHECK_INTERVAL = 5

def handle_exit(signun, frame):
    sys.exit(0)

def main():
    # Setup the listening socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket. IPPROTO_ICMP)
    except PermissionError:
        print('Missing permissions!')
        sys.exit(1)
    sock.setblocking(False)

    # Listen forever...
    last_ping_time = None
    while True:
        # Drain all existing ping requests
        print('standby')
        packet = None
        while True:
            try: packet, _ = sock.recvfrom(65535)
            except: break

        # If there any requests, parse the latest
        if packet is not None:
            icmp_header = packet[20:28]
            icmp_type, _, _, _, _ = struct.unpack('!BBHHH',icmp_header)
            if icmp_type == 8:
                last_ping_time = time.time()
            print('    heard')
        else:
            print('    nothing')

        # Shutdown if a request has been seen before but has not been seen in a while
        if last_ping_time is not None:
            if time.time() - last_ping_time > TIMEOUT_SECONDS:
                print('    die!!!')
                time.sleep(CHECK_INTERVAL)
                os.system('shutdown -h now')
            else:
                print(f'    alive ({time.time() - last_ping_time})')
        else:
            print('    unintialized')

        # Wait before repeating
        time.sleep(CHECK_INTERVAL)

    return

if __name__ == '__main__':
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    main()
