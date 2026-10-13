"""Authoring's Perl assertion lines: where a Test::More subtest fails on its own check, read lexically (SPEC-0074)."""
import json
from pathlib import Path

import pytest

from corsair.agents.test_authoring.static import assertion_lines
from corsair.reports.tap import parse_tap

RUNNER = Path(__file__).resolve().parents[1] / 'unit/tap_reports/runner'
FILE = '''use strict;
use warnings;
use Test::More;
my $re = qr{a/b}x; my %h = (s => 1, y => 2); my $half = $h{s} / 2;
# ok(1) in a comment, is(2) too
subtest(test_security => sub {
    my $out = Runner::run("a; ok(1)");   # is(1)
    like($out, qr/^a;/, 'literal');
    my $later = sub { ok(0) };
    $out =~ s{a}{b}g; $out =~ tr/a-z/A-Z/;
    is_deeply(
      [split /,/, $out],
      ['x'],
    );
    cmp_ok($half, '==', 1) if $out =~ m!x!;
    my %opts = (ok => 1); isnt($/, "x");
});
subtest test_control => sub { pass('nothing to check') };
done_testing;
'''


def test_subtest_ids_read_perl_and_count_only_calls_the_block_makes():
    assert assertion_lines(FILE, 't/case.t#test_security') == (8, 11, 15, 16)


def test_the_line_test_more_reports_for_a_failure_is_an_assertion_line():
    # The gate admits a security failure only at a planned assertion line; Perl 5.26.3 reported line 8 here.
    ids = ('t/fail.t#test_control', 't/fail.t#test_security')
    _, security = parse_tap((RUNNER / 'fail.tap').read_bytes(), ids, exit_status=1, test_paths=frozenset({'t/fail.t'}))
    assert security.failure.line in assertion_lines((RUNNER / 'fail.t').read_text(), ids[1])


@pytest.mark.parametrize('content, reason', [
    (FILE, 'has no assertion'),
    ('=pod\n\n=cut\nsubtest test_control => sub { ok(1) };\n', 'POD'),
    ('my $x = <<EOT;\nhi\nEOT\nsubtest test_control => sub { ok(1) };\n', 'heredoc'),
    ('sub ok { 1 }\nsubtest test_control => sub { ok(1) };\n', 'definition of an assertion name'),
    ('*main::is = sub { 1 };\nsubtest test_control => sub { is(1, 2) };\n', 'definition of an assertion name'),
    ('subtest test_control => sub { ok(1) };\nsubtest test_control => sub { ok(1) };\n', 'found 2'),
    ('subtest other => sub { ok(1) };\n', 'found 0'),
    ('subtest test_control => sub { ok("open };\n', 'unterminated'),
])
def test_what_the_reader_cannot_follow_is_refused_with_a_reason(content, reason):
    with pytest.raises(ValueError, match=reason):
        assertion_lines(content, 't/case.t#test_control')


CASES = Path(__file__).resolve().parents[2] / 'evals/case_e2e/operator_cases'


@pytest.mark.parametrize('name, spec', sorted(json.loads((CASES / 'cases.json').read_text()).items()))
def test_each_operator_case_declares_the_assertion_lines_the_reader_finds(name, spec):
    """The committed Docker cases (evals/case_e2e/operator_tests.py) plan the lines authoring would admit."""
    content = (CASES / name / spec['test'][1]).read_text()
    assert assertion_lines(content, spec['security']) == tuple(spec['assertion_lines'])
