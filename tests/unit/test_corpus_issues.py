"""Corpus cases as issue requests: reproducible local commits, neutral issue JSON, evaluator-only expected file."""
import json
import subprocess

from evals.corpus.cases import CORPUS, label_words, load, snapshot
from evals.corpus.issues import capture, main


def _tree(repository, sha):
    paths = subprocess.run(['git', '--git-dir', str(repository), 'ls-tree', '-r', '--name-only', sha],
                           capture_output=True, check=True, text=True).stdout.split()
    return {p: subprocess.run(['git', '--git-dir', str(repository), 'cat-file', 'blob', f'{sha}:{p}'],
                              capture_output=True, check=True).stdout for p in paths}


def test_a_pair_becomes_two_unrelated_reproducible_commits_and_a_neutral_issue(tmp_path):
    case = next(c for c in load() if c.case_id == 'ih-python-cmdi')
    issue, expected = capture(case, tmp_path / 'one')
    again, _ = capture(case, tmp_path / 'two')
    assert (issue['revision'], issue['fixed_revision']) == (again['revision'], again['fixed_revision'])
    repository = tmp_path / 'one' / case.case_id / 'repository.git'
    assert _tree(repository, issue['revision']) == snapshot(CORPUS / str(case.baseline.variant))
    assert _tree(repository, issue['fixed_revision']) == snapshot(CORPUS / str(case.candidate.variant))
    for sha in (issue['revision'], issue['fixed_revision']):
        parents = subprocess.run(['git', '--git-dir', str(repository), 'rev-list', '--parents', '-n1', sha],
                                 capture_output=True, check=True, text=True).stdout.split()
        assert parents == [sha]
    text = json.dumps(issue)
    assert label_words(json.dumps(issue['issue'])) == [] and str(case.baseline.variant) not in text and 'oracle' not in text
    assert expected['oracle']['gate'] == {'execution': 'completed', 'finding': 'reproduced', 'fix': 'verified'}
    assert json.loads((tmp_path / 'one' / case.case_id / 'issue.json').read_text()) == issue


def test_the_python_cohort_is_written_case_by_case(tmp_path, capsys):
    assert main(['--root', str(tmp_path), '--set', 'corpus']) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 17 and all((tmp_path / line.split()[0] / 'issue.json').is_file() for line in lines)


def test_the_committed_cohort_issue_files_are_what_the_generator_writes(tmp_path):
    import shutil
    from evals.cases import load_set
    from evals.corpus.issues import ISSUES
    for frozen in load_set('e2e', 'corpus'):
        case_id, committed = frozen.name, frozen.input
        assert committed['repository'] == f'evals/e2e/python/corpus/{case_id}/repository.git'
        case = next(c for c in load() if c.case_id == case_id)
        fresh, expected = capture(case, tmp_path)
        assert {**committed, 'repository': None} == {**fresh, 'repository': None}
        assert frozen.oracle == expected
        # The committed bare repository (as a clone has it, without empty directories) holds both commits.
        clone = tmp_path / 'clone' / case_id
        shutil.copytree(ISSUES / case_id / 'repository.git', clone)
        for sha in filter(None, (committed['revision'], committed.get('fixed_revision'))):
            assert _tree(clone, sha) == _tree(tmp_path / case_id / 'repository.git', sha)
