"""Perl adapter using native TAP execution and Devel::Cover statement evidence."""
from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from .base import PROBE_DIR, RESULT_DIR, PostCommand, ProbeResult
from .reports import read_probe

DRIVER = r'''use strict;
use warnings;
BEGIN {
    local @INC = grep { !ref($_) && $_ ne '.' && $_ !~ m{^/work(?:/|$)} } @INC;
    require JSON::PP;
}

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

COVERAGE_IDENTITY = r'''package CorsairCoverIdentity;
use strict;
use warnings;
use Digest::MD5 ();
use Digest::SHA ();
use File::Spec ();

my $installed;
sub install {
    return if $installed;
    require Devel::Cover::DB;
    require Devel::Cover::DB::Digests;
    my $failure = 'unsupported Devel::Cover identity API';
    die "$failure: Perl version\n" unless "$^V" eq 'v5.40.1';
    # These native 1.44 boundaries canonicalize paths and consume source digests.
    # Recharacterize vendor/API changes instead of silently accepting their data.
    my %expected = (
        'Devel::Cover' => '9e75f08a9875b6ab7be9c77f11e30e0ba277945d8ce753fa932874c5b891cde3',
        'Devel::Cover::DB' => '8ffe96855e19f5174ac4e7e203f48c70dbccf97673653c348f9600354e83bc03',
        'Devel::Cover::DB::Digests' => 'dd410a85aec2e775f47bedf81ec4aab8c3ccc57e85bad642a706bc58372c89fa',
        'Devel::Cover::DB::Structure' => '90b8d1678f98c167602a73d0efe9f604e696bf0e5be6817decfc3a3a901eca50',
    );
    # Loading the collector in the renderer would run its XS-only CHECK hook.
    my %sources = %INC;
    unless ($sources{'Devel/Cover.pm'}) {
        ($sources{'Devel/Cover.pm'} = $INC{'Devel/Cover/DB.pm'}) =~ s{/DB[.]pm\z}{.pm}
            or die "$failure: collector source layout\n";
    }
    for my $package (sort keys %expected) {
        no strict 'refs';
        my $version = ${"${package}::VERSION"};
        die "$failure: $package version\n" unless
            ($package eq 'Devel::Cover' && !defined($version)) || (defined($version) && $version eq '1.44');
        (my $module = "$package.pm") =~ s{::}{/}g;
        open my $source, '<', $sources{$module} or die "$failure: $module unavailable\n";
        binmode $source or die "$failure: $module unreadable\n";
        my $actual = Digest::SHA->new(256)->addfile($source)->hexdigest;
        close $source or die "$failure: $module close\n";
        die "$failure: $module changed\n" unless $actual eq $expected{$package};
    }
    die "$failure: digest/canonical_file/cover methods\n" unless
        defined(&Devel::Cover::DB::Structure::digest)
        && defined(&Devel::Cover::DB::Digests::canonical_file) && defined(&Devel::Cover::DB::cover);
    my $native_digest = \&Devel::Cover::DB::Structure::digest;
    no warnings 'redefine';
    *Devel::Cover::DB::Structure::digest = sub {
        die "$failure: digest arguments\n" unless @_ == 2 && defined($_[1]) && !ref($_[1]);
        my ($self, $file) = @_;
        my $content = $native_digest->(@_);
        return unless defined $content;
        die "$failure: digest result\n" unless $content =~ /\A[0-9a-f]{32}\z/;
        my $absolute = File::Spec->canonpath(File::Spec->rel2abs($file));
        return Digest::MD5->new->add("Corsair path identity v1\0", $absolute, "\0", $content)->hexdigest;
    };
    $installed = 1;
}
1;
'''

COVERAGE_BOOTSTRAP = r'''package CorsairCoverage;
use strict;
use warnings;
BEGIN {
    # Repository lookup resumes for the application after trusted collector imports.
    local @INC = grep { !ref($_) && $_ ne '.' && $_ !~ m{^/work(?:/|$)} } @INC;
    require Devel::Cover;
    require '/work/.corsair/CorsairCoverIdentity.pm';
    CorsairCoverIdentity::install();
    Devel::Cover->import;
}
1;
'''

COVERAGE_LAUNCHER = r'''set -eu
mode=$1
database=$2
shift 2
case "$mode" in reset|check) ;; *) exit 1 ;; esac
[ ! -L "$database" ] || { echo 'linked Perl coverage root' >&2; exit 1; }
if [ "$mode" = reset ] && [ ! -e "$database" ]; then
    mkdir -p "$database"
