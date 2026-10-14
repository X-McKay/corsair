import os


def ping(host: str) -> int:
    """Check that a host answers one ping."""
    return os.system("ping -c 1 " + host)
