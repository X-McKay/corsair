---
id: HANDOFF-0136
kind: handoff
title: OpenShell sandbox backend implemented, live qualification next
status: recorded
updated: 2026-10-14
related: [SPEC-0083, PLAN-0100, SPEC-0082]
---

# OpenShell sandbox backend implemented, live qualification next

## Verified state

The branch `claude/validate-openshell-v2-rl9wud` is based on develop at bc3c25fa and carries [SPEC-0083](../specs/SPEC-0083-openshell-sandbox-backend.md):

- the `Sandboxes` port with explicit selection (`CORSAIR_WORKSPACE`, default `docker`);
- `DockerSandboxes`, whose docker argv are pinned to the pre-port recording;
- replay, execute, diagnose, the reconciler and the Builder workspace running through the port;
- `OpenShellSandboxes` and `OpenShellWorkspace` on SDK 0.1.3, with v2 policies;
- the kind/OpenShell setup restored from 9c3bc62, plus `openshell-images-load`, `openshell-config`, `qualify-openshell-v2` and [the runbook](../../runbooks/openshell-v2.md).

The backend is implemented, not qualified: nothing has run against a gateway.

## Validation and blockers

- **Offline suite (cloud container):** `uv run --locked python -m pytest -c pyproject.toml --rootdir=. -n auto tests` gave 1588 passed and 117 skipped. Every Docker and live OpenShell test skipped, because the container has neither.
- **Live runs:** blocked here (no Docker, kind or gateway). They need the RIG0 cluster in this branch's worktree. Only one thread holds that cluster at a time, and the build owner holds it during the PoV spread.

Open facts only the live run settles:

- **Workdir and Landlock:** whether Landlock accepts `read_write: /work` before the directory exists, and whether the exec user can create it.
- **Exec user:** which user commands run as under the gateway's default process policy.
- **Exec behaviour:** the stdin limit (1 MiB chunks are assumed safe), how `no_login_shell` handles the environment, and when exit 124 arrives.
- **Policy readback:** the `sandbox get` / `policy get` JSON keys, and whether `sandbox get` shows the image at all.
- **Build policy:** the binary paths, TLS for each registry client, and that POST and unlisted hosts are denied.
- **Names and selectors:** whether native names and label selectors are accepted as assumed.
- **Resource limits:** the shape of the limits field.
- **Recipes writing outside the policy:** recipes that write to `$HOME` or system site-packages (only `/work`, `/tmp` and `/dev/null` are writable).

## Decisions and next steps

- **Transfer:** tar over exec stdin rather than CLI upload, so symlink handling is ours.
- **Environments:** OpenShell replays the sealed recipe and reruns the baseline in each probe sandbox.
- **Docker:** stays the default and unchanged.

Next: the coordinator hands this branch the RIG0 cluster, then the runbook sequence runs in `/home/al/git/corsair/.worktrees/claude/validate-openshell-v2-rl9wud`, ending with `make qualify-openshell-v2` and one decisive case on each backend.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0083, PLAN-0100 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. On RIG0, in /home/al/git/corsair/.worktrees/claude/validate-openshell-v2-rl9wud (git worktree add may need Al or Bash(git worktree add:*)), once the coordinator hands over the cluster: run docs/runbooks/openshell-v2.md through make qualify-openshell-v2 with evidence under that worktree's .runs, then one decisive case on OpenShell and on Docker (one live-inference user at a time). Stop and record the failure layer if admission, gateway or the policy gate fails; do not weaken policy or TLS. Fix what the live run shows, preserve every failed attempt, update PLAN-0100/CURRENT.md, and write a new handoff.
```
