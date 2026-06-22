import socket
import unittest

from backend import rfcomm_bridge


STATE_LINE = (
    b"STATE mpu=1 auto=0 fault=0 led=200,50,255 "
    b"kp=8.000 ki=0.250 kd=0.800 kw=0.000 sensor=0.0 "
    b"out=20.0 min=4.0 ex=0 ey=0 ez=1 mx=90 my=90 mz=93 "
    b"x=-1.25 y=0.00 z=0.00\n"
)


class FakeSocket:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.sent = []
        self.timeout = None
        self.closed = False

    def gettimeout(self):
        return self.timeout

    def settimeout(self, timeout):
        self.timeout = timeout

    def sendall(self, payload):
        self.sent.append(payload)

    def recv(self, _size):
        if not self.chunks:
            raise socket.timeout("no response")
        chunk = self.chunks.pop(0)
        if isinstance(chunk, BaseException):
            raise chunk
        return chunk

    def close(self):
        self.closed = True


class RequestStateTests(unittest.TestCase):
    def tearDown(self):
        sock = rfcomm_bridge.get_client_socket()
        rfcomm_bridge.clear_client_socket(sock)

    def test_collects_fragmented_state_response(self):
        fake_socket = FakeSocket(
            [b"STA", STATE_LINE[3:47], STATE_LINE[47:101], STATE_LINE[101:]]
        )
        rfcomm_bridge.set_client_socket(fake_socket)

        result = rfcomm_bridge.request_state(timeout=0.5)

        self.assertTrue(result["success"])
        self.assertEqual(fake_socket.sent, [b"APPSTATE\n"])
        self.assertTrue(result["state"]["mpu"])
        self.assertFalse(result["state"]["auto"])
        self.assertEqual(result["state"]["led"], [200, 50, 255])
        self.assertEqual(result["state"]["kp"], 8.0)
        self.assertEqual(result["state"]["mz"], 93)
        self.assertEqual(result["state"]["x"], -1.25)
        self.assertIs(rfcomm_bridge.get_client_socket(), fake_socket)
        self.assertFalse(fake_socket.closed)

    def test_ignores_unrelated_complete_lines_before_state(self):
        fake_socket = FakeSocket([b"OK\r\n", STATE_LINE])
        rfcomm_bridge.set_client_socket(fake_socket)

        result = rfcomm_bridge.request_state(timeout=0.5)

        self.assertTrue(result["success"])
        self.assertEqual(result["state"]["led"], [200, 50, 255])

    def test_timeout_clears_and_closes_stale_socket(self):
        fake_socket = FakeSocket([socket.timeout("timed out")])
        rfcomm_bridge.set_client_socket(fake_socket)

        result = rfcomm_bridge.request_state(timeout=0.01)

        self.assertFalse(result["success"])
        self.assertIsNone(rfcomm_bridge.get_client_socket())
        self.assertTrue(fake_socket.closed)


if __name__ == "__main__":
    unittest.main()
