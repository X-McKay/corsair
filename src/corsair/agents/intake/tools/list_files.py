"""Episode-bound inspection listing tool."""

import asyncio

from corsair.ports.intake import InspectionReader


def create_list_files(reader: InspectionReader):
    async def list_files() -> dict:
        """List bounded relative paths from the admitted source snapshot."""
        return await asyncio.to_thread(reader.read, "list")

    return list_files
