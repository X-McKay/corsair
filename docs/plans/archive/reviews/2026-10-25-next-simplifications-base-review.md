# Next simplifications to discuss

The requested Just/Nix/platform migration is one branch and one PR. These are identified follow-up opportunities, not hidden runtime changes in that migration. The strongest next work removes duplication at existing boundaries rather than adding a mixin, backend registry or scheduler.

## Report provenance and one writer

`eval` calls `save_report`, adds `dataset_digest`, then writes the file again. `rescore` discards the loaded dataset and writes no dataset identity. A real rescore probe confirmed this omission. Extend the existing writer with an optional dataset digest and have both callers write once. Test the returned/on-disk identity and rescore actual completed native child receipts. This improves reproducibility and deletes code without changing score policy.

## Names-only source listing

The producer's `list_files` consumes `iter_snapshot_files` but discards contents. A four-file probe measured five full artifact reads for a listing. Add one names-only helper backed by the existing immutable archive validator and use it in this real caller. Preserve lexical order, truncation, link/path/duplicate/size checks; keep content iteration for Docker staging. Test one validated artifact read and no content extraction, then re-run source/agent/native chain gates. No cache or abstraction framework is needed.

## Remove the duplicate original-source read

`Case.bind_recipe` requires the finding file and recipe module file to match. `prepare_case` still reads that path once for validation and immediately again for the excerpt. Remove only the discarded original read; the retained read validates the same path. Keep the distinct fixed-source module check. A counting regression should bind this optimization to the current Case invariant, with canonical-source, symlink/replacement and native reference tests retained.

## Reject invalid CLI bounds before I/O

`BatchRequest` constrains repeats/concurrency to 1–8, but argparse accepts 0 and 9, allowing store/dataset I/O before rejection. Add native `choices=range(1, 9)` to the two flags, matching the isolated evaluator. Retain Pydantic checks for direct callers and valid native-batch tests. This is an input-boundary cleanup, not another schema layer.

## Lower priority

A verified existing-blob fast path could avoid temporary writes/fsync/link attempts for repeated identical artifacts. It needs byte equality, corruption and concurrent first-writer tests, and must not change operation `claim`/`commit`. Measure repeated-round workloads before adding the extra branch. Batch summaries could also aggregate recorded `agent_seconds` while keeping missing/empty totals null. Neither has a demonstrated end-to-end latency benefit yet.

Review basis is `dab7942e`, with caller tracing and focused test/probe evidence. No additional agent/provider loop, broad tracing rewrite, weak evidence shortcut or wholesale uv-to-Nix Python graph translation is justified by this review. Nix pins the native tool shell; uv.lock remains the simpler Python dependency boundary. Fully hermetic builds are a separate requirement.