fi
[ -d "$database" ] || { echo 'Perl coverage root must be a directory' >&2; exit 1; }
invalid=$(find "$database" \( \( ! -type d -a ! -type f \) -o ! -readable -o ! -writable -o \( -type d -a ! -executable \) \) -print -quit)
[ -z "$invalid" ] || { echo 'invalid Perl coverage storage' >&2; exit 1; }
if [ "$mode" = reset ]; then
    # Clear only adapter-owned raw data, before any inherited Perl collector starts.
    find "$database" -mindepth 1 -delete
fi
exec "$@"
'''

COVERAGE_RENDERER = r'''use strict;
use warnings;
BEGIN {
    @INC = grep { !ref($_) && $_ ne '.' && $_ !~ m{^/work(?:/|$)} } @INC;
    require '/work/.corsair/CorsairCoverIdentity.pm';
    CorsairCoverIdentity::install();
}
use Devel::Cover::DB;
use JSON::PP qw(encode_json);
use Fcntl qw(:mode O_RDONLY O_NOFOLLOW);
use File::Compare qw(compare);
use File::Basename qw(dirname);
use File::Spec ();
use File::Temp qw(tempfile);

sub source_handle {
    my ($path, $expected) = @_;
    sysopen my $handle, $path, O_RDONLY | O_NOFOLLOW or die "cannot open source: $!";
    my @opened = stat $handle;
    die 'ambiguous source identity' unless @opened && S_ISREG($opened[2]) && $opened[3] == 1
        && $opened[0] == $expected->[0] && $opened[1] == $expected->[1] && $opened[7] == $expected->[7];
    binmode $handle or die "cannot read source bytes: $!";
    return $handle;
}

sub unique_prepared_source {
    my ($relative) = @_;
    return 0 unless defined($relative) && length($relative)
        && $relative !~ m{\A/|(?:\A|/)\.\.(?:/|\z)|\0};
    my $target = File::Spec->canonpath("/work/$relative");
    # Retain conservative prepared-tree inspection beside native path identity.
    return eval {
        my %sources;
        my @pending = ('/work');
        while (@pending) {
            my $path = pop @pending;
            my @metadata = lstat $path;
            die 'unreadable prepared source entry' unless @metadata;
            if (S_ISDIR($metadata[2])) {
                opendir my $directory, $path or die "cannot inspect prepared sources: $!";
                local $! = 0;
                my @entries = readdir $directory;
                die "cannot list prepared sources: $!" if $!;
                closedir $directory or die "cannot close source directory: $!";
                push @pending, map { "$path/$_" } grep { $_ ne '.' && $_ ne '..' } @entries;
                next;
            }
            die 'linked or nonregular prepared source' unless S_ISREG($metadata[2]) && $metadata[3] == 1;
            $sources{$path} = \@metadata;
        }
        my $metadata = $sources{$target} or die 'target source identity is missing';
        my $target_handle = source_handle($target, $metadata);
        for my $path (keys %sources) {
            next if $path eq $target || $sources{$path}[7] != $metadata->[7];
            my $candidate = source_handle($path, $sources{$path});
            seek $target_handle, 0, 0 or die "cannot rewind target source: $!";
            my $comparison = compare($candidate, $target_handle);
            close $candidate or die "cannot close candidate source: $!";
            die 'ambiguous prepared target source' if $comparison <= 0;
        }
        close $target_handle or die "cannot close target source: $!";
        1;
    } || 0;
}

