---
id: PLAN-0108
kind: plan
title: Just, Nix and macOS/Linux developer portability
status: complete
updated: 2026-10-25
related: [PLAN-0107]
---

> Historical record. Commands, counts and status describe the recorded revision, not the current working tree. See [current work](../../README.md) for current guidance.

# Just, Nix and macOS/Linux developer portability

Deliver one combined branch and PR, per the user's latest instruction. Supported developer targets are amd64 Linux (`x86_64-linux`) and Apple Silicon macOS (`aarch64-darwin`) only. Intel Mac and Linux ARM configurations are not required and must not complicate the flake or support claims.

Replace Make with documented Just recipes. Forward task arguments literally using native positional parameters, not shell interpolation. Install one Nixpkgs input pinned in flake.lock; use its Python/uv/Just/Bash/Docker-client/Temporal tools and keep Python dependencies in the existing uv.lock. CI must use the same shell, not a second setup tool chain.

Mac source admission must preserve descriptor/no-follow capability checks, immutable source/evidence identity and cleanup. No path-only fallback, provider replacement or Nix-host execution of untrusted targets. Test on actual macOS ARM and Linux AMD runners; local sandbox regression results (Linux ARM) do not establish target qualification. macOS Docker needs a separate Linux VM/daemon such as Desktop/Colima; hosted ARM runners cannot supply nested virtualization. Keep any Mac full-Docker qualification limitation explicit.

Before delivery, run the actual Just default/argument/error tests and lint/type gates, review only concrete issues, clean obsolete/generated paths, re-test all available native integration and final frozen auditor evaluation, build the wheel outside checkout, inspect fixture/lock/privacy boundaries, and record actual results and unrun gates. Propose further SDK/code simplifications separately from implemented migration behavior; do not silently expand scope.

Completed local final qualification: 120 passed in 139.91 seconds; frozen auditor 6/6; both target flake outputs evaluated. Target-native CI and physical-Mac Docker limits are recorded in [HANDOFF-0141](../handoffs/HANDOFF-0141-just-nix-platforms.md).
