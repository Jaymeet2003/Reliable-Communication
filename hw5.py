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
    """
    Implementation of the sending logic for sending data over a slow,
    lossy, constrained network.

    Args:
        sock -- A socket object, constructed and initialized to communicate
                over a simulated lossy network.
        data -- A bytes object, containing the data to send over the network.
    """

    # Naive implementation where we chunk the data to be sent into
    # packets as large as the network will allow, and then send them
    # over the network, pausing half a second between sends to let the
    # network "rest" :)
    logger = homework5.logging.get_logger("hw5-sender")
    chunk_size = homework5.MAX_PACKET - 4  # Account for 4 bytes used for sequence number
    seq_number = 0
    acked = False
    window_size = 2  # Maximum number of packets in transit
    window = []  # List to track packets in the window

    # Initialize variables for RTT estimation
    estimated_rtt = 1.0  # Initial estimated RTT
    deviation_rtt = 0.0
    alpha = 0.125  # Weighting factor for EWMA
    beta = 0.25  # Weighting factor for deviation of RTT
    
    # Split data into chunks
    chunks = [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]

    while chunks or not acked:
        if chunks:
            # Send packets while within the window size constraint
            while len(window) < window_size and chunks:
                packet = struct.pack("i", seq_number) + chunks[0]
                sock.send(packet)
                window.append((packet, seq_number))
                seq_number += 1
                chunks.pop(0)
                start_time = time.time()  # Record the start time for the sent packet
                logger.info("Sent packet with sequence number %d", seq_number - 1)

        # Set socket timeout using Karn's algorithm
        timeout = estimated_rtt + 4 * deviation_rtt
        sock.settimeout(timeout)

        try:
            response = sock.recv(1024)
            ack_seq = struct.unpack("i", response)[0]
            acked = True

            # Remove acknowledged packets from the window
            window = [(pkt, seq) for pkt, seq in window if seq > ack_seq]

            # Update RTT estimation and deviation
            sample_rtt = time.time() - start_time  # Calculate sample RTT
            estimated_rtt = (1 - alpha) * estimated_rtt + alpha * sample_rtt
            deviation_rtt = (1 - beta) * deviation_rtt + beta * abs(sample_rtt - estimated_rtt)
        except socket.timeout:
            logger.info("Timeout, retransmitting packets in the window")

            # Retransmit all packets in the window
            for packet, seq in window:
                sock.send(packet)
                logger.info("Retransmitted packet with sequence number %d", seq)


    # Implement connection termination sequence here
    # Send a special packet indicating the end of data transmission
    fin_packet = struct.pack("i", -1)
    sock.send(fin_packet)
    logger.info("Sent FIN packet")

    # Wait for FIN-ACK
    while True:
        try:
            response = sock.recv(1024)
            if struct.unpack("i", response)[0] == -1:
                logger.info("Received FIN-ACK, closing connection")
                break
        except socket.timeout:
            # Resend FIN packet if timeout occurs
            sock.send(fin_packet)
            logger.info("Timeout, resending FIN packet")


def recv(sock: socket.socket, dest: io.BufferedIOBase) -> int:
    """
    Implementation of the receiving logic for receiving data over a slow,
    lossy, constrained network.

    Args:
        sock -- A socket object, constructed and initialized to communicate
                over a simulated lossy network.

    Return:
        The number of bytes written to the destination.
    """
    logger = homework5.logging.get_logger("hw5-receiver")
    expected_seq = 0
    num_bytes = 0

    while True:
        data = sock.recv(homework5.MAX_PACKET + 4)  # 4 extra bytes for the sequence number
        if not data:
            break

        seq_number = struct.unpack("i", data[:4])[0]

        if seq_number == -1:
            # FIN packet received, terminate connection
            logger.info("Received FIN packet, sending FIN-ACK")
            fin_ack_packet = struct.pack("i", -1)
            sock.send(fin_ack_packet)
            break

        if seq_number == expected_seq:
            dest.write(data[4:])
            num_bytes += len(data) - 4
            dest.flush()
            logger.info("Received and wrote %d bytes from packet with sequence number %d", len(data) - 4, seq_number)

            # Send ACK
            ack_packet = struct.pack("i", expected_seq)
            sock.send(ack_packet)
            expected_seq += 1

    return num_bytes