---
name: perl-tap
description: Write Perl differential probes with core TAP and Devel::Cover evidence. Use when the runtime is perl / perl-tap.
---

# Perl / TAP

Submit one module named `CorsairProbe.pm`:

```perl
package CorsairProbe;
use strict;
use warnings;
use lib '/work';
use Target;

our $CONTROL_PAYLOAD = 'benign';
our $EXPLOIT_PAYLOAD = 'malicious';

sub run_target {
    my ($payload) = @_;
    my $result = Target::operation($payload);
    return $result->{is_safe};
}

1;
```

- Return one scalar boolean invariant for both payloads: `1` means it held; `0` or the empty string means the
  reported condition occurred. The kernel-owned driver emits TAP and performs the assertion.
- Every exception from the probe or application is an error. Catch only an expected fixed-revision rejection, then
  let the boolean invariant decide.
- Call the real module through its public subroutine. Do not use `Test::MockModule`, `Test::MockObject`,
  `Sub::Override`, symbol-table replacement, or a copied implementation.
- The repository root is on `PERL5LIB`. Use the project's checked-in `Makefile.PL`, `Build.PL`, or `cpanfile` only
  when dependencies are required. The runtime already supplies Perl 5.40, core TAP modules, JSON::PP, and
  Devel::Cover.
- Use `File::Temp` and core filesystem modules for fixtures. The source tree is read-only and probes have no network.
