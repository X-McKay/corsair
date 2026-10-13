"""SPEC-0025 in-sandbox pinned source fetch: fixed recipe, strict receipt, exact host admission.

Offline contract only; nothing here is live qualification. A refusal of any kind means the
caller discards the sandbox with confirmed cleanup; it is never repaired in place or retried.
The caller also owns sandbox creation, provider attachment and network narrowing.
"""
from dataclasses import dataclass
import re
import shutil
from urllib.parse import urlsplit
from uuid import UUID

from corsair.adapters.git_source import confined_path
from corsair.ports.artifacts import SourceSnapshot
from corsair.ports.execution import ExecutionError, ExecutionReceipt, SandboxExecution
from corsair.ports.sandbox import SandboxHandle

HOST = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+'
SHA1 = '[0-9a-f]{40}'

# Positional parameters: $1 shell, $2 git, $3 workdir, $4 url, $5 commit, $6 placeholder variable name,
# $7 '1' when the operator skips symlink and submodule entries (SPEC-0037), else empty.
# Variable data is never interpolated into the script text. Recipe refusals exit 65 (source content or
# workdir) or 66 (credential placeholder absent); any other nonzero exit is the fetch or hosting service.
PREAMBLE = r'''sh=$1 git=$2 dir=$3 url=$4 commit=$5 name=$6 skip=${7:-}
export LC_ALL=C GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0 GIT_LFS_SKIP_SMUDGE=1
g() { "$git" -c core.hooksPath=/dev/null -c protocol.allow=never -c protocol.https.allow=always \
  -c transfer.fsckObjects=true -c submodule.recurse=false -c core.autocrlf=false -c core.symlinks=false \
  -c credential.helper= -C "$dir" "$@"; }
fail() { printf 'corsair-source-fetch: %s\n' "$2" >&2; exit "$1"; }
'''
# The placeholder is sent as the basic-auth password. SPEC-0025 assumes the OpenShell proxy resolves
# basic-auth placeholders on egress to the bound host; unverified in pinned 0.1.3.
FETCH_PART = r'''mkdir -p -- "$dir"
cd -- "$dir"
[ -z "$(ls -A)" ] || fail 65 'workdir not empty'
g init -q >&2
if [ -n "$name" ]; then
  placeholder=$(printenv "$name") || fail 66 'credential placeholder absent'
  set -- -c "http.extraHeader=Authorization: Basic $(printf 'corsair:%s' "$placeholder" | base64 | tr -d '\n')"
else
  set --
fi
g "$@" fetch --depth=1 --no-tags "$url" "$commit" >&2
[ "$(g rev-parse --verify 'FETCH_HEAD^{commit}')" = "$commit" ] || fail 65 'fetched commit differs'
'''
# Raw blobs only: no checkout, so no .gitattributes eol/ident/encoding transformation applies.
MATERIALIZE_PART = r'''cd -- "$dir"
[ "$(ls -A)" = .git ] || fail 65 'workdir holds more than the fetched repository'
if [ "$skip" = 1 ]; then set -- -e '120000 blob' -e '160000 commit'; else set --; fi
if g ls-tree -r --full-tree "$commit" | cut -d' ' -f1,2 | grep -qvx -e '100644 blob' -e '100755 blob' "$@"; then
  fail 65 'only regular blobs admitted; symlinks and submodules refused'
fi
g ls-tree -rz --full-tree "$commit" > .git/corsair-tree
xargs -0 "$sh" -euc '
git=$1 skip=$2; shift 2; tab=$(printf "\t")
for rec; do
  meta=${rec%%"$tab"*}; path=${rec#*"$tab"}
  case $meta in
    "100644 blob "*) perm=644 ;;
    "100755 blob "*) perm=755 ;;
    "120000 blob "*|"160000 commit "*) [ "$skip" = 1 ] || exit 255; continue ;;
    *) exit 255 ;;
  esac
  case $path in */*) mkdir -p -- "${path%/*}" ;; esac
  "$git" cat-file blob "${meta##* }" > "$path"
  chmod "$perm" -- "$path"
done' corsair-materialize "$git" "$skip" < .git/corsair-tree
rm -f .git/corsair-tree
g update-ref --no-deref HEAD "$commit" >&2
'''
INVENTORY_PART = r'''cd -- "$dir"
head=$(g rev-parse --verify HEAD) tree=$(g rev-parse --verify 'HEAD^{tree}')
find . -path ./.git -prune -o ! -path . -exec "$sh" -euc '
for p; do
  hex=$(printf %s "${p#./}" | od -An -v -tx1 | tr -d " \n")
  if [ -h "$p" ]; then kind=l; elif [ -f "$p" ]; then kind=f; elif [ -d "$p" ]; then kind=d; else kind=o; fi
  mode=$(stat -c %a -- "$p") size=- sum=-
  if [ "$kind" = f ]; then size=$(stat -c %s -- "$p"); sum=$(sha256sum < "$p"); sum=${sum%% *}; fi
  printf "%s %s %s %s %s\n" "$hex" "$kind" "$mode" "$size" "$sum"
done' corsair-inventory {} + > .git/corsair-inventory
sort .git/corsair-inventory > .git/corsair-sorted
: > .git/corsair-skip
if [ "$skip" = 1 ]; then
  # What Git records for the skipped entries; the inventory below shows none of them reached the workdir.
  g ls-tree -rz --full-tree HEAD | xargs -0 "$sh" -euc '
tab=$(printf "\t")
for rec; do
  meta=${rec%%"$tab"*}; path=${rec#*"$tab"}
  case $meta in
    "120000 blob "*|"160000 commit "*)
      hex=$(printf %s "$path" | od -An -v -tx1 | tr -d " \n")
      printf "%s %s %s\n" "$hex" "${meta%% *}" "${meta##* }" ;;
  esac
done' corsair-skipped | sort > .git/corsair-skip
fi
count=$(wc -l < .git/corsair-sorted)
printf 'corsair-source-fetch v1\nhead %s\ntree %s\n' "$head" "$tree"
while read -r hex mode object; do printf 'skip %s %s %s\n' "$mode" "$object" "$hex"; done < .git/corsair-skip
while read -r hex kind mode size sum; do printf 'entry %s %s %s %s %s\n' "$kind" "$mode" "$size" "$sum" "$hex"; done < .git/corsair-sorted
printf 'end %s\n' $count
rm -f .git/corsair-inventory .git/corsair-sorted .git/corsair-skip
'''
FETCH_SCRIPT = PREAMBLE + FETCH_PART + MATERIALIZE_PART + INVENTORY_PART
MATERIALIZE_SCRIPT = PREAMBLE + MATERIALIZE_PART + INVENTORY_PART
INVENTORY_SCRIPT = PREAMBLE + INVENTORY_PART
EXIT_LAYERS = {65: 'source_admission', 66: 'credential'}


