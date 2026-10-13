"""Capture a ticket to a new private JSON file: python -m corsair.tickets.capture --help."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from corsair.configuration import ProviderConfig
from corsair.ports.tickets import TicketError
from .source import ticket_source


async def capture(config, ticket_id, output):
    if config.tickets is None:
        raise ValueError('configure the tickets section before capture')
    # Reserve exclusively before dispatch; remove only our own reservation on failure.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    identity = os.fstat(fd)
    try:
        with os.fdopen(fd, 'w') as destination:
            async with ticket_source(config.tickets) as source:
                snapshot = await source.capture(ticket_id)
            json.dump({'snapshot': snapshot.model_dump(mode='json'), 'sha256': snapshot.digest}, destination, indent=2)
    except BaseException:
        try:
            current = os.stat(output, follow_symlinks=False)
            if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                os.unlink(output)
        except FileNotFoundError:
            pass
        raise
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--ticket', required=True, type=int)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    config = ProviderConfig.model_validate_json(args.config.read_bytes())
    try:
        snapshot = asyncio.run(capture(config, args.ticket, args.output))
    except TicketError as error:
        parser.exit(1, str(error) + '\n')
    print(f'Captured {snapshot.provider} ticket {snapshot.id}: {snapshot.digest}')


if __name__ == '__main__':
    main()
