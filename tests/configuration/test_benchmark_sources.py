"""SPEC-0037: every inventory case resolves to one exact fix commit or a stated gap, and the committed pins agree."""
import json

from evals.benchmark.sources import PINS, SourceRequest, Unresolved, load_rows, resolve


def test_every_inventory_case_resolves_or_names_its_gap():
    rows = load_rows()
    results = {row['case_id']: resolve(row) for row in rows}
    # A row without a fix reference is the only kind left unresolved; every reference present is understood.
    assert {case for case, item in results.items() if isinstance(item, Unresolved)} == \
        {row['case_id'] for row in rows if not row['fixed_reference']}
    resolved = {case: item for case, item in results.items() if isinstance(item, SourceRequest)}
    references = {row['case_id']: row['fixed_reference'] for row in rows}
    assert all(item.target.commit in references[case] for case, item in resolved.items())
    # Pull-request commit pages and .patch links normalise to the repository and commit.
    assert (resolved['GHSA-xxvw-45rp-3mj2'].via, resolved['GHSA-xxvw-45rp-3mj2'].target.url) == \
        ('pull_request', 'https://github.com/nodeca/js-yaml')
    assert (resolved['CVE-2026-8450'].via, resolved['CVE-2026-8450'].target.url) == \
        ('patch', 'https://github.com/libwww-perl/HTTP-Daemon')
    # A fix hosted outside the inventory's repository is resolved where the commit is, and flagged.
    assert not resolved['CVE-2023-31486'].repository_matches_inventory
    # Acquisition follows no redirects, so a GitLab commit reference resolves to the canonical `.git` URL.
    assert resolved['CVE-2023-31486'].target.url == 'https://salsa.debian.org/perl-team/interpreter/perl.git'
    assert resolved['VUL4J-18'].repository_matches_inventory


def test_committed_pins_match_the_resolver():
    pins = json.loads(PINS.read_text())
    rows = load_rows()
    results = {row['case_id']: resolve(row) for row in rows}
    assert pins['unresolved'] == {case: item.reason for case, item in results.items() if isinstance(item, Unresolved)}
    assert set(pins['cases']) == {case for case, item in results.items() if isinstance(item, SourceRequest)}
    for case, record in pins['cases'].items():
        request = results[case]
        assert (record['url'], record['commit'], record['via']) == (request.target.url, request.target.commit, request.via)
        assert record['outcome'] in ('acquired', 'refused')
        if record['outcome'] == 'acquired':
            assert record['tree']['commit'] == record['commit']
            assert record['baseline_candidate'] in (None, *record['parents'])
        else:
            assert record['layer'] in ('host_network', 'source_unavailable', 'transport', 'budget',
                                       'source_admission', 'native_git', 'receipt_storage')