def absolute(path):
    if (not isinstance(path, str) or not path.startswith('/') or path == '/' or path.endswith('/')
            or any(p in ('', '.', '..') for p in path[1:].split('/')) or any(ord(c) < 33 or ord(c) == 127 for c in path)):
        raise ValueError('Canonical absolute path required')


@dataclass(frozen=True)
class FetchRecipe:
    """Operator-owned; `transport` is git's HTTPS remote helper, the binary that opens connections."""
    shell: str
    git: str
    transport: str
    workdir: str
    max_inventory_entries: int
    allowed_hosts: frozenset[str]
    skip_nonregular: bool = False  # must match the host capture's choice; admission compares the skipped entries

    def __post_init__(self):
        for path in (self.shell, self.git, self.transport, self.workdir): absolute(path)
        if type(self.max_inventory_entries) is not int or not 1 <= self.max_inventory_entries <= 65536:
            raise ValueError('Bounded operator inventory limit required')
        if (type(self.allowed_hosts) is not frozenset or not self.allowed_hosts
                or not all(isinstance(h, str) and re.fullmatch(HOST, h) for h in self.allowed_hosts)):
            raise ValueError('Nonempty frozenset of lowercase repository hosts required')
        if type(self.skip_nonregular) is not bool: raise ValueError('Explicit skip choice required')


