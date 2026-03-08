import socket
import threading
from common.protocol import send_message, receive_message


class TCPServer:
    def __init__(self, host="localhost", port=8000, request_handler=None):
        self.host = host
        self.port = port
        self.request_handler = request_handler or self.default_handler
        self.server_socket = None

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(500)

        print(f"Server listening on {self.host}:{self.port}")

        while True:
            client_socket, address = self.server_socket.accept()
            print(f"Accepted connection from {address}")

            client_handler = threading.Thread(
                target=self.handle_client,
                args=(client_socket, address),
                daemon=True
            )
            client_handler.start()

    def handle_client(self, client_socket, address):
        client_socket.settimeout(60)

        try:
            while True:
                message = receive_message(client_socket)

                if message is None:
                    print(f"Connection closed by {address}")
                    break

                response = self.request_handler(message)

                send_message(client_socket, response)

        except (socket.timeout, ConnectionResetError):
            print(f"Connection timeout/reset from {address}")

        except Exception as e:
            print(f"Protocol error with {address}: {e}")

        finally:
            client_socket.close()
            print(f"Closed connection from {address}")

    def default_handler(self, message):
        return {"status": "received", "message": message}
