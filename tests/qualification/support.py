"""Native command receipts and a bounded, trusted network fixture; no runtime adapter."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import time
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[2]
LOCK = yaml.safe_load((ROOT / "deploy/runtime-lock.yaml").read_text())
FIXTURES = ROOT / "deploy/qualification"


class Kubectl:
    def __init__(self, kubeconfig, context, evidence):
        self.argv = [str(ROOT / ".tools" / LOCK["platform"] / "kubectl"), "--kubeconfig", str(kubeconfig), "--context", context]
        self.evidence = evidence
        self.counter = 0

    def run(self, *args, check=True, timeout=120):
        return self.native(self.argv + list(map(str, args)), check=check, timeout=timeout)

    def native(self, argv, check=True, timeout=120, env=None):
        """Retain an operator native-tool receipt, including uncertain delivery."""
        self.counter += 1
        receipt = {"argv": list(map(str, argv)), "started_at": datetime.now(timezone.utc).isoformat()}
        started = time.monotonic()
        try:
            result = subprocess.run(receipt["argv"], capture_output=True, text=True, timeout=timeout, env=env)
            receipt.update(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired as error:
            receipt.update(timed_out=True, stdout=(error.stdout or b"").decode(), stderr=(error.stderr or b"").decode())
            raise RuntimeError("Native command timed out; remote completion unknown; see command receipt") from error
        finally:
            receipt["elapsed_seconds"] = time.monotonic() - started
            (self.evidence / f"command-{self.counter:04d}.json").write_text(json.dumps(receipt, indent=2))
        if check and result.returncode:
            raise RuntimeError(f"Native infrastructure/resource error ({result.returncode}): {result.stderr[-2000:]}")
        return result

    def get(self, *args, timeout=120):
        return json.loads(self.run("get", *args, "-o", "json", timeout=timeout).stdout)


def require_owned_cluster(kube):
    """Compare the dedicated node's Docker identity before operator mutations."""
    owner = json.loads((ROOT / ".state/kind/owner.json").read_text())
    found = kube.native(["docker", "--host=unix:///var/run/docker.sock", "inspect", "--format", "{{.Id}}", "corsair-control-plane"])
    if found.stdout.strip() != owner["container_id"]:
        raise RuntimeError("Cluster container identity changed; refusing mutations")
    server = kube.run("config", "view", "--minify", "-o", "jsonpath={.clusters[0].cluster.server}").stdout
    if not server.startswith("https://127.0.0.1:"):
        raise RuntimeError("Qualification requires a localhost-bound kind API")
    nodes = kube.get("nodes")["items"]
    if len(nodes) != 1 or nodes[0]["metadata"]["name"] != "corsair-control-plane":
        raise RuntimeError("Unexpected cluster topology; refusing mutations")
    return nodes[0]


def require_platform(kube):
    """Fail the common prerequisite before any fixture namespace is created."""
    nodes = kube.get("nodes")["items"]
    for node in nodes:
        assert any(c["type"] == "Ready" and c["status"] == "True" for c in node["status"]["conditions"]), "Node not Ready"
        info = node["status"]["nodeInfo"]
        assert info["kubeletVersion"] == LOCK["kubernetes"]["version"], "Kubernetes differs from runtime lock"
        assert info["architecture"] == "amd64" and info["operatingSystem"] == "linux"
    daemon = kube.get("daemonset", "calico-node", "-n", "kube-system")
    assert daemon["status"]["desiredNumberScheduled"] == 1 and daemon["status"]["numberReady"] == 1, "Calico node not Ready"
    controller = kube.get("deployment", "calico-kube-controllers", "-n", "kube-system")
    assert controller["status"].get("availableReplicas", 0) == 1, "Calico controller not Ready"
    for resource in (daemon, controller):
        spec = resource["spec"]["template"]["spec"]
        for container in spec.get("initContainers", []) + spec["containers"]:
            name, digest = container["image"].split("@")
            assert LOCK["calico"]["images"][name] == digest, "Calico image differs from runtime lock"


