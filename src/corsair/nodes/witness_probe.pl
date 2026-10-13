# Operator witness probe for one Perl TAP run (SPEC-0074); loaded by the runner's bootstrap, never by workload code.
#
# The Perl counterpart of witness_probe.py, writing the same `corsair-witness-v2` record so the host maps it to the
# gate's witness unchanged. Core modules only (B, Cwd, Fcntl, File::Basename, JSON::PP, Scalar::Util, Symbol).
# Each top-level Test::More subtest is one test's call phase (Test::More::subtest is wrapped before the file loads). At its start the identified target sub (its name, and
# its package when the symbol is qualified, defined in the target file) is wrapped wherever the symbol table holds
# it, imported aliases included, so its calls, returns and dies are counted. `open` is replaced through
# CORE::GLOBAL::open before the test file compiles: a file open while a target call is on the stack is recorded,
# and a failed one is recorded as an error with its errno. Opens of the planned file outside a target call after the
# target was first entered are counted apart: `body_planned` when the test file itself opens it (checking its own
# fixture), `offstack_planned` otherwise. Pipe, dup and in-memory opens are not file opens. Not observed: child
# processes, `sysopen`, XS code, and calls through a code reference taken before the subtest started. It runs inside
# the test interpreter, so it is tamper-evident (overrides and wrappers are checked at the end), not tamper-proof.
package Corsair::WitnessProbe;
use strict;
use warnings;
use B ();
use Cwd ();
use Fcntl ();
use File::Basename ();
use JSON::PP ();
use Scalar::Util ();
use Symbol ();

my $SCHEMA = 'corsair-witness-v2';
my ($MAX_OPENS, $MAX_CALLS, $MAX_TESTS) = (32, 32, 16);
my (%config, $record, $test_file, $target_file, $sub_name, $package, $original_subtest);
my (%wrapped, %wrapper_of);  # target CV address => wrapper; glob name => wrapper installed there
our $inside = 0;  # target calls on the stack
our ($active, $depth);  # the running top-level subtest's id; nesting depth

sub start {
    my ($sha256, $settings, $file) = @_;
    %config = %$settings;
    $test_file = Cwd::realpath($file) || $file;
    $target_file = Cwd::realpath("$config{root}/$config{target_path}") || '';
    my @parts = split /\./, $config{target_symbol};
    $sub_name = pop @parts;
    $package = @parts ? join('::', @parts) : undef;
    $record = {schema => $SCHEMA, nonce => $config{nonce}, plugin_sha256 => $sha256,
               target => {path => $config{target_path}, symbol => $config{target_symbol},
                          effect_name => $config{effect_name}},
               tool_registered => JSON::PP::false, intact => JSON::PP::false, unsupported => undef, tests => {}};
    $Carp::Internal{+__PACKAGE__}++;  # carp and croak from the target report its caller, not the wrapper
    require Test::More;
    $original_subtest = \&Test::More::subtest;
    no warnings 'redefine';
    *Test::More::subtest = \&_subtest;
    *CORE::GLOBAL::open = \&_open;
    $record->{tool_registered} = JSON::PP::true;
}

sub _test { defined $active ? $record->{tests}{$active} : undef }

sub _name {
    my ($error) = @_;
    return Scalar::Util::blessed($error) ? ref($error) : 'die';
}

sub _planned {
    my ($path) = @_;
    return 0 unless defined $path && length $path;
    my $resolved = eval { Cwd::realpath($path) };
    return grep({ defined $_ && File::Basename::basename($_) eq $config{effect_name} } $path, $resolved) ? 1 : 0;
}

# The file a 2- or 3-argument open names, or undef for a pipe, a dup, an in-memory or a 1-argument open.
sub _path {
    my (undef, $mode, @rest) = @_;
    return undef unless defined $mode;
    if (!@rest) {
        (my $spec = $mode) =~ s/^\s+|\s+$//g;
        return undef if $spec =~ /^\||\|$|^\+?(?:<|>>?)&/ || $spec eq '-' || $spec eq '>-';
        $spec =~ s/^\+?(?:<|>>|>)\s*//;
        return length $spec ? $spec : undef;
    }
    (my $kind = $mode) =~ s/:.*//s;
    $kind =~ s/\s+//g;
    return undef unless $kind =~ /^\+?(?:<|>>|>)$/ && defined $rest[0] && !ref $rest[0];
    return "$rest[0]";
}

