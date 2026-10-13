---
id: SPEC-0066
kind: spec
title: Configurable inference and ticket providers
status: accepted
updated: 2026-10-13
related: [PLAN-0072]
---

# Configurable inference and ticket providers

## Goal and scope

Implement GitHub issue and Azure DevOps work-item capture and native OpenAI-compatible/Bedrock inference. User direction includes independently selectable provider and model per agent, with an explicit shared default. No provider fallback, ticket mutation or automatic repository selection from ticket text. Existing local vLLM profiles remain valid.

## Boundaries and design

A shared operator JSON file has independent inference and tickets sections. Inference names reusable model configurations and maps agent names to them, with an optional default. Resolve and validate every selected agent before creating clients; unknown agents/models are errors. PydanticAI owns request translation; boto3 owns AWS credential resolution. Secrets are referenced by environment name or AWS profile, never configuration literals. Direct, isolated and durable callers share resolution; SDK clients remain worker-side.

Ticket adapters return one immutable vendor-neutral snapshot with source identity, revision, timestamps, description and bounded paginated discussion. Official REST APIs are accessed through the existing HTTP client: GitHub has no official Python SDK and Azure's comments route uses a preview API; a small read-only mapping avoids SDK objects in contracts. No custom authentication broker or retry engine. Fail explicitly on auth, access, missing item, rate limit, transport, malformed or oversized responses. Capture is a bounded observation, not a transactionally atomic snapshot across pages. Stored ticket content is untrusted input.

## Acceptance and validation

Mock HTTP tests exercise mapping, pagination, limits, failures and no redirects/credential leakage. Native PydanticAI/SDK tests exercise model selection, tool output and settings without network. Configuration tests cover mixed providers, isolated agent selection, unknown names, missing credentials and backwards compatibility. Run affected agent/durable suites and full offline guards. Live Bedrock, OpenAI-compatible services, GitHub private issues and Azure capture require separately configured credentials and are unqualified until measured.

## Decisions and open questions

User authorized implementation and per-agent configuration. Use the existing model factory seam and typed inputs, not a new scheduler. Ticket capture feeds the identification input through an explicit bounded bridge; repository, revision and investigation scope remain operator-owned. See PLAN-0072.
