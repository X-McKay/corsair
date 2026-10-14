"""Drives replay x2, run_probe, diagnose and sweep against the fake docker CLI on PATH (see test_docker_argv.py)."""
import sys, uuid, hashlib, os
from pathlib import Path
sys.path.insert(0, "src"); sys.path.insert(0, ".")
uuid.uuid4 = lambda: uuid.UUID(int=7)  # deterministic run ids
import secrets; secrets.token_hex = lambda n=16: "t" * (2*n)
from tests.v2.test_build_replay import BASELINE, RUNTIME, make_case
from corsair.v2.build import replay
from corsair.v2 import execute, reconcile
from corsair.v2.contracts import Recipe, ProbeDraft, FrozenPatch
tmp = Path(sys.argv[1]); tmp.mkdir(parents=True, exist_ok=True)
case = make_case(tmp)
for net in (False, True):
    r = Recipe(setup=(("pip", "install", "-e", "."),), network_during_setup=net, baseline_test=BASELINE)
    built, env = replay(case, RUNTIME, r, run_id="run1", artifacts=tmp / "art")
    print("REPLAY", built.replayed, built.reason, built.cleanup_confirmed, env)
from tests.v2.test_execute import draft, frozen, SYNTAX_RUNTIME
from corsair.v2.contracts import Environment
envir = Environment(image="corsair-v2-env:abc", workdir="/work", runtime_row="python312-pytest", recipe_sha256="a"*64, tree_sha256="b"*64)
patch = frozen(draft("control", "True", test_file="tests/corsair/test_control.py"), draft("exploit", "False"))
run = execute.run_probe(envir, RUNTIME, patch, "exploit", run_id="run1", artifacts=tmp / "art")
print("RUN", run.facts, run.outcome, run.cleanup_confirmed, run.image_digest)
print("DIAG", execute.diagnose(envir, SYNTAX_RUNTIME, patch.control, run_id="run1"))
print("SWEEP", reconcile.sweep("run1"))
