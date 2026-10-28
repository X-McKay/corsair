"""Episode-bound read-only inspection tool."""

import asyncio

from corsair.contracts import safe_path
from corsair.ports.intake import InspectionReader


def create_read_file(reader: InspectionReader):
    async def read_file(path: str) -> dict:
        """Read one normalized relative text path in the admitted source snapshot."""
        safe_path(path)
        return await asyncio.to_thread(reader.read, "read", path)

    return read_file
