"""Offline tests. Accidental real network connections fail immediately."""
import socket

def _offline(*args, **kwargs):
    raise AssertionError("Tests must not make live network connections")

socket.socket.connect = _offline
socket.create_connection = _offline
