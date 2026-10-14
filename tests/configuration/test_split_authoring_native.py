"""Pre-execution review binding for the explicit native fixture pilot."""
from hashlib import sha256

import pytest

from corsair.ports.test_runner import ApprovedPatch, PatchFile
from evals.experiments.split_authoring.native import execute_pair, sources, inventory_hashes


@pytest.mark.parametrize('change', ['patch', 'source', 'status', 'supporting_source'])
def test_stale_or_invalid_review_prevents_native_execution(tmp_path, change):
    patch = ApprovedPatch(tuple(PatchFile(path, b'# inert') for path in
        ('test_control.py', 'test_exploit.py')), ('test_control.py', 'test_exploit.py'))
    review = {'status': 'supported', 'patch_sha256': patch.sha256,
              'source_inventory': inventory_hashes(),
              'sources': {name: sha256(content).hexdigest() for name, content in sources().items()}}
    if change == 'patch':
        review['patch_sha256'] = '0' * 64
    elif change == 'source':
        review['sources']['safe'] = '0' * 64
    elif change == 'supporting_source':
        review['source_inventory']['safe']['test_existing.py'] = '0' * 64
    else:
        review['status'] = 'invalid'
    destination = tmp_path / 'native'
    with pytest.raises(ValueError, match='review must bind'):
        execute_pair(patch, review, destination)
    assert not destination.exists()
