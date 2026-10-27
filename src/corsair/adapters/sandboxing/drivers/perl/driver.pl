#!/usr/bin/env perl
# Trusted in-image driver for the Perl html-injection recipe (CWE-79).
#
# This program is intentionally not an agent tool. It receives an operator-created,
# JSON-only job, writes a fixed Test::More test and a core-only line tracer, runs the
# test under the tracer, and emits one strict JSON record on stdout mirroring driver.py
# (schema corsair.driver/1). Target stdout/stderr are redirected to work files and never
# become driver output. The driver does not print the rendered target value, the payload,
# or any die message.
#
# Threat limit: the target remains arbitrary Perl within a constrained container. The
# record is evidence of the fixed driver assertion under that isolation boundary, not a
# proof against a hostile interpreter/kernel/daemon or an arbitrary build dependency.

use strict;
use warnings;
use JSON::PP ();
use Time::HiRes ();

my $JOB_PATH    = '/input/job.json';
my $WORK        = '/work';
my $TEST_PATH   = "$WORK/test_recipe.t";
my $TRACER_DIR  = "$WORK/Devel";
my $TRACER_PATH = "$TRACER_DIR/LineCover.pm";
my $OBSERVATION = "$WORK/observation.json";
my $COVERAGE    = "$WORK/coverage.json";
my $TAP         = "$WORK/tap.txt";
my $ERR         = "$WORK/err.txt";
# The container's own cgroup v2 CPU accounting (Docker's private cgroup namespace).
my $CPU_STAT    = '/sys/fs/cgroup/cpu.stat';

# The fixed test. It reads the same job JSON, loads the pinned module, invokes the sub
# with the operator-fixed leading arguments plus the single model payload, and makes the
# operator-owned html-injection assertion. It writes observation.json and prints TAP; it
# never prints the rendered value or payload.
my $TEST_SOURCE = <<'PERL';
use strict;
use warnings;
use Test::More;
use JSON::PP ();

my $job = JSON::PP::decode_json(do { local (@ARGV, $/) = ('/input/job.json'); <> });
my $recipe = $job->{recipe};

sub _observe {
    my ($kind) = @_;
    if (open(my $fh, '>', '/work/observation.json')) {
        print $fh JSON::PP::encode_json({ kind => $kind });
        close $fh;
    }
}

sub _module_path {
    my $raw = $recipe->{module_file};
    die "invalid module path\n"
      if !defined $raw || $raw =~ m{\A/} || $raw =~ m{(?:\A|/)\.\.?(?:/|\z)};
    return "/source/$raw";
}

sub _markup_chars {
    my ($text) = @_;
    my $count = () = ($text =~ /[<>]/g);
    return $count;
}

sub _invoke {
    my $path = _module_path();
    require $path;
    my $fq = $recipe->{package} . '::' . $recipe->{function};
    no strict 'refs';
    die "recipe function is absent or not callable\n" unless defined &{$fq};
    my @args = (@{ $recipe->{fixed_args} }, $job->{payload});
    return &{$fq}(@args);
}

sub _allowed {
    my ($message) = @_;
    for my $substr (@{ $recipe->{allowed_exceptions} }) {
        return 1 if index($message, $substr) >= 0;
    }
    return 0;
}

my $baseline = $recipe->{baseline_markup_chars};

if ($job->{role} eq 'control') {
    my $result = eval { _invoke() };
    if ($@) {
        _observe('execution_error');
        ok(0, 'control invocation raised an unexpected exception');
        done_testing();
    }
    else {
        my $same  = defined $result && $result eq $recipe->{expected_control};
        my $clean = defined $result && _markup_chars($result) == $baseline;
        my $valid = $same && $clean;
        _observe($valid ? 'held' : 'invalid_control');
        ok($valid, 'control preserved expected public behavior');
        done_testing();
    }
}
else {
    my $result = eval { _invoke() };
    if ($@) {
        if (_allowed("$@")) {
            _observe('held');
            ok(1, 'adversarial input was rejected by an allowed exception');
        }
        else {
            _observe('execution_error');
            ok(0, 'adversarial invocation raised an unexpected exception');
        }
        done_testing();
    }
    else {
        # An undefined result rendered no HTML at all, so it carries no injected markup:
        # like an allowed rejection it holds, and it can never establish an injection.
        my $excess = defined $result && _markup_chars($result) > $baseline;
        _observe($excess ? 'disclosure' : 'held');
        ok(!$excess, 'adversarial result injected no excess markup');
        done_testing();
    }
}
PERL

