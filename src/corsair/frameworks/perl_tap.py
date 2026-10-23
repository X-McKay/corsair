"""Perl adapter using native TAP execution and Devel::Cover statement evidence."""
from __future__ import annotations

import re
from collections.abc import Mapping

from .base import PROBE_DIR, RESULT_DIR, ProbeResult
from .reports import read_probe

DRIVER = r'''use strict;
use warnings;
use JSON::PP ();

my $role = $ENV{CORSAIR_ROLE};
my $result_path = $ENV{CORSAIR_RESULT};
my $junit_path = $ENV{CORSAIR_JUNIT};
my $encode_json = \&JSON::PP::encode_json;
my $true = JSON::PP::true;
my $false = JSON::PP::false;
my $expected = $role eq 'control';

sub xml_escape {
    my ($value) = @_;
    $value = '' unless defined $value;
    $value = substr($value, 0, 2000);
    $value =~ s/&/&amp;/g;
    $value =~ s/</&lt;/g;
    $value =~ s/>/&gt;/g;
    $value =~ s/"/&quot;/g;
    $value =~ s/'/&apos;/g;
    return $value;
}

sub record {
    my ($result, $invariant, $type, $message) = @_;
    open my $record, '>', $result_path or die "cannot write result: $!";
    print {$record} $encode_json->({
        role => $role, result => $result, exception_type => $type,
        message => defined($message) ? substr($message, 0, 2000) : undef,
        invariant_held => defined($invariant) ? ($invariant ? $true : $false) : undef,
    });
    close $record;
    my $problem = '';
    if ($result ne 'PASS') {
        my $tag = $result eq 'ERROR' ? 'error' : 'failure';
        $message = 'security invariant did not match the role expectation' unless defined $message;
        $problem = '<' . $tag . ' type="' . xml_escape($type) . '" message="' . xml_escape($message) . '"/>';
    }
    open my $junit, '>', $junit_path or die "cannot write junit: $!";
    print {$junit} '<testsuites><testsuite tests="1"><testcase name="test_probe[' . xml_escape($role)
        . ']">' . $problem . '</testcase></testsuite></testsuites>';
    close $junit;
}

my $loaded = eval { require CorsairProbe; 1 };
if (!$loaded) {
    my $message = "$@";
    record('ERROR', undef, 'CompileError', $message);
    print "not ok 1 - test_probe[$role]\n1..1\n";
    warn $message;
    exit 1;
}

my $payload = $role eq 'control' ? $CorsairProbe::CONTROL_PAYLOAD : $CorsairProbe::EXPLOIT_PAYLOAD;
my ($invariant, $error);
{
    local $@;
    $invariant = eval { CorsairProbe::run_target($payload) };
    $error = $@;
}
if (length $error) {
    my $type = ref($error) || 'RuntimeError';
    record('ERROR', undef, $type, "$error");
    print "not ok 1 - test_probe[$role]\n1..1\n";
    warn $error;
    exit 1;
}
if (ref($invariant) || !defined($invariant) || "$invariant" !~ /\A(?:|0|1)\z/) {
    my $message = 'run_target(payload) must return a scalar boolean';
    record('ERROR', undef, 'TypeError', $message);
    print "not ok 1 - test_probe[$role]\n1..1\n";
    warn "$message\n";
    exit 1;
}
my $actual = $invariant ? 1 : 0;
my $result = $actual == $expected ? 'PASS' : 'FAIL';
record($result, $actual, undef, undef);
print (($result eq 'PASS' ? 'ok' : 'not ok') . " 1 - test_probe[$role]\n1..1\n");
exit($result eq 'PASS' ? 0 : 1);
'''

COVERAGE_RENDERER = r'''use strict;
use warnings;
use Devel::Cover::DB;
use JSON::PP qw(encode_json);

my ($database, $output) = @ARGV;
my $db = Devel::Cover::DB->new(db => $database);
$db->merge_runs;
my $cover = $db->cover;
my %files;
while (my ($path, $file) = each %{$cover}) {
    my $statements = $file->{statement} || {};
    my @lines = sort { $a <=> $b } grep {
        my $entries = $statements->{$_};
        scalar grep { $_->covered } @{$entries};
    } keys %{$statements};
    $files{$path} = { executed_lines => \@lines };
}
open my $handle, '>', $output or die "cannot write coverage: $!";
print {$handle} encode_json({ files => \%files });
close $handle;
'''


class PerlTap:
    name = "perl-tap"
    language = "perl"
    target_suffixes = (".pm", ".pl", ".t")
    guidance = "perl-tap"
    probe_file = "CorsairProbe.pm"

    def guard(self, probe: str):
        from ..kernel import Gate, GateVerdict

        required = ("package CorsairProbe", "$CONTROL_PAYLOAD", "$EXPLOIT_PAYLOAD", "sub run_target")
        missing = [symbol for symbol in required if symbol not in probe]
        banned = re.search(r"\b(?:Test::Mock|Test::MockModule|Sub::Override)\b", probe)
        reason = (f"probe must define {', '.join(missing)}" if missing else
                  "mocking modules cannot own the observed property" if banned else
                  "symbol preflight passed; perl validates syntax and exports in the container")
        return GateVerdict(passed=not missing and banned is None, stage=Gate.AST_GUARD, reason=reason)

    def driver_files(self) -> dict[str, bytes]:
        return {"corsair_driver.t": DRIVER.encode(), "render_coverage.pl": COVERAGE_RENDERER.encode()}

    def command(self, role: str, target_file: str) -> list[str]:
        return ["perl", f"-MDevel::Cover=-db,{RESULT_DIR}/cover_db", "-I/work", f"-I{PROBE_DIR}",
                f"{PROBE_DIR}/corsair_driver.t"]

    def after_command(self) -> list[str]:
        return ["perl", f"{PROBE_DIR}/render_coverage.pl", f"{RESULT_DIR}/cover_db",
                f"{RESULT_DIR}/coverage.json"]

    def environment(self, role: str) -> Mapping[str, str]:
        return {"CORSAIR_ROLE": role, "CORSAIR_RESULT": f"{RESULT_DIR}/result.json",
                "CORSAIR_JUNIT": f"{RESULT_DIR}/junit.xml", "HOME": "/tmp", "PERL5LIB": "/work"}

    def result_paths(self) -> list[str]:
        return [f"{RESULT_DIR}/result.json", f"{RESULT_DIR}/junit.xml", f"{RESULT_DIR}/coverage.json"]

    def read(self, files: Mapping[str, bytes | None], hypothesis, role: str, source=None) -> ProbeResult:
        return read_probe(files, hypothesis, role, native_error_kind="error")
