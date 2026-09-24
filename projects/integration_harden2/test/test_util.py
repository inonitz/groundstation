"""Tests for util/: the shared standalone helpers (Hebrew numbers, the port probe, the
native-program environment)."""
import os
import socket
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from util.hebrew import hebnum_to_digits
from util.net import port_open
from util.process import native_env


def test_hebrew_number_words_become_digits():
    assert hebnum_to_digits("טוס עשרים וחמישה מטרים") == "טוס 25 מטרים"
    assert hebnum_to_digits("עלה מאה עשרים מטר") == "עלה 120 מטר"
    assert hebnum_to_digits("פנה חמישה עשר מעלות") == "פנה 15 מעלות"
    # an ordinal with the article is kept
    assert hebnum_to_digits("השני מימין") == "השני מימין"


def test_port_open_sees_a_listener_and_nothing_else():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert port_open("127.0.0.1", port)
    assert not port_open("127.0.0.1", port, timeout=0.2)


def test_native_env_adds_the_native_library_folder():
    env = native_env(PULSE_SERVER="unix:/x")
    assert (
        env["LD_LIBRARY_PATH"].split(":")[0] == config.NATIVE_BIN_DIR
        and env["PULSE_SERVER"] == "unix:/x"
    )
