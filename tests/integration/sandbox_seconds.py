"""Shared real-Docker assertion that sandbox timing travels through the raw receipt."""

from __future__ import annotations

from corsair.contracts import Observation


def assert_sandbox_seconds(observation: Observation) -> None:
    """Both roles carry driver wall and cgroup CPU seconds and trusted host seconds.

    Host seconds span container create to wait, so they cover the driver's own wall time.
    """
    for role in (observation.control, observation.adversarial):
        assert role is not None
        assert role.wall_seconds is not None and role.wall_seconds > 0
        assert role.cpu_seconds is not None and role.cpu_seconds > 0
        assert role.host_seconds is not None and role.host_seconds >= role.wall_seconds