class NetworkFixture:
    def __init__(self, kube, name):
        self.kube = kube
        self.namespace = "corsair-net-" + uuid.uuid4().hex[:12]
        self.evidence = kube.evidence / name
        self.evidence.mkdir()
        self.uid = None

    def setup(self):
        self.kube.run("create", "namespace", self.namespace)
        self.uid = self.kube.get("namespace", self.namespace)["metadata"]["uid"]
        (self.evidence / "owner.json").write_text(json.dumps({"namespace": self.namespace, "uid": self.uid}))
        rendered = self.evidence / "manifests"
        rendered.mkdir()
        shutil.copyfile(FIXTURES / "fixtures.yaml", rendered / "fixtures.yaml")
        images = [{"name": name, "newName": spec["image"], "digest": spec["digest"]} for name, spec in LOCK["fixtures"].items()]
        (rendered / "kustomization.yaml").write_text(yaml.safe_dump({"apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization", "resources": ["fixtures.yaml"], "images": images}))
        self.kube.run("apply", "-n", self.namespace, "-k", rendered)
        self.kube.run("wait", "-n", self.namespace, "--for=condition=Ready", "pod", "--all", "--timeout=90s")
        pod = self.kube.get("pod", "echo", "-n", self.namespace)
        service = self.kube.get("service", "echo", "-n", self.namespace)
        self.endpoints = {"pod": pod["status"]["podIP"], "service": service["spec"]["clusterIP"]}
        self.wait_service(pod["metadata"]["uid"], service["metadata"]["uid"])

    def wait_service(self, pod_uid, service_uid):
        # Pod Ready and EndpointSlice Ready do not acknowledge proxy rule sync.
        # This pre-policy setup observation never replaces fresh strict controls.
        started = time.monotonic()
        deadline = started + 30
        receipt = {"namespace": self.namespace, "namespace_uid": self.uid,
                   "pod_uid": pod_uid, "service_uid": service_uid,
                   "started_at": datetime.now(timezone.utc).isoformat(),
                   "budget_seconds": 30, "ready": False, "attempts": []}
        try:
            assert not self.kube.get("networkpolicies", "-n", self.namespace, timeout=10)["items"], "Service setup requires no policies"
            while time.monotonic() < deadline:
                slices = self.kube.get("endpointslices", "-n", self.namespace, "-l", "kubernetes.io/service-name=echo", timeout=min(10, deadline - time.monotonic()))
                attempt = {"endpoint_command": f"command-{self.kube.counter:04d}.json", "requests": []}
                receipt["attempts"].append(attempt)
                endpoints = []
                for item in slices["items"]:
                    assert any(o["uid"] == service_uid and o["kind"] == "Service" for o in item["metadata"].get("ownerReferences", [])), "EndpointSlice Service identity changed"
                    if item.get("endpoints"):
                        assert item["ports"] == [{"name": "", "protocol": "TCP", "port": 5678}], "Unexpected Service port"
                    endpoints.extend(item.get("endpoints") or [])
                endpoint_ready = bool(endpoints)
                for endpoint in endpoints:
                    assert endpoint.get("targetRef", {}).get("uid") == pod_uid and endpoint["addresses"] == [self.endpoints["pod"]], "EndpointSlice Pod identity changed"
                    conditions = endpoint.get("conditions", {})
                    endpoint_ready &= conditions.get("ready") is True and conditions.get("terminating") is not True
                attempt["endpoint_ready"] = endpoint_ready
                if endpoint_ready:
                    markers = []
                    for probe in ("probe-allowed", "probe-denied"):
                        if time.monotonic() >= deadline:
                            break
                        result, marker = self.request(probe, self.endpoints["service"], "GET", timeout=min(20, deadline - time.monotonic()))
                        attempt["requests"].append({"probe": probe, "marker": marker, "command": f"command-{self.kube.counter:04d}.json", "exit_code": result.returncode})
                        if result.returncode == 0:
                            assert result.stdout == "corsair-network-ok\n\nSTATUS:200", "Unexpected Service setup response"
                            markers.append(marker)
                        else:
                            assert result.returncode in (7, 28) and result.stdout == "\nSTATUS:000", f"Unexpected Service setup failure: {result.stderr}"
                            break
                    if len(markers) == 2 and time.monotonic() < deadline:
                        logs = self.kube.run("logs", "-n", self.namespace, "echo", "--timestamps=true", timeout=min(10, deadline - time.monotonic())).stdout
                        assert all(marker in logs for marker in markers), "Service setup server log coverage missing"
                        assert time.monotonic() < deadline, "Service setup exceeded 30 seconds"
                        receipt["ready"] = True
                        return
                time.sleep(min(0.25, max(0, deadline - time.monotonic())))
            raise AssertionError("Service setup did not converge within 30 seconds; fresh controls not admitted")
        finally:
            receipt["elapsed_seconds"] = time.monotonic() - started
            (self.evidence / "service-readiness.json").write_text(json.dumps(receipt, indent=2))

    def policy(self, filename):
        self.kube.run("apply", "-n", self.namespace, "-f", FIXTURES / filename)

    def remove_policy(self, filename):
        self.kube.run("delete", "-n", self.namespace, "-f", FIXTURES / filename, "--wait=true")

    def logs(self):
        return self.kube.run("logs", "-n", self.namespace, "echo", "--timestamps=true").stdout

    def request(self, probe, address, method, timeout=20):
        marker = "request-" + uuid.uuid4().hex
        result = self.kube.run("exec", "-n", self.namespace, probe, "--", "curl", "--noproxy", "*", "--silent", "--show-error", "--connect-timeout", "2", "--max-time", "3", "--request", method, "--write-out", "\nSTATUS:%{http_code}", f"http://{address}:5678/{marker}", check=False, timeout=timeout)
        return result, marker

    def allowed(self, probe, converge=False):
        markers = []
        deadline = time.monotonic() + 30
        for address in self.endpoints.values():
            for method in ("GET", "POST"):
                while True:
                    result, marker = self.request(probe, address, method)
                    if result.returncode == 0:
                        break
                    if not converge or result.returncode != 28 or time.monotonic() >= deadline:
                        raise AssertionError(f"Expected reachable control: {result.stderr}")
                    time.sleep(1)
                assert result.stdout == "corsair-network-ok\n\nSTATUS:200"
                markers.append(marker)
        logs = self.logs()
        assert all(marker in logs for marker in markers), "Server log coverage missing for successful controls"

    def denied(self):
        # NetworkPolicy has no convergence status. Poll one fresh connection,
        # recording every attempt, then demand three fresh trials on both routes.
        deadline = time.monotonic() + 30
        while True:
            result, _ = self.request("probe-denied", self.endpoints["pod"], "GET")
            if result.returncode == 28 and result.stdout == "\nSTATUS:000":
                break
            assert result.returncode == 0, f"Unexpected failure; not a network-denial observation: {result.stderr}"
            assert time.monotonic() < deadline, "Policy did not converge to denial within 30 seconds"
            time.sleep(1)
        markers = []
        for _ in range(3):
            self.allowed("probe-allowed")
            for address in self.endpoints.values():
                for method in ("GET", "POST"):
                    result, marker = self.request("probe-denied", address, method)
                    assert result.returncode == 28 and result.stdout == "\nSTATUS:000", f"Expected curl timeout; got exit {result.returncode}: {result.stdout} {result.stderr}"
                    markers.append(marker)
        # Positive controls above established log coverage; absence supplements
        # the independent client timeout and rollback observations.
        logs = self.logs()
        assert not any(marker in logs for marker in markers), "A denied request reached the server"
        (self.evidence / "denials.json").write_text(json.dumps({"markers": markers, "routes": self.endpoints, "methods": ["GET", "POST"], "trials_per_route_method": 3}, indent=2))

    def cleanup(self):
        receipt = {"namespace": self.namespace, "uid": self.uid, "confirmed": False}
        try:
            if self.uid is None:
                raise RuntimeError("Namespace ownership unknown; refusing automatic deletion")
            for resource in ("pods", "services", "networkpolicies", "events"):
                self.kube.run("get", resource, "-n", self.namespace, "-o", "json", check=False)
            self.kube.run("logs", "-n", self.namespace, "echo", "--timestamps=true", check=False)
            current = self.kube.get("namespace", self.namespace)
            if current["metadata"]["uid"] != self.uid:
                raise RuntimeError("Namespace identity changed; refusing to delete replacement")
            self.kube.run("delete", "namespace", self.namespace, "--wait=true", "--timeout=90s")
            remaining = self.kube.run("get", "namespace", self.namespace, "--ignore-not-found", "-o", "json")
            if remaining.stdout.strip():
                raise RuntimeError("Namespace deletion not confirmed")
            receipt["confirmed"] = True
        finally:
            (self.evidence / "cleanup.json").write_text(json.dumps(receipt, indent=2))
