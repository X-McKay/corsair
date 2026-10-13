"""Workload-side scan for one fake credential, run as `python3 -c SCAN prefix length sha256 key root...`.

The scanner never receives the credential: it hashes each fixed-length window that starts with
the known public prefix and compares it with the expected digest. It reports the credential env
variable's value only when it is not the credential. Unreadable or truncated scopes are reported
as unknown, never as absent.
"""

SCAN = r'''
import hashlib, json, os, stat, sys
prefix, length, digest, key, roots = sys.argv[1].encode(), int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5:]
MAX_FILES, MAX_FILE, MAX_TOTAL = 20000, 4 << 20, 256 << 20
total = 0
def hits(data):
    found, start = 0, data.find(prefix)
    while start >= 0:
        found += hashlib.sha256(data[start:start + length]).hexdigest() == digest
        start = data.find(prefix, start + 1)
    return found
def value(raw):
    if raw is None:
        return {'present': False}
    is_dummy = hashlib.sha256(raw.encode()).hexdigest() == digest
    return {'present': True, 'is_dummy': is_dummy, 'value': None if is_dummy else raw}
out = {'env': value(os.environ.get(key)), 'placeholders': {}, 'processes': {}, 'roots': {}}
out['placeholders'] = {k: v for k, v in os.environ.items() if v.startswith('openshell:')}
for pid in sorted(p for p in os.listdir('/proc') if p.isdigit()):
    try:
        data = open(f'/proc/{pid}/environ', 'rb').read()
    except OSError as error:
        out['processes'][pid] = {'state': 'unknown', 'error': type(error).__name__}
        continue
    env = dict(e.split(b'=', 1) for e in data.split(b'\0') if b'=' in e)
    raw = env.get(key.encode())
    out['processes'][pid] = {'state': 'scanned', 'matches': hits(data),
                             'env': value(None if raw is None else raw.decode(errors='replace'))}
for root in roots:
    record = out['roots'][root] = {'state': 'scanned', 'files': 0, 'bytes': 0, 'matches': [], 'unreadable': [], 'truncated': []}
    if not os.path.lexists(root):
        record['state'] = 'absent'
        continue
    def unreadable(path, error):
        record['unreadable'].append([path, type(error).__name__])
    for parent, dirs, files in os.walk(root, onerror=lambda e: unreadable(e.filename, e)):
        for name in files:
            path = os.path.join(parent, name)
            if record['files'] >= MAX_FILES or total >= MAX_TOTAL:
                record['truncated'].append(path)
                continue
            try:
                info = os.lstat(path)
                if not stat.S_ISREG(info.st_mode):
                    continue
                with open(path, 'rb') as handle:
                    data = handle.read(MAX_FILE + 1)
            except OSError as error:
                unreadable(path, error)
                continue
            if len(data) > MAX_FILE:
                record['truncated'].append(path)
            record['files'] += 1
            record['bytes'] += len(data)
            total += len(data)
            if hits(data):
                record['matches'].append(path)
    if record['unreadable'] or record['truncated']:
        record['state'] = 'partial'
    for field in ('unreadable', 'truncated'):
        record[field + '_count'] = len(record[field])
        record[field] = record[field][:50]
print(json.dumps(out, sort_keys=True))
'''