@dataclass(frozen=True)
class CredentialBinding:
    """OpenShell provider bound to exactly the repository host; the workload sees only a placeholder."""
    provider: str
    env_name: str
    host: str

    def __post_init__(self):
        if (not isinstance(self.provider, str) or not re.fullmatch('[a-z0-9][a-z0-9-]{0,62}', self.provider)
                or not isinstance(self.env_name, str) or not re.fullmatch('[A-Z_][A-Z0-9_]{0,63}', self.env_name)
                or not isinstance(self.host, str) or not re.fullmatch(HOST, self.host)):
            raise ValueError('Provider name, placeholder variable and repository host required')


@dataclass(frozen=True)
class FetchTarget:
    url: str
    commit: str
    credential: CredentialBinding | None = None

    def __post_init__(self):
        if not isinstance(self.url, str) or not re.fullmatch(r'https://[a-z0-9.-]+(?:/[A-Za-z0-9._~%-]+)+', self.url):
            raise ValueError('Plain HTTPS repository URL without userinfo, port, query or fragment required')
        parts = urlsplit(self.url)
        if not re.fullmatch(HOST, parts.netloc) or any(p in ('.', '..') for p in parts.path.split('/')):
            raise ValueError('Canonical HTTPS repository URL required')
        if not isinstance(self.commit, str) or not re.fullmatch(SHA1, self.commit):
            raise ValueError('Exact 40-hex commit required')
        if self.credential is not None and (not isinstance(self.credential, CredentialBinding) or self.credential.host != self.host):
            raise ValueError('Credential binding must name exactly the repository host')

    @property
    def host(self) -> str:
        return urlsplit(self.url).netloc


def fetch_command(recipe: FetchRecipe, target: FetchTarget) -> tuple[str, ...]:
    if target.host not in recipe.allowed_hosts: raise ValueError('Repository host not operator-allowed')
    name = target.credential.env_name if target.credential else ''
    return (recipe.shell, '-euc', FETCH_SCRIPT, 'corsair-source-fetch', recipe.shell, recipe.git, recipe.workdir,
            target.url, target.commit, name, '1' if recipe.skip_nonregular else '')


@dataclass(frozen=True)
class FetchEntry:
    kind: str
    mode: str
    size: int | None
    sha256: str | None
    path: str


@dataclass(frozen=True)
class FetchInventory:
    head: str
    tree: str
    entries: tuple[FetchEntry, ...]
    skipped: tuple[tuple[str, str, str], ...] = ()  # (path, mode, object) Git records for skipped entries


SKIP = re.compile(r'skip (120000|160000) ([0-9a-f]{40}) ((?:[0-9a-f]{2})+)')
ENTRY = re.compile(r'entry ([fdlo]) ([0-7]{3,4}) (-|0|[1-9][0-9]*) (-|[0-9a-f]{64}) ((?:[0-9a-f]{2})+)')


