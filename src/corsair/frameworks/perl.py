"""Perl coverage layered over the kernel's one Python pytest driver.

The submitted Python probe starts the native Perl target with ``subprocess``. Its
child inherits ``PERL5OPT`` so Devel::Cover records statement coverage under the
isolated result directory.  ``cover -report json`` deliberately is not used:
its built-in JSON report is summary-only.  Instead, the kernel-owned collector
reads the Devel::Cover database API and emits a coverage.py-compatible exact
source map for the inherited Python reader.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from .base import PROBE_DIR, RESULT_DIR, ProbeResult
from .pytest_ import Pytest, read_coverage

PERL_DB = f"{RESULT_DIR}/perl"
PERL_COVERAGE_JSON = f"{RESULT_DIR}/perl-coverage.json"
_PERL_COLLECTOR = f"{PROBE_DIR}/collect_perl_coverage.pl"


# This is trusted kernel code written beside the driver.  It intentionally uses
# Devel::Cover::DB rather than ``cover -report json``: Report::Json writes only
# aggregate summaries, whereas DB->cover->file(...)->statement exposes the
# individual statement hit counts used by Report::Text.
PERL_COVER_COLLECTOR = r'''use strict;
use warnings;
use JSON::PP;
use Devel::Cover::DB;

my $DB_DIR = "/tmp/corsair/perl";
my $REPORT = "/tmp/corsair/perl-coverage.json";
my $WORKDIR = "/work";

sub work_file {
    my ($path) = @_;
    return unless defined $path && !ref $path;
    my $relative;
    if (index($path, "$WORKDIR/") == 0) {
        $relative = substr($path, length($WORKDIR) + 1);
    } elsif ($path !~ m{\A/}) {
        # Devel::Cover 1.38 in Debian Bookworm stores files relative to its
        # collection directory, while newer releases retain absolute names.
        $relative = $path;
    } else {
        return;
    }
    return unless length $relative;
    return if $relative =~ m{(?:^|/)(?:\.|\.\.)(?:/|$)};
    return "$WORKDIR/$relative";
}

sub write_report {
    my ($files) = @_;
    my $temporary = "$REPORT.$$";
    open my $out, ">:raw", $temporary or die "open $temporary: $!";
    print {$out} JSON::PP->new->canonical->encode({ files => $files });
    close $out or die "close $temporary: $!";
    rename $temporary, $REPORT or die "rename $temporary: $!";
}

sub main {
    # No database means that no instrumented Perl child finished.  Leave no
    # report so the adapter records missing native evidence as unknown.
    return unless -d $DB_DIR;

    # Debian's Devel::Cover 1.38 stores source records relative to this
    # directory and consults it again while reading the matching structure.
    chdir $WORKDIR or die "chdir $WORKDIR: $!";
    my $db = Devel::Cover::DB->new(db => $DB_DIR);
    # A process normally merges its own shard at END, but merge leftover shards
    # before asking the documented DB API for coverage.
    $db->merge_runs;
    my $cover = $db->cover;
    my %files;
    for my $path ($cover->items) {
        my $source = work_file($path) or next;
        my $statements = $cover->file($path)->statement or next;
        my %executed;
        for my $line (sort { $a <=> $b } $statements->items) {
            next unless $line =~ /\A[1-9][0-9]*\z/;
            my $entries = $statements->location($line);
            next unless ref($entries) eq "ARRAY";
            for my $statement (@$entries) {
                next unless ref($statement) && $statement->can("covered");
                my $count = $statement->covered;
                if (defined($count) && $count =~ /\A[0-9]+\z/ && $count > 0) {
                    $executed{$line} = 1;
                }
            }
        }
        $files{$source} = { executed_lines => [sort { $a <=> $b } keys %executed] };
    }
    write_report(\%files);
}

# A damaged native database must not be converted into affirmative evidence.
eval { main(); 1 } or exit 0;
'''


class Perl(Pytest):
    """Python pytest driver plus Devel::Cover statement evidence for Perl targets."""

    name = "perl"
    language = "perl"

    def driver_files(self) -> dict[str, bytes]:
        return {**super().driver_files(), "collect_perl_coverage.pl": PERL_COVER_COLLECTOR.encode()}

    def environment(self, role: str) -> Mapping[str, str]:
        return {**super().environment(role),
                "PERL5OPT": f"-MDevel::Cover=-db,{PERL_DB},-coverage,statement,-silent,1"}

    def after_command(self) -> list[str]:
        # Do not instrument this trusted reader; it must inspect exactly the
        # database emitted by the target subprocess, not add a collector run.
        return ["env", "-u", "PERL5OPT", "perl", _PERL_COLLECTOR]

    def result_paths(self) -> list[str]:
        return [path for path in super().result_paths() if not path.endswith("coverage.json")] + [PERL_COVERAGE_JSON]

    def read(self, files: Mapping[str, bytes | None], hypothesis) -> ProbeResult:
        covered_target, covered_lines = read_coverage(files.get(PERL_COVERAGE_JSON), hypothesis)
        return replace(super().read(files, hypothesis), covered_target=covered_target, covered_lines=covered_lines)
