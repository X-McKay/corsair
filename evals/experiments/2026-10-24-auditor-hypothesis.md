# Auditor hypothesis-coherence experiment

Date: 2026-10-24. Native Google ADK Runner, tool-free auditor factory, configured LiteLLM OpenAI-compatible connector, model `openai/gpt-6.1-sol`, reasoning effort low. Worker endpoint and credentials are private and not committed.

Frozen development manifest: `datasets/auditor-dev.json`, canonical dataset SHA-256 `e865d259995f2e31d971ba5e01a3b5a627fe02771a195436fb73203b927fe0ef`. Two reviewed authored fixtures: a source-grounded path-disclosure proposal and a matching payload pair accompanied by a materially false SQL-interpolation hypothesis. Oracle decisions stayed outside the ADK packet.

| Prompt | Attempts | Passed | Calls | Outcome |
| --- | ---: | ---: | ---: | --- |
| Original coherence instruction | 2 | 1 | 2 | Accepted the false hypothesis because payloads tested a different real issue |
| Tightened complete-claim instruction | 2 | 2 | 2 | Rejected the unsupported mechanism without inferring execution |
| Tightened instruction, 3 repeats | 6 | 6 | 6 | Both frozen labels matched across the repeated development run |

Original prompt digest: `14aeeacb5d83c6c7180395e3f19a4238ede150a044c97a5da74ac820c41908c9`. Tightened prompt digest: `aa902286b052488bbc3c9c2e0d7207a670cae1ce24ad2c6d996404c5b0c28e84`.

The change is the ordinary packaged auditor instruction, not an evaluator-only override or oracle-specific code. Repeated changed-prompt run reported 4,668 input tokens and 604 output tokens. Monetary cost was unavailable and remains null. No significance, broad accuracy, unseen-family performance or production safety claim is made from two development examples. These cases were used to improve the prompt and are not a held-out test set.

Separately, the isolated security producer request was blocked by the provider's `cyber_policy`. It is a failed/blocked operational attempt, not a missing denominator and not an agent accuracy pass. No alternate-provider or prompt-obfuscation retry was used to evade it. Real native integration therefore uses a clearly labelled scripted ADK model. The ordinary live auditor smoke and these semantic fixtures were actually executed.

Private raw outputs remain in ignored `.runs/evaluations`; this public sanitized note preserves the experiment's identities and limitations. Next step: independently labelled held-out families and operator-approved provider suitability, then evaluate whole investigations with repeated runs before promoting the system.
