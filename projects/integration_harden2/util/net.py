"""Network helpers shared by several modules."""
import socket

JSON_HEADERS = {"Content-Type": "application/json"}


def port_open(host, port, timeout=0.5):
    """True when something accepts a TCP connection on host:port. The ONE port probe
    in the app. connect_ex returns an errno instead of throwing; `host` must be a
    numeric IP (a name lookup could still throw), which every caller passes."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    code = sock.connect_ex((host, port))
    sock.close()
    return code == 0