# The line tracer: a core-only Devel:: module loaded with `perl -d:LineCover`. perl calls
# DB::DB before every statement; we record executed lines of /source files only and write
# them at process end. No CPAN dependency and no interactive debugger.
my $TRACER_SOURCE = <<'PERL';
package Devel::LineCover;
use strict;
use warnings;
our %SEEN;

package DB;

sub DB {
    my (undef, $file, $line) = caller(0);
    return unless defined $file && defined $line;
    return unless substr($file, 0, 8) eq '/source/';
    $Devel::LineCover::SEEN{$file}{$line} = 1;
}

sub sub {    ## no critic
    no strict 'refs';
    my $name = $DB::sub;
    if (wantarray)            { my @r = &$name; return @r; }
    elsif (defined wantarray) { my $r = &$name; return $r; }
    else                      { &$name; return; }
}

package Devel::LineCover;

END {
    require JSON::PP;
    my %files;
    for my $file (keys %SEEN) {
        $files{$file} = { executed_lines => [ sort { $a <=> $b } keys %{ $SEEN{$file} } ] };
    }
    if (open(my $fh, '>', '/work/coverage.json')) {
        print $fh JSON::PP::encode_json({ files => \%files });
        close $fh;
    }
}

1;
PERL

sub write_file {
    my ($path, $content) = @_;
    open(my $fh, '>', $path) or die "cannot write $path: $!\n";
    print $fh $content;
    close $fh;
}

sub emit {
    my ($record) = @_;
    print JSON::PP->new->canonical->encode($record), "\n";
}

