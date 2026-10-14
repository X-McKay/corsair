"""Explicit native-tool provisioning for one owned local kind cluster."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time
from datetime import datetime, timezone
import urllib.request
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[2]
LOCK = yaml.safe_load((ROOT / "deploy/runtime-lock.yaml").read_text())
TOOLS = ROOT / ".tools" / LOCK["platform"]
CLUSTER = "corsair"
STATE = ROOT / ".state/kind"
KUBECONFIG = STATE / "kubeconfig"
OPENSHELL_STATE = ROOT / ".state/openshell"
ENV = os.environ.copy()
for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
    ENV.pop(key, None)
ENV["KIND_EXPERIMENTAL_PROVIDER"] = "docker"
ENV["KUBECONFIG"] = str(KUBECONFIG)


def download(spec, destination, executable=False):
    if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() == spec["sha256"]:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(spec["url"], timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != spec["sha256"]:
        raise RuntimeError(f"Checksum mismatch: {destination.name}")
    temporary = destination.with_suffix(".download")
    temporary.write_bytes(data)
    temporary.chmod(0o755 if executable else 0o600)
    temporary.replace(destination)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("tools", "up", "down"))
    args = parser.parse_args()
    if (platform.system(), platform.machine()) != ("Linux", "x86_64"):
        parser.error("Only Linux amd64 is selected for this first qualification tuple")
    evidence = ROOT / ".runs/bootstrap" / uuid.uuid4().hex
    evidence.mkdir(parents=True)
    (evidence / "runtime-lock.yaml").write_text((ROOT / "deploy/runtime-lock.yaml").read_text())
    counter = 0

    def run(argv, timeout=300, check=True):
        nonlocal counter
        counter += 1
        print("Running:", " ".join(map(str, argv)), flush=True)
        receipt = {"argv": list(map(str, argv)), "started_at": datetime.now(timezone.utc).isoformat()}
        started = time.monotonic()
        try:
            result = subprocess.run(receipt["argv"], env=ENV, capture_output=True, text=True, timeout=timeout)
            receipt.update(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired as error:
            receipt.update(timed_out=True, stdout=(error.stdout or b"").decode(), stderr=(error.stderr or b"").decode())
            raise RuntimeError(f"Command timed out; completion unknown; evidence: {evidence}") from error
        finally:
            receipt["elapsed_seconds"] = time.monotonic() - started
            (evidence / f"{counter:02d}.json").write_text(json.dumps(receipt, indent=2))
        if check and result.returncode:
            raise RuntimeError(f"Command failed ({result.returncode}); evidence: {evidence}; {result.stderr[-2000:]}")
        return result

    kind = TOOLS / "kind"
    kubectl = TOOLS / "kubectl"
    docker = ["docker", "--host=unix:///var/run/docker.sock"]
    if args.action == "tools":
        for name in ("kind", "kubectl"):
            download(LOCK[name], TOOLS / name, executable=True)
        run([kind, "version"])
        run([kubectl, "version", "--client", "-o", "json"])
        return
    for name in ("kind", "kubectl"):
        path = TOOLS / name
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != LOCK[name]["sha256"]:
            parser.error("Run the explicit tools target to install checksum-verified binaries")
    run(docker + ["info", "--format", '{"server_version":"{{.ServerVersion}}","kernel":"{{.KernelVersion}}","architecture":"{{.Architecture}}","storage_driver":"{{.Driver}}"}'])
    owner_path = STATE / "owner.json"
    container = f"{CLUSTER}-control-plane"
    if args.action == "down":
        if not owner_path.exists():
            parser.error("No local ownership receipt; refusing to delete a possibly unrelated cluster")
        if (OPENSHELL_STATE / "port-forward.json").exists():
            parser.error("A recorded gateway port-forward may still run; run make openshell-forward-stop first")
        owner = json.loads(owner_path.read_text())
        found = run(docker + ["inspect", "--format", "{{.Id}}", container], check=False)
        if found.returncode == 0 and found.stdout.strip() != owner["container_id"]:
            parser.error("Cluster container identity changed; refusing to delete its replacement")
        if found.returncode and "no such" not in found.stderr.lower():
            raise RuntimeError(f"Cannot establish cluster identity; evidence: {evidence}")
        run([kind, "delete", "cluster", "--name", CLUSTER])
        remaining = run(docker + ["inspect", container], check=False)
        if remaining.returncode == 0 or "no such" not in remaining.stderr.lower():
            raise RuntimeError("Cluster deletion not confirmed")
        # The gateway, its namespace and its client identity lived only in this node.
        gateway_state = OPENSHELL_STATE.exists()
        if gateway_state:
            shutil.rmtree(OPENSHELL_STATE)
        (evidence / "cleanup.json").write_text(json.dumps({"cluster": CLUSTER, "container_id": owner["container_id"], "confirmed": True, "openshell_state_removed": gateway_state}))
        owner_path.unlink()
        KUBECONFIG.unlink(missing_ok=True)
        return
    existing = run([kind, "get", "clusters"])
    collision = run(docker + ["inspect", "--format", "{{.Id}}", container], check=False)
    if collision.returncode and "no such" not in collision.stderr.lower():
        raise RuntimeError(f"Cannot establish local container identity; evidence: {evidence}")
    if CLUSTER in existing.stdout.splitlines() or collision.returncode == 0 or owner_path.exists():
        parser.error("corsair already exists; refusing to adopt or overwrite it")
    STATE.mkdir(parents=True, exist_ok=True)
    STATE.chmod(0o700)
    try:
        run([kind, "create", "cluster", "--name", CLUSTER, "--config", ROOT / "deploy/kind/cluster.yaml", "--image", LOCK["kubernetes"]["node_image"], "--kubeconfig", KUBECONFIG, "--retain"], timeout=600)
    except RuntimeError:
        # Vendor diagnostics retain the original infrastructure failure. Never
        # retry kubeadm or weaken the runtime into an apparent qualification.
        for service in ("kubelet", "containerd"):
            run(docker + ["exec", container, "journalctl", "-u", service, "--no-pager", "-n", "100"], check=False)
        raise
    finally:
        found = run(docker + ["inspect", "--format", "{{.Id}}", container], check=False)
        if found.returncode == 0:
            owner_path.write_text(json.dumps({"cluster": CLUSTER, "container_id": found.stdout.strip()}))
        if KUBECONFIG.exists():
            KUBECONFIG.chmod(0o600)
    calico = ROOT / ".cache/calico"
    download(LOCK["calico"], calico / "calico.yaml")
    images = [{"name": name, "newName": name, "digest": digest} for name, digest in LOCK["calico"]["images"].items()]
    (calico / "kustomization.yaml").write_text(yaml.safe_dump({"apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization", "resources": ["calico.yaml"], "images": images}))
    # Let the node's CRI pull the exact digest-pinned references from the pod
    # specs. Loading a digest-only Docker archive through kind can give it a
    # synthetic import-<date> name that containerd cannot resolve later.
    kube = [kubectl, "--kubeconfig", KUBECONFIG, "--context", "kind-corsair"]
    run(kube + ["apply", "--server-side", "--field-manager=corsair-bootstrap", "-k", calico])
    run(kube + ["rollout", "status", "daemonset/calico-node", "-n", "kube-system", "--timeout=180s"])
    run(kube + ["rollout", "status", "deployment/calico-kube-controllers", "-n", "kube-system", "--timeout=180s"])
    run(kube + ["wait", "--for=condition=Ready", "nodes", "--all", "--timeout=180s"])
    run(kube + ["get", "nodes", "-o", "json"])
    print(f"Cluster ready; bootstrap evidence: {evidence}", flush=True)


if __name__ == "__main__":
    main()