def parse_fetch_receipt(stdout: bytes, max_entries: int) -> FetchInventory:
    if not isinstance(stdout, bytes) or not stdout.endswith(b'\n'): raise ValueError('Complete LF receipt required')
    lines = stdout[:-1].split(b'\n')
    if len(lines) < 4 or len(lines) - 4 > max_entries: raise ValueError('Receipt missing lines or inventory over bound')
    try: lines = [line.decode('ascii') for line in lines]
    except UnicodeDecodeError: raise ValueError('ASCII receipt required') from None
    head, tree, end = re.fullmatch(f'head ({SHA1})', lines[1]), re.fullmatch(f'tree ({SHA1})', lines[2]), re.fullmatch('end (0|[1-9][0-9]*)', lines[-1])
    if lines[0] != 'corsair-source-fetch v1' or not head or not tree or not end:
        raise ValueError('Malformed receipt identity or trailer')
    body, skipped, previous = lines[3:-1], [], ''
    while body and body[0].startswith('skip '):
        match = SKIP.fullmatch(body.pop(0))
        if not match: raise ValueError('Malformed skip line')
        mode, obj, hexpath = match.groups()
        if hexpath <= previous: raise ValueError('Skip lines not strictly sorted or duplicated')
        previous = hexpath
        try: path = bytes.fromhex(hexpath).decode('utf8')
        except UnicodeDecodeError: raise ValueError('UTF8 path required') from None
        confined_path(path)
        skipped.append((path, mode, obj))
    entries, previous = [], ''
    for line in body:
        match = ENTRY.fullmatch(line)
        if not match: raise ValueError('Malformed inventory line')
        kind, mode, size, digest, hexpath = match.groups()
        if (kind == 'f') == (size == '-') or (kind == 'f') == (digest == '-'):
            raise ValueError('Regular files need size and digest; other entries none')
        if hexpath <= previous: raise ValueError('Inventory not strictly sorted or duplicated')
        previous = hexpath
        try: path = bytes.fromhex(hexpath).decode('utf8')
        except UnicodeDecodeError: raise ValueError('UTF8 path required') from None
        confined_path(path)
        entries.append(FetchEntry(kind, mode, None if size == '-' else int(size), None if digest == '-' else digest, path))
    if int(end[1]) != len(entries): raise ValueError('Inventory count mismatch')
    return FetchInventory(head[1], tree[1], tuple(entries), tuple(skipped))


class SourceFetchRefused(RuntimeError):
    discard_sandbox = True

    def __init__(self, layer: str, reason: str, receipt: ExecutionReceipt | None = None):
        self.layer, self.reason, self.receipt = layer, reason, receipt
        super().__init__(f'{layer}: {reason}; discard the sandbox, never repair in place')


@dataclass(frozen=True)
class SourceFetchAdmission:
    commit: str
    tree: str
    file_count: int
    total_bytes: int
    elapsed_seconds: float
    operation: str


@dataclass(frozen=True)
class WorkspaceBudget:
    """Operator-owned pre-flight storage budget while no per-workspace quota is qualified (SPEC-0036 deferred).

    `workspace_bytes` is the gateway's configured workspace claim size; the captured tree may use at most a
    quarter of it, leaving the rest for `.git` and builds. `node_path` is where the node's storage lives on this
    host, and the run starts only if a full workspace still leaves `reserve_bytes` free there. This bounds
    neither bytes nor inodes during the run; it refuses cases that cannot fit and nodes already short of space.
    """
    workspace_bytes: int
    reserve_bytes: int
    node_path: str

    def __post_init__(self):
        absolute(self.node_path)
        for value in (self.workspace_bytes, self.reserve_bytes):
            if type(value) is not int or not 1 << 20 <= value <= 1 << 40: raise ValueError('Bounded byte budget required')


class WorkspaceBudgetRefused(RuntimeError):
    """Raised before any sandbox exists; nothing to discard."""

    def __init__(self, layer: str, reason: str):
        self.layer, self.reason = layer, reason
        super().__init__(f'{layer}: {reason}')


def admit_workspace_budget(snapshot: SourceSnapshot, budget: WorkspaceBudget, free_bytes: int) -> int:
    """Refuse a case that cannot fit the workspace or a node short of space; return the tree size."""
    if type(free_bytes) is not int or free_bytes < 0: raise ValueError('Measured free bytes required')
    tree_bytes = sum(f.artifact.size for f in snapshot.files)
    if tree_bytes * 4 > budget.workspace_bytes:
        raise WorkspaceBudgetRefused('sandbox', f'storage_budget: tree {tree_bytes} bytes exceeds a quarter of '
                                                f'the {budget.workspace_bytes}-byte workspace')
    if free_bytes < budget.workspace_bytes + budget.reserve_bytes:
        raise WorkspaceBudgetRefused('host', f'storage_budget: {free_bytes} bytes free at {budget.node_path}, '
                                             f'need {budget.workspace_bytes + budget.reserve_bytes}')
    return tree_bytes


def node_free_bytes(budget: WorkspaceBudget) -> int:
    return shutil.disk_usage(budget.node_path).free


