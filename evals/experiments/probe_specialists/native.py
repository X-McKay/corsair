"""Explicit post-review fixture execution using existing offline Docker/native ports."""
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4
from pydantic import TypeAdapter
from corsair.adapters.docker_image import DockerCase, WORK
from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.adapters.pytest_runner import PytestRunner, PytestRunnerConfig
from corsair.ports.test_runner import NativeTestRun
from evals.experiments.split_authoring.native import IMAGE, COMMAND, limited_docker


def inventory_hashes(inventories):
    return {revision: {path: sha256(content).hexdigest() for path, content in files.items()} for revision, files in inventories.items()}


def execute_pair(patch, review, inventories, ids, destination):
    hashes = inventory_hashes(inventories)
    if review.get('status') != 'supported' or review.get('patch_sha256') != patch.sha256 or review.get('source_inventory') != hashes:
        raise ValueError('supported independent review must bind patch and complete captured inventory')
    if len(ids) != 2 or len(set(ids)) != 2 or {file.path for file in patch.files} != {identity.split('::')[0] for identity in ids}:
        raise ValueError('fixture execution requires exactly two approved probes')
    destination = Path(destination).resolve(); destination.mkdir(parents=True, exist_ok=False)
    (destination/'pre-execution-review.json').write_text(json.dumps(review, indent=2))
    store_root=destination/'objects';store_root.mkdir(mode=0o700)
    report={'patch_sha256':patch.sha256,'source_inventory':hashes,'image':IMAGE,'runs':{},'scope':'Controlled native fixture behavior only; no production deployment or broad runtime qualification.'}
    with LocalArtifacts(store_root,max_bytes=1024*1024) as store:
        for revision,files in inventories.items():
            work=destination/revision;tree=work/'source';tree.mkdir(parents=True)
            for path,content in files.items():
                target=tree/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
            identity=sha256(json.dumps(hashes[revision],sort_keys=True).encode()).hexdigest()
            with DockerCase(IMAGE,tree,identity,60,kind='probe-specialists',docker=limited_docker,
                    env=('PYTEST_DISABLE_PLUGIN_AUTOLOAD=1','PYTHONPATH=.'),evidence=work) as sandbox:
                runner=PytestRunner(sandbox,sandbox,store,PytestRunnerConfig(COMMAND,'.corsair-junit.xml',WORK))
                outcome=runner.run(patch,control_test_id=ids[0],security_test_id=ids[1],discovery_command=COMMAND+('--collect-only','-q'),operation=uuid4())
            report['runs'][revision]={'native':TypeAdapter(NativeTestRun).dump_python(outcome,mode='json'),'container_cleanup':sandbox.cleanup}
            (destination/'report.json').write_text(json.dumps(report,indent=2))
    return report
