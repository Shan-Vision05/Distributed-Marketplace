import socket
from common.protocol import send_message, receive_message


class TCPClient:
    def __init__(self, host, port, timeout=30):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.client_socket = None

    def connect(self):
        if self.client_socket is not None:
            return

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect((self.host, self.port))
        self.client_socket = sock

    def send_request(self, message):

        try:
            self.connect()

            send_message(self.client_socket, message)

            response = receive_message(self.client_socket)

            if response is None:
                self.close()
                return None

            return response

        except (socket.timeout, ConnectionResetError, BrokenPipeError) as e:
            print(f"Error during communication: {e}")
            self.close()
            return None

        except Exception as e:
            print(f"Protocol error: {e}")
            self.close()
            return None

    def close(self):
        if self.client_socket is not None:
            try:
                self.client_socket.close()
            except Exception:
                pass
            self.client_socket = None