my ($database, $output, $target) = @ARGV;
my %files;
if (unique_prepared_source($target)) {
    my $db = Devel::Cover::DB->new(db => $database);
    $db->merge_runs;
    my $cover = $db->cover;
    while (my ($path, $file) = each %{$cover}) {
        my $statements = $file->{statement} || {};
        my @lines = sort { $a <=> $b } grep {
            my $entries = $statements->{$_};
            scalar grep { $_->covered } @{$entries};
        } keys %{$statements};
        $files{$path} = { executed_lines => \@lines };
    }
}
my $directory = dirname($output);
my @directory = lstat $directory;
die 'coverage output parent must be a real directory' unless @directory && S_ISDIR($directory[2]);
my ($handle, $temporary) = tempfile('.coverage-XXXXXX', DIR => $directory, UNLINK => 1);
print {$handle} encode_json({ files => \%files }) or die "cannot write coverage: $!";
close $handle or die "cannot close coverage: $!";
rename $temporary, $output or die "cannot publish coverage: $!";
'''


def _unique_source_content(source: Path, target: str) -> bool:
    """Devel::Cover 1.44 canonicalizes byte-identical sources to one path."""
    try:
        root = source.resolve()
        target_path = root / target
        if not target_path.resolve().is_relative_to(root) or not target_path.is_file():
            return False
        content = target_path.read_bytes()
        for candidate in root.rglob("*"):
            if ".git" in candidate.relative_to(root).parts or candidate == target_path:
                continue
            if not candidate.is_file():
                continue
            if not candidate.resolve().is_relative_to(root):
                return False
            if candidate.stat().st_size == len(content) and candidate.read_bytes() == content:
                return False
    except (OSError, RuntimeError, ValueError):
        return False
    return True


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
        return {"corsair_driver.t": DRIVER.encode(), "render_coverage.pl": COVERAGE_RENDERER.encode(),
                "CorsairCoverage.pm": COVERAGE_BOOTSTRAP.encode(),
                "CorsairCoverIdentity.pm": COVERAGE_IDENTITY.encode(),
                "perl-coverage.sh": COVERAGE_LAUNCHER.encode()}

    def command(self, role: str, target_file: str) -> list[str]:
        return ["sh", f"{PROBE_DIR}/perl-coverage.sh", "reset", f"{RESULT_DIR}/cover_db",
                "perl", "-I/work", f"-I{PROBE_DIR}",
                f"{PROBE_DIR}/corsair_driver.t"]

    def post_command(self, role: str, target_file: str) -> PostCommand:
        environment = dict(self.environment(role))
        environment.pop("PERL5OPT")
        environment.pop("DEVEL_COVER_OPTIONS")
        # An omitted Docker exec overlay does not unset an image-level variable.
        return PostCommand(("env", "-u", "PERL5OPT", "-u", "DEVEL_COVER_OPTIONS", "sh",
                            f"{PROBE_DIR}/perl-coverage.sh", "check", f"{RESULT_DIR}/cover_db",
                            "perl", f"{PROBE_DIR}/render_coverage.pl", f"{RESULT_DIR}/cover_db",
                            f"{RESULT_DIR}/coverage.json", target_file), environment)

    def environment(self, role: str) -> Mapping[str, str]:
        return {"CORSAIR_ROLE": role, "CORSAIR_RESULT": f"{RESULT_DIR}/result.json",
                "CORSAIR_JUNIT": f"{RESULT_DIR}/junit.xml", "HOME": "/tmp", "PERL5LIB": "/work",
                "PERL5OPT": f"-I{PROBE_DIR} -MCorsairCoverage",
                "DEVEL_COVER_OPTIONS": f"-db,{RESULT_DIR}/cover_db,-merge,1,-silent,1,-coverage,statement,"
                                       "-select,^/work/(?![.]corsair/)"}

    def result_paths(self) -> list[str]:
        return [f"{RESULT_DIR}/result.json", f"{RESULT_DIR}/junit.xml", f"{RESULT_DIR}/coverage.json"]

    def read(self, files: Mapping[str, bytes | None], hypothesis, role: str, source=None) -> ProbeResult:
        normalized = dict(files)
        if source is None or not _unique_source_content(source, hypothesis.target_file):
            normalized[f"{RESULT_DIR}/coverage.json"] = None
        return read_probe(normalized, hypothesis, role, native_error_kind="error")
