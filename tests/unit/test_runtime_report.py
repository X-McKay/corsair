"""SPEC-0042 report: a case's `project_root` scopes which build files are fetched and detected."""
from evals.benchmark.cases import InventoryCase
from evals.benchmark.runtimes import evaluate, under

import pytest

PIN = {'cases': {'C': {'outcome': 'acquired', 'url': 'https://example.invalid/r.git', 'commit': 'f' * 40}}}


def write(root, files):
    for path, body in files.items():
        target = root / 'C' / ('f' * 40) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)


def test_project_root_scopes_detection(tmp_path):
    # Perl core layout (CVE-2023-31486): the module lives under cpan/HTTP-Tiny/ with no build file of its own, while a
    # sibling dist has one. Scoped to the module, the case is undetermined for that reason, not from the sibling.
    write(tmp_path, {'cpan/HTTP-Tiny/lib/HTTP/Tiny.pm': b'package HTTP::Tiny;\n', 'cpan/HTTP-Tiny/t/000_load.t': b'',
                     'cpan/Other/Makefile.PL': b'use 5.008;\n', 'Makefile.SH': b''})
    row = {'case_id': 'C', 'language': 'Perl', 'project_root': 'cpan/HTTP-Tiny'}
    [record] = evaluate(tmp_path, PIN, [row], {})
    assert record['project_root'] == 'cpan/HTTP-Tiny'
    assert record['status'] == 'undetermined' and record['revisions']['fix']['missing'] == ['no perl build file at the project root']
    # A build file under the root is read relative to it, and the requirement names the root.
    write(tmp_path, {'cpan/HTTP-Tiny/Makefile.PL': b'use 5.006;\n'})
    [record] = evaluate(tmp_path, PIN, [row], {})
    requirement = record['revisions']['fix']['requirement']
    assert requirement['root'] == 'cpan/HTTP-Tiny' and requirement['files'] == ['Makefile.PL']


def test_checkout_filter_and_inventory_field():
    assert under('cpan/HTTP-Tiny/Makefile.PL', 'cpan/HTTP-Tiny') == 'Makefile.PL'
    assert under('cpan/HTTP-Tiny-Extra/Makefile.PL', 'cpan/HTTP-Tiny') is None
    assert under('Makefile.PL', '') == 'Makefile.PL'
    base = dict(case_id='C', language='Perl', build_system='b', project='p', issue_id='i', issue_category='c', cwe=None,
                source='s', source_revision='r', source_record_url='u', repository_url=None, fixed_reference=None,
                vulnerable_reference=None, fixed_version_claim=None, oracle_supplied=False, license_status='l', notes='',
                runtime_qualified=False, qualification_status='candidate', retrieved_on='2026-10-13')
    assert InventoryCase(**base, project_root='cpan/HTTP-Tiny').project_root == 'cpan/HTTP-Tiny'
    for bad in ('/etc', '../x', 'a/../b', 'a/', ''):
        with pytest.raises(ValueError): InventoryCase(**base, project_root=bad)
