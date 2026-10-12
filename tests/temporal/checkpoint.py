"""Two-process fixture probe; operator stops/restarts the persistent service between phases.

This probe never starts a service, mutates its database, or downloads a binary.
"""

import argparse
import asyncio
from pathlib import Path

from temporalio.api.enums.v1 import EventType
from temporalio.client import Client, WorkflowHistory

from corsair.workflows.fixture import FixtureInvestigation, FixtureStage
from corsair.workflows.fixture_contracts import FixtureRequest
from tests.temporal.support import save_and_replay, wait_for_child, worker


async def run(args):
    destination = Path(args.evidence_dir)
    if args.phase == "prepare":
        # Refuse evidence reuse before even connecting, hence before any dispatch.
        destination.mkdir(parents=True, exist_ok=False)
    else:
        originals = {}
        runs = {}
        for label, identity in (("parent", args.identity), ("child", args.identity + "/fixture-stage")):
            original = (destination / f"pending-{label}.json").read_text(encoding="utf-8")
            originals[label] = WorkflowHistory.from_json(identity, original)
            runs[label] = originals[label].events[0].workflow_execution_started_event_attributes.original_execution_run_id
            assert runs[label]
    client = await Client.connect(args.address)
    async with worker(client, args.identity):
        if args.phase == "prepare":
            parent = await client.start_workflow(
                FixtureInvestigation.run,
                FixtureRequest(args.identity, "persistent fixture", wait_for_release=True),
                id=args.identity, task_queue=args.identity,
            )
            child = await asyncio.wait_for(wait_for_child(client, args.identity), 30)
            for label, handle in (("parent", parent), ("child", child)):
                history = await handle.fetch_history()
                with (destination / f"pending-{label}.json").open("x", encoding="utf-8") as output:
                    output.write(history.to_json())
            print(f"Pending parent={parent.id} child={child.id}; preparation completed, completion not dispatched")
        else:
            parent = client.get_workflow_handle_for(FixtureInvestigation.run, args.identity, run_id=runs["parent"])
            child = await asyncio.wait_for(wait_for_child(client, args.identity,
                                                        parent_run_id=runs["parent"], child_run_id=runs["child"]), 30)
            for label, handle in (("parent", parent), ("child", child)):
                pending = await handle.fetch_history()
                assert pending.events[0].workflow_execution_started_event_attributes.original_execution_run_id == runs[label]
                assert pending.events[:len(originals[label].events)] == originals[label].events
            await child.signal(FixtureStage.release)
            result = await asyncio.wait_for(parent.result(), 30)
            assert (result.value, result.prepare_attempts, result.operation_attempts) == (
                "persistent fixture", 1, 1,
            )
    if args.phase == "resume":
        await save_and_replay(parent, destination)
        history = await save_and_replay(child, destination)
        assert sum(e.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED
                   for e in history.events) == 2
        print(f"Restored original child history; completed once and replayed parent={parent.id} child={child.id}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "resume"))
    parser.add_argument("--address", required=True)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--evidence-dir", required=True)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
