# First durable investigation

New investigations run intake first and use recipe-free test execution. Complete [installation](installation.md), configure an admitted source root, reviewed locally available images, shared artifact storage and an explicit model provider, then follow [recipe-free investigations](../guides/investigations.md) for the intake-gated v4 request and typed API.

Run the separate inspection image build and ordinary worker:

```bash
just images-intake
uv run --locked corsair worker --settings /operator/settings.json
```

In another terminal, submit issue JSON (or use `--issue OWNER/REPO#N`):

```bash
uv run --locked corsair investigate --json /operator/issue.json --source /operator/repository \
  --settings /operator/settings.json --wait --format json
```

The worker uses native ADK episodes and ordinary Temporal activities. A producer constructs a test plan, an outcome-blind auditor reviews it, and accepted commands execute only in the configured sandbox. Results distinguish process outcomes from security assessment, which remains `UNRESOLVED`. Source/image changes are re-admitted rather than hidden by provider retries or image pulls.

`inspect RUN_ID` reads a committed result; `inspect RUN_ID --online --watch` observes Temporal. `cancel RUN_ID` requests cancellation and does not assert immediate cleanup. See [operations](../operations/overview.md) and [disaster recovery](../operations/disaster-recovery.md) for host/artifact loss limits.

The [quickstart](quickstart.md) retains a no-model historical fixed-observer diagnostic. Its recipe request is not valid input to the new `investigate` command. Historical results and frozen evaluations keep their versioned semantics.
