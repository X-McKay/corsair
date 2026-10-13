"""One command per image for the live chain on this checkout's own kind cluster, plus cluster status and run archiving.

`run` drives the existing make targets in order and stops at the first failure: cluster (created only when this
checkout holds no receipt), admission (reused when an earlier run of this checkout still passes the installer's own
check on this node and lock), network (reused when it still passes the policy gate's own check), image build (only
when no prepared receipt exists) and load, gateway install, the toolchain gate, then a fresh gateway and the image's
real case. Every step logs under one run directory and the run ends with SUMMARY.md there. Reuse calls the same
`require_admission` and `require_network` checks the installer and gates apply; it adds no trust logic of its own.

It never runs `workspace-storage` or `kind-down`, never deletes or adopts state another run left behind, and never
retries a step: a retained gateway, image cache or foreign cluster stops the run with what to inspect.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from tests.qualification.support import ROOT

RUNS = ROOT / '.runs'
QUALIFY = RUNS / 'qualify'
KIND_STATE = ROOT / '.state/kind'
GATEWAY_STATE = ROOT / '.state/openshell'
TOOLCHAIN_CACHE = ROOT / '.cache/toolchains'
STEPS = ('tools', 'cluster', 'admission', 'network', 'image-build', 'image-load', 'gateway', 'gate', 'case-gateway',
         'case')
REUSE_CANDIDATES = 5


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def make_targets():
    return set(re.findall(r'^([a-z0-9][a-z0-9-]*):', (ROOT / 'Makefile').read_text(), re.M))


def case_ids(toolchain):
    """The cases `qualify-<toolchain>-case` runs, from its `CASES_<toolchain>` line in the Makefile."""
    found = re.search(rf'^CASES_{re.escape(toolchain)} := (.*)$', (ROOT / 'Makefile').read_text(), re.M)
    return found.group(1).split() if found else []


def make(target, log, variables):
    """One make target in this checkout; its whole output goes to `log`. Returns the exit code (None on a missing make)."""
    argv = ['make', '-C', str(ROOT), target, *(f'{k}={v}' for k, v in variables.items())]
    with log.open('w') as out:
        out.write('$ ' + ' '.join(argv) + '\n')
        out.flush()
        try:
            # The outer make's command-line variables would otherwise reach every inner target through MAKEFLAGS.
            env = {k: v for k, v in os.environ.items() if k not in ('MAKEFLAGS', 'MFLAGS', 'MAKELEVEL', 'MAKEOVERRIDES')}
            return subprocess.run(argv, stdout=out, stderr=subprocess.STDOUT, env=env, check=False).returncode
        except FileNotFoundError as error:
            out.write(str(error) + '\n')
            return None


class Cluster:
    """Read-only questions about this checkout's cluster, answered with the gates' own checks."""

    def __init__(self, evidence):
        self.evidence = evidence
        self._kube = None

    def kube(self):
        from tests.qualification.support import Kubectl
        if self._kube is None:
            self.evidence.mkdir(parents=True, exist_ok=True)
            self._kube = Kubectl(KIND_STATE / 'kubeconfig', 'kind-corsair', self.evidence)
        return self._kube

    def owned(self):
        return (KIND_STATE / 'owner.json').is_file()

    def node_uid(self):
        from tests.qualification.support import require_owned_cluster
        return require_owned_cluster(self.kube())['metadata']['uid']

    def sandbox_installed(self):
        return bool(self.kube().run('get', 'crd', 'sandboxes.agents.x-k8s.io', '--ignore-not-found', '-o', 'name').stdout.strip())

    def admission_ok(self, path):
        from tests.qualification.install_gateway import require_admission
        require_admission(self.kube(), path)

    def network_ok(self, path):
        from tests.qualification.test_policy import require_network
        require_network(self.kube(), path)


def reuse(check, explicit, pattern):
    """The first candidate the gate's own check accepts: the explicit path, else this checkout's newest runs."""
    tried = []
    candidates = [Path(explicit)] if explicit else sorted(QUALIFY.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)[:REUSE_CANDIDATES]
    for candidate in candidates:
        try:
            check(candidate)
            return candidate, tried
        except Exception as error:  # Any refusal by the gate's check means "not reusable"; the reason is kept.
            tried.append({'path': str(candidate), 'refused': f'{type(error).__name__}: {error}'[:500]})
    return None, tried


def image_cache_state(toolchain):
    """'absent', 'prepared' (receipt matches the current sources) or why a retained attempt cannot be used."""
    from tests.qualification.prepare_toolchains import BASES, source_hashes
    cache = TOOLCHAIN_CACHE / toolchain
    if not cache.exists():
        return 'absent'
    build = cache / 'build.json'
    if not build.is_file():
        return f'{cache} holds an attempt without build.json; inspect and archive it, never delete it to force a rebuild'
    try:
        receipt = json.loads(build.read_text())
    except (OSError, UnicodeDecodeError, ValueError) as error:
        return f'{build} cannot be read as a receipt ({type(error).__name__}: {error}); inspect and archive {cache}, never delete it to force a rebuild'
    if not isinstance(receipt, dict):
        return f'{build} holds a {type(receipt).__name__}, not a receipt object; inspect and archive {cache}, never delete it to force a rebuild'
    if receipt.get('sources') != source_hashes(toolchain) or receipt.get('base') != BASES[toolchain] or receipt.get('trusted_control_passed') is not True:
        return f'{build} was prepared from other sources or base, or its trusted control did not pass; inspect and archive {cache}'
    return 'prepared'


class Run:
    def __init__(self, toolchain, case, root, cluster, runner=make, admission=None, network=None):
        self.toolchain, self.case, self.root = toolchain, case, root
        self.cluster, self.runner = cluster, runner
        self.explicit = {'admission': admission, 'network': network}
        self.steps = {name: {'outcome': 'unrun'} for name in STEPS}
        self.facts = {}

    def step(self, name, target, **variables):
        started = time.monotonic()
        log = self.root / 'logs' / f'{name}-{target}.log'
        code = self.runner(target, log, variables)
        record = self.steps[name]
        # A step may take several targets (admission-artifacts, admission-install, qualify-admission); each keeps its log.
        record.setdefault('commands', []).append({'command': ' '.join(['make', target, *(f'{k}={v}' for k, v in variables.items())]),
                                                  'log': str(log.relative_to(self.root)), 'exit': code})
        record.update(outcome='passed' if code == 0 else 'failed', log=str(log.relative_to(self.root)),
                      seconds=round(record.get('seconds', 0) + time.monotonic() - started, 1))
        if code != 0:
            raise Stop(name, f'make {target} exited {code}; see {record["log"]}')

    def refuse(self, name, detail):
        self.steps[name].update(outcome='failed', detail=detail)
        raise Stop(name, detail)

    def execute(self):
        (self.root / 'logs').mkdir(parents=True)
        try:
            self.step('tools', 'tools')
            if self.cluster.owned():
                self.steps['cluster'].update(outcome='reused', detail='this checkout holds .state/kind/owner.json')
            else:
                self.step('cluster', 'kind-up')
            try:
                self.facts['node_uid'] = self.cluster.node_uid()
            except Exception as error:
                self.refuse('cluster', f'owned cluster check refused: {error}; run make cluster-status')
            admission = self.admission()
            network = self.network()
            self.images()
            self.gateway('gateway', admission)
            self.step('gate', 'qualify-toolchain', TOOLCHAINS=self.toolchain, CORSAIR_NETWORK_RUN=network,
                      CORSAIR_QUAL_RUN=self.root / 'toolchain')
            if self.case:
                # The gate's teardown uninstalled its gateway; the case gets a fresh one from the same admission.
                self.gateway('case-gateway', admission)
                self.step('case', f'qualify-{self.toolchain}-case', CASE=self.case, CORSAIR_NETWORK_RUN=network,
                          CORSAIR_QUAL_RUN=self.root / 'case')
            else:
                self.steps['case-gateway'].update(outcome='skipped', detail='no CASE given')
                self.steps['case'].update(outcome='skipped', detail='no CASE given; a matrix row still needs one real case')
            return Stop(None, None)
        except Stop as stop:
            return stop

    def reused(self, name, check, pattern):
        path, tried = reuse(check, self.explicit[name], pattern)
        self.steps[name]['refused_candidates'] = tried
        if self.explicit[name] and not path:
            # The operator asked for this evidence; running a fresh check instead would answer a different question.
            self.refuse(name, f'the {name} evidence named explicitly was refused: {tried[0]["refused"]}')
        return path

    def admission(self):
        path = self.reused('admission', self.cluster.admission_ok, '*/admission')
        record = self.steps['admission']
        if path:
            record.update(outcome='reused', evidence=str(path))
            return path
        if not self.cluster.sandbox_installed():
            self.step('admission', 'admission-artifacts')
            self.step('admission', 'admission-install')
        self.step('admission', 'qualify-admission', CORSAIR_QUAL_RUN=self.root / 'admission')
        record['evidence'] = str(self.root / 'admission')
        return self.root / 'admission'

    def network(self):
        path = self.reused('network', self.cluster.network_ok, '*/network')
        record = self.steps['network']
        if path:
            record.update(outcome='reused', evidence=str(path))
            return path
        self.step('network', 'qualify-network', CORSAIR_QUAL_RUN=self.root / 'network')
        record['evidence'] = str(self.root / 'network')
        return self.root / 'network'

    def images(self):
        state = image_cache_state(self.toolchain)
        if state == 'prepared':
            self.steps['image-build'].update(outcome='reused', detail=f'.cache/toolchains/{self.toolchain}/build.json matches the sources')
        elif state == 'absent':
            self.step('image-build', 'toolchain-images', TOOLCHAINS=self.toolchain)
        else:
            self.refuse('image-build', state)
        self.step('image-load', 'toolchain-images-load', TOOLCHAINS=self.toolchain)

    def gateway(self, name, admission):
        if GATEWAY_STATE.exists():
            self.refuse(name, f'{GATEWAY_STATE} is retained from an earlier install; inspect it, then let make qualify-gateway '
                              'consume and uninstall it with its controls, never delete it by hand')
        self.step(name, 'openshell-install', CORSAIR_ADMISSION_RUN=admission)


class Stop(Exception):
    def __init__(self, step, detail):
        super().__init__(detail)
        self.step, self.detail = step, detail


def git(*args):
    result = subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def write_summary(run, stop, started, finished, identity):
    outcome = 'passed' if stop.step is None else 'failed'
    if outcome == 'passed' and not run.case:
        outcome = 'gate passed; case unrun'
    data = dict(identity, toolchain=run.toolchain, case=run.case, outcome=outcome, failed_step=stop.step,
                detail=stop.detail, started_at=started, finished_at=finished, steps=run.steps, **run.facts)
    (run.root / 'summary.json').write_text(json.dumps(data, indent=2, default=str))
    lines = [f'# Qualify {run.toolchain}' + (f' with {run.case}' if run.case else ''), '',
             f'- Outcome: **{outcome}**' + (f' at step `{stop.step}`: {stop.detail}' if stop.step else ''),
             f'- Checkout: `{ROOT}` at `{identity["commit"]}` ({identity["branch"]})',
             f'- Node: `{run.facts.get("node_uid", "unknown")}`',
             f'- Started {started}, finished {finished}', '',
             '| Step | Outcome | Seconds | Evidence or log | Detail |', '| --- | --- | --- | --- | --- |']
    for name in STEPS:
        step = run.steps[name]
        detail = (step.get('detail') or '').replace('|', '/')
        if step.get('refused_candidates'):
            detail = (detail + ' ' if detail else '') + f'{len(step["refused_candidates"])} earlier run(s) refused for reuse (summary.json)'
        lines.append(f'| {name} | {step["outcome"]} | {step.get("seconds", "")} | {step.get("evidence") or step.get("log", "")} | {detail} |')
    lines += ['', 'Gate and case results, sandbox ids and cleanup are in their own evidence directories (toolchain/, case/).',
              'Admission and network reuse used the installer and policy gate checks on this node and runtime lock.']
    (run.root / 'SUMMARY.md').write_text('\n'.join(lines) + '\n')
    return outcome


def command_run(args):
    from tests.qualification.prepare_toolchains import BASES
    if args.toolchain not in BASES:
        raise SystemExit(f'Unknown TOOLCHAIN {args.toolchain!r}; prepared image directories: {sorted(BASES)}')
    if args.case and (f'qualify-{args.toolchain}-case' not in make_targets() or args.case not in case_ids(args.toolchain)):
        # Checked before anything is installed: a refused case after the case gateway would leave that gateway behind.
        raise SystemExit(f'qualify-{args.toolchain}-case does not run {args.case}; it runs {case_ids(args.toolchain) or "nothing"}. '
                         'Run without CASE for the gate alone')
    # Untracked files count too (a stray test module would be collected); ignored .runs, .state and .cache do not.
    dirty = git('status', '--porcelain', '--untracked-files=all')
    if dirty:
        raise SystemExit('The checkout differs from its commit; evidence must name one commit. Commit, stash or remove:\n' + dirty)
    root = QUALIFY / (args.run or f'{args.toolchain}-{stamp()}')
    if root.exists():
        raise SystemExit(f'{root} exists; evidence is never overwritten, pick another RUN')
    os.umask(0o077)
    identity = {'commit': git('rev-parse', 'HEAD'), 'branch': git('rev-parse', '--abbrev-ref', 'HEAD'), 'checkout': str(ROOT)}
    run = Run(args.toolchain, args.case, root, Cluster(root / 'checks'), admission=args.admission, network=args.network)
    started = datetime.now(timezone.utc).isoformat()
    stop = run.execute()
    outcome = write_summary(run, stop, started, datetime.now(timezone.utc).isoformat(), identity)
    print((root / 'SUMMARY.md').read_text())
    print(f'Summary: {root / "SUMMARY.md"}')
    raise SystemExit(0 if stop.step is None else 1)


def command_status(args):
    """Read-only: who holds the cluster from this checkout's view, what is installed, what could be reused."""
    from tests.qualification.prepare_toolchains import BASES
    evidence = RUNS / 'cluster-status' / stamp()
    cluster = Cluster(evidence)
    status = {'checkout': str(ROOT), 'commit': git('rev-parse', 'HEAD'), 'owner_receipt': cluster.owned(),
              'gateway_state_retained': GATEWAY_STATE.exists()}
    found = subprocess.run(['docker', '--host=unix:///var/run/docker.sock', 'inspect', '--format', '{{.Id}}', 'corsair-control-plane'],
                           capture_output=True, text=True, check=False)
    status['corsair_container'] = found.stdout.strip() if found.returncode == 0 else None
    if status['owner_receipt']:
        status['owner_container'] = json.loads((KIND_STATE / 'owner.json').read_text()).get('container_id')
        try:
            status['node_uid'] = cluster.node_uid()
            status['agent_sandbox_installed'] = cluster.sandbox_installed()
            status['admission_reusable'] = str(reuse(cluster.admission_ok, None, '*/admission')[0])
            status['network_reusable'] = str(reuse(cluster.network_ok, None, '*/network')[0])
        except Exception as error:
            status['refused'] = f'{type(error).__name__}: {error}'[:500]
    elif status['corsair_container']:
        status['note'] = 'A corsair cluster exists but this checkout holds no receipt: another checkout holds it.'
    status['prepared_images'] = {name: image_cache_state(name) for name in sorted(BASES) if (TOOLCHAIN_CACHE / name).exists()}
    print(json.dumps(status, indent=2))