def _secret_free(receipt, secrets):
    if not all(isinstance(s, bytes) and s for s in secrets): raise ValueError('Nonempty secret byte values required')
    if any(s in receipt.stdout or s in receipt.stderr for s in secrets):
        raise SourceFetchRefused('credential', 'secret value present in receipt output', receipt)


def admit_fetch(receipt: ExecutionReceipt, snapshot: SourceSnapshot, recipe: FetchRecipe, target: FetchTarget,
                *, secrets: tuple[bytes, ...] = ()) -> SourceFetchAdmission:
    if target.commit != snapshot.commit or target.host not in recipe.allowed_hosts:
        raise ValueError('Target must name the captured commit on an allowed host')
    _secret_free(receipt, secrets)
    if receipt.delivery != 'acknowledged' or receipt.completion != 'terminal_observed':
        raise SourceFetchRefused('sandbox', f'fetch outcome unknown ({receipt.reason}); no retry', receipt)
    if receipt.native_exit != 0:
        raise SourceFetchRefused(EXIT_LAYERS.get(receipt.native_exit, 'dependency'), f'fetch exit {receipt.native_exit}', receipt)
    try: inventory = parse_fetch_receipt(receipt.stdout, recipe.max_inventory_entries)
    except ValueError as error: raise SourceFetchRefused('source_admission', str(error), receipt) from error
    refuse = lambda reason: SourceFetchRefused('source_admission', reason, receipt)
    if (inventory.head, inventory.tree) != (snapshot.commit, snapshot.tree): raise refuse('commit or tree differs from capture')
    if snapshot.skipped and not recipe.skip_nonregular: raise ValueError('Capture skipped entries; the recipe must skip them too')
    if set(inventory.skipped) != {(s.path, s.mode, s.object) for s in snapshot.skipped}:
        raise refuse('skipped entries differ from capture')
    expected = {f.path: (f.mode[3:], f.artifact.size, f.artifact.sha256) for f in snapshot.files}
    directories = {'/'.join(p.split('/')[:n]) for p in expected for n in range(1, p.count('/') + 1)}
    files, seen = {}, set()
    for entry in inventory.entries:
        if entry.kind == 'f': files[entry.path] = (entry.mode, entry.size, entry.sha256)
        elif entry.kind == 'd' and entry.path in directories: seen.add(entry.path)
        elif entry.kind == 'd': raise refuse('extra directory ' + entry.path)
        else: raise refuse('non-regular entry ' + entry.path)
    if files.keys() - expected.keys(): raise refuse('extra file ' + min(files.keys() - expected.keys()))
    if expected.keys() - files.keys(): raise refuse('missing file ' + min(expected.keys() - files.keys()))
    if directories - seen: raise refuse('missing directory ' + min(directories - seen))
    changed = sorted(p for p in expected if files[p] != expected[p])
    if changed: raise refuse('mode, size or bytes differ: ' + changed[0])
    return SourceFetchAdmission(snapshot.commit, snapshot.tree, len(files), sum(v[1] for v in files.values()),
                                receipt.elapsed_seconds, receipt.operation)


def fetch_source(execution: SandboxExecution, handle: SandboxHandle, snapshot: SourceSnapshot, recipe: FetchRecipe,
                 target: FetchTarget, operation: UUID, *, secrets: tuple[bytes, ...] = ()) -> SourceFetchAdmission:
    """Exactly one native execution; the caller deletes the sandbox on any refusal."""
    if not isinstance(operation, UUID) or target.commit != snapshot.commit:
        raise ValueError('UUID operation and target naming the captured commit required')
    command = fetch_command(recipe, target)
    try: receipt = execution.execute(handle, command, operation)
    except ExecutionError as error:
        _secret_free(error.receipt, secrets)
        raise SourceFetchRefused(error.receipt.failure_layer or 'sandbox', error.receipt.reason, error.receipt) from error
    if receipt.operation != str(operation): raise SourceFetchRefused('sandbox', 'receipt names another operation', receipt)
    return admit_fetch(receipt, snapshot, recipe, target, secrets=secrets)
