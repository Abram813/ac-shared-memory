from __future__ import annotations

import socket

import pytest

from .conftest import NetworkBlocked


def test_external_tcp_connection_is_blocked() -> None:
    with pytest.raises(NetworkBlocked):
        socket.create_connection(("example.com", 80), timeout=1)


def test_external_dns_is_blocked() -> None:
    with pytest.raises(NetworkBlocked):
        socket.getaddrinfo("example.com", 443)


def test_loopback_is_still_allowed() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.connect(("127.0.0.1", port))