sub _open (*;$@) {
    my $path = _path(@_);
    my $handle = (defined $_[0] && !ref $_[0] && ref \$_[0] ne 'GLOB')
        ? Symbol::qualify_to_ref($_[0], scalar caller) : undef;
    my $ok = @_ == 1 ? CORE::open($handle || $_[0])
           : @_ == 2 ? ($handle ? CORE::open($handle, $_[1]) : CORE::open($_[0], $_[1]))
           : ($handle ? CORE::open($handle, $_[1], @_[2 .. $#_]) : CORE::open($_[0], $_[1], @_[2 .. $#_]));
    my $errno = $! + 0;
    my $test = _test();
    if ($test && defined $path) {
        if ($inside) {
            if (@{$test->{opens}} < $MAX_OPENS) {
                push @{$test->{opens}}, {path => substr($path, 0, 512), planned => _planned($path) ? JSON::PP::true : JSON::PP::false};
            } else {
                $test->{truncated} = JSON::PP::true;
            }
            if (!$ok) {
                if (@{$test->{os_errors}} < $MAX_OPENS) { push @{$test->{os_errors}}, {type => 'open', errno => $errno} }
                else { $test->{truncated} = JSON::PP::true }
            }
        } elsif ($test->{entered} && _planned($path)) {
            my $site = (caller)[1];
            my $own = defined $site && (Cwd::realpath($site) || $site) eq $test_file;
            $test->{$own ? 'body_planned' : 'offstack_planned'} += 1;
        }
    }
    $! = $errno;
    return $ok;
}

# Every glob holding a CODE slot, by full name, walking packages from main::.
sub _globs {
    my ($stash, $seen, $found) = @_;
    no strict 'refs';
    for my $key (keys %{"${stash}::"}) {
        my $name = "${stash}::$key";
        if ($key =~ /::$/) {
            (my $inner = $name) =~ s/::$//;
            next if $key eq 'main::' || $seen->{$inner}++;
            _globs($inner, $seen, $found);
            next;
        }
        my $glob = \*{$name};
        $found->{$name} = *{$glob}{CODE} if ref $glob eq 'GLOB' && defined *{$glob}{CODE};
    }
    return $found;
}

sub _is_target {
    my ($code) = @_;
    my $cv = B::svref_2object($code);
    my $gv = eval { $cv->GV } or return 0;
    return 0 if ref $gv eq 'B::SPECIAL' || $gv->NAME ne $sub_name;
    return 0 if defined $package && $gv->STASH->NAME ne $package;
    my $file = eval { $cv->FILE };
    return defined $file && length $file && $target_file ne '' && (Cwd::realpath($file) || '') eq $target_file;
}

sub _wrap {
    my ($original) = @_;
    return sub {
        my $test = _test();
        $test->{entered} += 1 if $test;
        my ($want, @result) = (wantarray);
        my $ok = do {
            local $inside = $inside + 1;
            eval {
                if ($want) { @result = $original->(@_) }
                elsif (defined $want) { $result[0] = $original->(@_) }
                else { $original->(@_) }
                1;
            };
        };
        my $error = $@;
        if ($test) {
            if (@{$test->{exits}} < $MAX_CALLS) { push @{$test->{exits}}, $ok ? undef : _name($error) }
            else { $test->{truncated} = JSON::PP::true }
        }
        die $error unless $ok;
        return $want ? @result : $result[0];
    };
}

# Wrap the target wherever a glob holds it (its own name and any imported alias); idempotent per subtest.
sub _wrap_targets {
    my $globs = _globs('main', {}, {});
    my %targets;
    for my $code (values %$globs) {
        my $address = Scalar::Util::refaddr($code);
        $targets{$address} = $code if !$wrapped{$address} && !grep({ $_ == $address } map { Scalar::Util::refaddr($_) } values %wrapped)
            && _is_target($code);
    }
    $wrapped{$_} ||= _wrap($targets{$_}) for keys %targets;
    no strict 'refs';
    no warnings 'redefine';
    for my $name (keys %$globs) {
        my $wrapper = $wrapped{Scalar::Util::refaddr($globs->{$name})} or next;
        *{$name} = $wrapper;
        $wrapper_of{$name} = $wrapper;
    }
}

# Test::More's subtest with the block wrapped; `goto` leaves no probe frame, so Test::More reports the test's own line.
sub _subtest {
    my ($name, $code, @rest) = @_;
    goto &$original_subtest if $depth || !defined $name || ref $code ne 'CODE';
    my $id = "$config{file}#$name";
    my $tests = $record->{tests};
    if (!exists $tests->{$id} && keys(%$tests) < $MAX_TESTS) {
        $tests->{$id} = {entered => 0, exits => [], opens => [], os_errors => [], truncated => JSON::PP::false,
                         complete => JSON::PP::false, offstack_planned => 0, body_planned => 0};
    }
    my $call = sub {
        local $depth = 1;
        local $active = exists $tests->{$id} ? $id : undef;
        _wrap_targets();
        my $want = wantarray;
        my @result;
        my $ok = eval { @result = $want ? $code->(@_) : scalar $code->(@_); 1 };
        my $error = $@;
        $tests->{$active}{complete} = JSON::PP::true if defined $active;
        die $error unless $ok;
        return $want ? @result : $result[0];
    };
    @_ = ($name, $call, @rest);
    goto &$original_subtest;
}

sub finish {
    return unless $record;
    no strict 'refs';
    my $intact = (\&CORE::GLOBAL::open == \&_open) && (\&Test::More::subtest == \&_subtest)
        && !grep({ !defined *{$_}{CODE} || *{$_}{CODE} != $wrapper_of{$_} } keys %wrapper_of);
    $record->{intact} = $intact ? JSON::PP::true : JSON::PP::false;
    my $data = JSON::PP->new->canonical->encode($record);
    my $flags = Fcntl::O_WRONLY() | Fcntl::O_CREAT() | Fcntl::O_EXCL() | (eval { Fcntl::O_NOFOLLOW() } || 0);
    my $stream;
    if (!sysopen($stream, $config{record_path}, $flags, 0600)) {
        $? = 3;  # Something else created the record path: the run fails rather than offering that file.
        return;
    }
    binmode $stream;
    print {$stream} $data;
    close $stream or $? = 3;
}

1;
