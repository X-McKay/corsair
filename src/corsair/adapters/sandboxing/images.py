"""Inspect configured local images only; never pulls or queries a registry."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, closing
from typing import Any

import docker
from docker.errors import ImageNotFound

from corsair.contracts.intake import AvailableImage, ImageCandidate, ImageInventory
from corsair.settings import Settings


def _architecture(value: str) -> str:
    return {"aarch64": "arm64", "x86_64": "amd64"}.get(value, value)


def available_images(settings: Settings, client: Any) -> ImageInventory:
    candidates = [
        ImageCandidate(
            reference=settings.image,
            language="python",
            execution_mode="callable",
        ),
        ImageCandidate(
            reference=settings.node_image,
            language="javascript",
            execution_mode="callable",
        ),
        ImageCandidate(
            reference=settings.java_image,
            language="java",
            execution_mode="callable",
        ),
        *settings.intake_images,
    ]
    info = client.info()
    architecture = _architecture(str(info.get("Architecture", "")))
    if architecture not in {"arm64", "amd64"} or info.get("OSType") != "linux":
        raise ValueError("Docker host platform is not admitted")
    images = []
    for candidate in candidates:
        try:
            image = client.images.get(candidate.reference)
        except ImageNotFound:
            continue
        if (
            image.attrs.get("Os") != "linux"
            or _architecture(str(image.attrs.get("Architecture", ""))) != architecture
        ):
            continue
        images.append(AvailableImage(**candidate.model_dump(), image_id=str(image.id)))
    return ImageInventory(images=images)


def recheck_image(client: Any, image: AvailableImage) -> bool:
    try:
        current = client.images.get(image.reference)
    except ImageNotFound:
        return False
    return str(current.id) == image.image_id


def discover_images(settings: Settings) -> ImageInventory:
    with closing(docker.from_env(timeout=15)) as client:
        return available_images(settings, client)


@asynccontextmanager
async def docker_client() -> AsyncGenerator[Any]:
    task = asyncio.create_task(asyncio.to_thread(docker.from_env, timeout=15))
    try:
        client = await asyncio.shield(task)
    except asyncio.CancelledError:
        client = await task
        await asyncio.to_thread(client.close)
        raise
    try:
        yield client
    finally:
        await asyncio.to_thread(client.close)