sub safe_job {
    my ($value) = @_;
    return undef unless ref $value eq 'HASH';
    my %required = map { $_ => 1 } qw(
      schema_version operation_id role source_digest submission_digest recipe payload
    );
    return undef unless keys %$value == keys %required;
    for my $key (keys %$value) { return undef unless $required{$key}; }
    return undef unless ($value->{schema_version} // '') eq 'corsair.driver-job/1';
    return undef unless ($value->{role} // '') =~ /\A(?:control|adversarial)\z/;
    return undef unless ref $value->{recipe} eq 'HASH';
    return undef unless ref $value->{recipe}{fixed_args} eq 'ARRAY';
    return undef unless ref $value->{recipe}{allowed_exceptions} eq 'ARRAY';
    return $value;
}

sub coverage_lines {
    my ($module_file) = @_;
    return [] unless -e $COVERAGE;
    my $text = eval { local (@ARGV, $/) = ($COVERAGE); <> };
    return [] unless defined $text;
    my $document = eval { JSON::PP::decode_json($text) };
    return [] unless ref $document eq 'HASH' && ref $document->{files} eq 'HASH';
    my $entry = $document->{files}{"/source/$module_file"};
    return [] unless ref $entry eq 'HASH' && ref $entry->{executed_lines} eq 'ARRAY';
    my %seen;
    for my $line (@{ $entry->{executed_lines} }) {
        return [] unless defined $line && "$line" =~ /\A[1-9][0-9]*\z/;
        $seen{ 0 + $line } = 1;
    }
    # Force numeric JSON encoding (0 + ...) so the strict verifier sees integers.
    return [ map { 0 + $_ } sort { $a <=> $b } keys %seen ];
}

# The cgroup v2 usage_usec CPU total, or undef when the file or field is absent.
sub cgroup_cpu_usec {
    open(my $handle, '<', $CPU_STAT) or return undef;
    while (my $line = <$handle>) {
        if ($line =~ /\Ausage_usec ([0-9]+)\s*\z/) {
            close $handle;
            return 0 + $1;
        }
    }
    close $handle;
    return undef;
}

sub read_observation {
    return undef unless -e $OBSERVATION;
    my $text = eval { local (@ARGV, $/) = ($OBSERVATION); <> };
    return undef unless defined $text;
    my $doc = eval { JSON::PP::decode_json($text) };
    return undef unless ref $doc eq 'HASH';
    return $doc->{kind};
}

# --- main -----------------------------------------------------------------------------

my $raw = eval { local (@ARGV, $/) = ($JOB_PATH); <> };
my $decoded = defined $raw ? eval { JSON::PP::decode_json($raw) } : undef;
my $job = safe_job($decoded);
if (!defined $job) {
    # No secret-bearing input here, but never reflect untrusted job values.
    emit({ schema_version => 'corsair.driver/1', driver_error => 'invalid job' });
    exit 2;
}

mkdir $WORK unless -d $WORK;
mkdir $TRACER_DIR unless -d $TRACER_DIR;
write_file($TEST_PATH,   $TEST_SOURCE);
write_file($TRACER_PATH, $TRACER_SOURCE);

my $exit_code;
my $started = Time::HiRes::clock_gettime(Time::HiRes::CLOCK_MONOTONIC());
{
    open(my $old_out, '>&', \*STDOUT) or die "cannot save stdout: $!\n";
    open(my $old_err, '>&', \*STDERR) or die "cannot save stderr: $!\n";
    open(STDOUT, '>', $TAP)  or die "cannot redirect stdout: $!\n";
    open(STDERR, '>', $ERR)  or die "cannot redirect stderr: $!\n";
    # DockerSandbox owns the wall-clock probe deadline and stops the whole container on
    # expiry. Do not add a second target-execution timeout here.
    my $status = system($^X, '-d:LineCover', '-I', $WORK, $TEST_PATH);
    open(STDOUT, '>&', $old_out) or die "cannot restore stdout: $!\n";
    open(STDERR, '>&', $old_err) or die "cannot restore stderr: $!\n";
    if ($status == -1) { $exit_code = 2; }
    elsif ($status & 127) { $exit_code = 128 + ($status & 127); }
    else { $exit_code = $status >> 8; }
}
# Integer microseconds (0 + int) so the strict verifier sees a JSON integer.
my $wall_usec = 0 + int(
    (Time::HiRes::clock_gettime(Time::HiRes::CLOCK_MONOTONIC()) - $started) * 1_000_000);

my $observed = read_observation();
my $module_file = $job->{recipe}{module_file} // '';
my $role = $job->{role};

my ($status_name, %junit, $outcome);
if (defined $observed && $observed eq 'held' && $exit_code == 0) {
    ($status_name, $outcome) = ('PASS', 'PROPERTY_HELD');
    %junit = (tests => 1, failures => 0, errors => 0, skipped => 0);
}
elsif (defined $observed && $observed eq 'disclosure' && $role eq 'adversarial' && $exit_code != 0) {
    ($status_name, $outcome) = ('FAILURE', 'VIOLATION');
    %junit = (tests => 1, failures => 1, errors => 0, skipped => 0);
}
elsif (defined $observed && $observed eq 'invalid_control' && $exit_code != 0) {
    ($status_name, $outcome) = ('INVALID', 'INVALID');
    %junit = (tests => 1, failures => 1, errors => 0, skipped => 0);
}
elsif (defined $observed && $observed eq 'execution_error' && $exit_code != 0) {
    ($status_name, $outcome) = ('ERROR', 'ERROR');
    %junit = (tests => 1, failures => 0, errors => 1, skipped => 0);
}
else {
    ($status_name, $outcome) = ('ERROR', 'ERROR');
    %junit = (tests => 1, failures => 0, errors => 1, skipped => 0);
}

my %kinds = map { $_ => 1 } qw(held disclosure invalid_control);
my $target_executed = (defined $observed && $kinds{$observed}) ? JSON::PP::true : JSON::PP::false;

my %record = (
    schema_version    => 'corsair.driver/1',
    operation_id      => $job->{operation_id},
    role              => $role,
    source_digest     => $job->{source_digest},
    submission_digest => $job->{submission_digest},
    native_exit_code  => $exit_code,
    junit             => { status => $status_name, %junit },
    outcome           => $outcome,
    observation_kind  => $observed,
    target_executed   => $target_executed,
    covered_lines     => coverage_lines($module_file),
    coverage_file     => $module_file,
);
# Efficiency telemetry only: the verifier never admits an outcome from it.
$record{wall_usec} = $wall_usec;
my $cpu_usec = cgroup_cpu_usec();
$record{cpu_usec} = $cpu_usec if defined $cpu_usec;
emit(\%record);

# Deliberately the child test's native status, so docker_exit_code matches native_exit_code.
exit $exit_code;