def main_checkout():
    common = git('rev-parse', '--path-format=absolute', '--git-common-dir')
    return Path(common).parent if common else None


def command_archive(args):
    """Copy this worktree's .runs into the main checkout's .runs before the worktree is deleted; nothing is removed."""
    main = main_checkout()
    if main is None or main.resolve() == ROOT.resolve():
        raise SystemExit('This is the main checkout; archive-runs copies a worktree\'s .runs into the main checkout')
    if not RUNS.is_dir():
        raise SystemExit(f'{RUNS} does not exist; nothing to archive')
    name = str(ROOT.resolve().relative_to(main.resolve() / '.worktrees')).replace('/', '-') if ROOT.resolve().is_relative_to(main.resolve() / '.worktrees') else ROOT.name
    destination = Path(args.dest) if args.dest else main / '.runs' / 'worktrees' / f'{name}-{stamp()}'
    if destination.exists():
        raise SystemExit(f'{destination} exists; never merged into or overwritten')
    if destination.resolve().is_relative_to(RUNS.resolve()):
        raise SystemExit('Destination is inside the source .runs')
    os.umask(0o077)
    shutil.copytree(RUNS, destination, symlinks=True)
    count = lambda root: sorted((str(p.relative_to(root)), p.lstat().st_size) for p in root.rglob('*') if p.is_file() or p.is_symlink())
    source, copied = count(RUNS), count(destination)
    if source != copied:
        raise SystemExit(f'Copy differs from {RUNS} ({len(source)} vs {len(copied)} files); keep the worktree and inspect {destination}')
    (destination / 'ARCHIVE.json').write_text(json.dumps({'source': str(RUNS), 'commit': git('rev-parse', 'HEAD'),
                                                          'branch': git('rev-parse', '--abbrev-ref', 'HEAD'),
                                                          'files': len(source), 'bytes': sum(s for _, s in source),
                                                          'archived_at': datetime.now(timezone.utc).isoformat()}, indent=2))
    print(f'Archived {len(source)} files from {RUNS} to {destination}; the worktree may now be removed')


