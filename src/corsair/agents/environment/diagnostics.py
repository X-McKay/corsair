"""Deterministic setup symptoms and next actions; never infer policy from stderr.

Text matches are reported symptoms, not root-cause qualification. Full command, dependency
coordinates, endpoints and output remain available via the cited ledger run.
"""
from corsair.core.blockers import Blocker
from corsair.ports.execution import ExecutionReceipt


def setup_blocker(receipt: ExecutionReceipt, run_id: int, error: str | None) -> Blocker | None:
    evidence = (f"setup run {run_id}: command, operation and output in the private setup ledger",)
    def issue(code, summary, actions, certainty="observed", owner="operator"):
        return Blocker(code=code, summary=summary, certainty=certainty, owner=owner,
                       actions=tuple(actions), evidence=evidence)

    if receipt.storage_error or receipt.failure_layer == "receipt_storage":
        return issue("receipt_storage", "Execution evidence could not be retained reliably.",
                     ["Check the artifact/journal path, permissions, capacity and original operation receipt.",
                      "Reconcile execution before restarting; a zero exit does not repair missing evidence."])
    if receipt.worker_cleanup == "unconfirmed":
        return issue("cleanup_unconfirmed", "Execution worker cleanup is unconfirmed.",
                     ["Inspect the original worker and sandbox identities and retained cleanup receipt.",
                      "Confirm cleanup through the supported runtime; do not repeat the workload yet."])
    if receipt.failure_layer == "output_budget":
        return issue("output_limit", "Execution exceeded its output budget; remote completion may be unknown.",
                     ["Inspect the retained output and operation state before any retry.",
                      "Reduce command verbosity; an operator must review any budget change."])
    if receipt.delivery != "acknowledged" or receipt.completion != "terminal_observed":
        if receipt.delivery == "not_dispatched":
            return issue("execution_not_dispatched", "The execution boundary refused or failed before dispatch.",
                         ["Inspect the receipt's native error, gateway connectivity, host admission and sandbox identity.",
                          "Correct the recorded cause before starting a new attempt; no workload completion is claimed."])
        return issue("execution_unknown", "Command delivery or completion is unknown.",
                     ["Inspect the operation receipt and original sandbox through the supported runtime.",
                      "Do not resend the command until its outcome is reconciled; inspect gateway/transport health."], "unknown")
    if error or receipt.failure_layer or receipt.native_exit is None:
        return issue("execution_failure", "Execution returned an infrastructure failure or incomplete receipt.",
                     ["Inspect native error type, reason, status, failure layer and operation receipt.",
                      "Correct host/runtime/evidence failure before a new attempt; do not classify this as an application result."])
    if receipt.native_exit == 0:
        return None

    # Bounded scan only, no arbitrary output echoed into user-facing guidance.
    output = (receipt.stdout[-16384:] + b"\n" + receipt.stderr[-16384:]).decode("utf-8", "replace").lower()
    common = "Read the cited command and stdout/stderr for the exact dependency, version, repository and attempted endpoint."
    if any(s in output for s in ("certificate verify failed", "certificate_verify_failed", "pkix path building failed", "ssl certificate problem")):
        return issue("tls_trust", "The command reported a TLS trust failure.",
                     [common, "Check endpoint certificate chain, clock, and configured CA/proxy trust with the operator; keep TLS verification enabled."], "reported")
    if any(s in output for s in ("401 unauthorized", "403 forbidden", "authentication failed", "status code 401", "status code 403")):
        return issue("registry_access", "The command reported an access/authentication refusal.",
                     [common, "Check registry availability and the supported credential configuration. A 403 alone does not establish policy denial.",
                      "If native policy evidence confirms a denial, have the operator review the exact host/port/method against the intended OpenShell policy."], "reported")
    if any(s in output for s in ("temporary failure in name resolution", "could not resolve host", "name or service not known", "connection refused", "connection timed out", "read timed out", "network is unreachable")):
        return issue("connectivity", "The command reported a connectivity failure; its cause is not yet established.",
                     [common, "Check DNS, destination availability, proxy and gateway reachability from the same execution boundary.",
                      "Inspect native policy evidence for the attempted endpoint; request a scoped operator policy change only if an intended access is confirmed denied."], "reported")
    if any(s in output for s in ("no matching distribution found", "could not find a version that satisfies", "could not resolve dependencies", "could not find artifact", "eresolve", "etarget")):
        return issue("dependency_resolution", "The package manager reported an unresolved dependency or version conflict.",
                     [common, "Check manifest/lock constraints, configured registry, artifact availability and runtime/platform compatibility.",
                      "A missing package message alone does not prove the registry was reachable; inspect earlier network/authentication errors. Do not silently substitute versions."], "reported", "developer")
    if "no space left on device" in output or "disk quota exceeded" in output:
        return issue("storage_capacity", "The command reported exhausted storage or quota.",
                     ["Inspect workspace and node capacity, inode/quota limits and retained output.",
                      "Ask the operator to reclaim owned resources or review the workspace budget; do not delete unknown resources."], "reported")
    return issue("setup_command_failed", f"Setup command exited with status {receipt.native_exit}.",
                 ["Inspect the cited command and output to distinguish dependency, compilation, test discovery or baseline-test failure.",
                  "Check the repository's declared procedure and required inputs. Only an explicit correction_available result permits a bounded changed invocation; otherwise start a new attempt after correcting the cause. No automatic retry or security verdict."], "unknown", "developer")


def budget_blocker() -> Blocker:
    return Blocker(code="setup_budget", summary="The operator setup command budget is exhausted.",
                   certainty="observed", owner="operator",
                   actions=("Inspect the completed command ledger for repeated or unnecessary work.",
                            "Review the recipe and budget before starting a new attributable attempt."))
