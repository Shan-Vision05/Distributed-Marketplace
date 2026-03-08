import json
import struct

HEADER_SIZE = 4

def send_message(socket, message):

    encoded_message = json.dumps(message).encode('utf-8')
    message_header = struct.pack('>I', len(encoded_message))
    socket.sendall(message_header + encoded_message)


def receive_message(sock):
    header = b''
    while len(header) < HEADER_SIZE:
        chunk = sock.recv(HEADER_SIZE - len(header))
        if not chunk:
            return None
        header += chunk

    message_length = struct.unpack('>I', header)[0]

    message_data = b''
    while len(message_data) < message_length:
        chunk = sock.recv(message_length - len(message_data))
        if not chunk:
            return None
        message_data += chunk

    return json.loads(message_data.decode('utf-8'))
