"""Content-addressed trusted images for the real Docker tests.

The Docker tests run each recipe kind against ``corsair-<lang>:<content tag>`` from
``corsair.entrypoints.gym.image_tag``: the image built from this working tree's
``deploy/<lang>/`` and driver directory (``just images-gym``). They never use, rebuild
or retag the shared ``:0.1`` images, so a driver edit is tested against its own build.
"""

from __future__ import annotations

from pathlib import Path

from corsair.entrypoints.gym import gym_images
from corsair.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
PYTHON_KIND = "python.secret_disclosure/1"


def content_images() -> dict[str, str]:
    """Every default recipe kind's content-tagged image for this working tree."""
    return gym_images(ROOT, Settings())


def content_image(kind: str) -> str:
    """One recipe kind's content-tagged image."""
    return content_images()[kind]


def with_content_images(settings: Settings) -> Settings:
    """``settings`` with the Python default and every recipe kind on content tags."""
    images = content_images()
    return settings.model_copy(update={"image": images[PYTHON_KIND], "images": images})