def optional(pattern):
    """argparse type: '' (make passes every option) means not given; anything else must match `pattern`."""
    def parse(value):
        if not value:
            return None
        if not re.fullmatch(pattern, value):
            raise argparse.ArgumentTypeError(f'{value!r} is not allowed here')
        return value
    return parse


NAME = r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}'
PATH = r'[A-Za-z0-9._/-]{1,1024}'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run', help='Live chain for one image (make qualify-image)')
    run.add_argument('--toolchain', required=True, help='Image directory under deploy/qualification/toolchains')
    run.add_argument('--case', type=optional(NAME), help='Benchmark case id for the image\'s qualify-<dir>-case target')
    run.add_argument('--run', type=optional(NAME), help='Run directory name under .runs/qualify (default <toolchain>-<UTC stamp>)')
    run.add_argument('--admission', type=optional(PATH), help='Admission evidence to try first instead of this checkout\'s newest runs')
    run.add_argument('--network', type=optional(PATH), help='Network evidence to try first instead of this checkout\'s newest runs')
    run.set_defaults(handler=command_run)
    commands.add_parser('status', help='Read-only cluster and evidence status (make cluster-status)').set_defaults(handler=command_status)
    archive = commands.add_parser('archive', help='Copy this worktree\'s .runs into the main checkout (make archive-runs)')
    archive.add_argument('--dest', type=optional(PATH), help='Destination directory (default <main checkout>/.runs/worktrees/<worktree>-<stamp>)')
    archive.set_defaults(handler=command_archive)
    args = parser.parse_args(argv)
    args.handler(args)


if __name__ == '__main__':
    main()
