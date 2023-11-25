"""
Where solution code to HW5 should be written.  No other files should
be modified.
"""

import socket
import io
import time
import typing
import struct
import homework5
import homework5.logging


def send(sock: socket.socket, data: bytes):
    logger = homework5.logging.get_logger("hw5-sender")
    chunk_size = homework5.MAX_PACKET - 4
    seq_number = 0
    window = []
    estimated_rtt = 1.0
    dev_rtt = 0.5
    alpha = 0.125
    beta = 0.25
    timeout = estimated_rtt + 4 * dev_rtt

    chunks = [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]

    while seq_number < len(chunks) or window:
        while seq_number < len(chunks) and len(window) < 2:
            packet = struct.pack("!I", seq_number) + chunks[seq_number]
            sock.send(packet)
            window.append((packet, time.time()))
            logger.info("Sent packet with sequence number %d", seq_number - 1)
            seq_number += 1

        sock.settimeout(timeout)
        try:
            ack, _ = sock.recvfrom(1024)
            ack_number = struct.unpack("!I", ack)[0]

            while window and window[0][0][:4] <= struct.pack("!I", ack_number):
                sent_time = window.pop(0)[1]
                sample_rtt = time.time() - sent_time
                estimated_rtt = (1 - alpha) * estimated_rtt + alpha * sample_rtt
                dev_rtt = (1 - beta) * dev_rtt + beta * abs(sample_rtt - estimated_rtt)
                timeout = estimated_rtt + 4 * dev_rtt

        except socket.timeout:
            logger.info("Timeout, retransmitting packets in the window")
            for packet, _ in window:
                sock.send(packet)
                logger.info("Retransmitted packet with sequence number %d", _)

    # Connection Termination
    fin_packet = struct.pack("!I", 0xFFFFFFFF)
    sock.send(fin_packet)

    while True:
        try:
            # sock.settimeout(2 * timeout)  # Double the timeout for FIN packet
            logger.info("Fin")
            ack, _ = sock.recvfrom(1024)
            if ack == fin_packet:
                logger.info("Received FIN-ACK, closing connection")
                break
        except socket.timeout:
            sock.send(fin_packet)
            logger.info("Timeout, resending FIN packet")


def recv(sock: socket.socket, dest: io.BufferedIOBase) -> int:
    logger = homework5.logging.get_logger("hw5-receiver")
    expected_seq = 0
    received_data = {}

    while True:
        packet = sock.recv(homework5.MAX_PACKET + 4)
        if not packet:
            continue

        seq_number, = struct.unpack("!I", packet[:4])
        if seq_number == 0xFFFFFFFF:
            logger.info("Received FIN packet, sending FIN-ACK")
            fin_ack_packet = struct.pack("!I", 0xFFFFFFFF)
            sock.send(fin_ack_packet)
            break

        if seq_number >= expected_seq:
            received_data[seq_number] = packet[4:]
            while expected_seq in received_data:
                dest.write(received_data.pop(expected_seq))
                logger.info("Received and wrote %d bytes from packet with sequence number %d", len(packet) - 4, seq_number)
                expected_seq += 1

        ack_packet = struct.pack("!I", expected_seq - 1)
        sock.send(ack_packet)

    return dest.tell()