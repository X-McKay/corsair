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

- Return the same Boolean invariant through the same setup and target call for both payloads: `1` means true
  (preserved); `0` or the empty string means false (the reported condition occurred). The driver assigns control
  `PASS` for true and exploit `PASS` for false; exploit `FAIL` is a clean true observation and scoped negative
  evidence. Undefined values, references and arbitrary truthy values are invalid. The probe receives no role or
  expected answer; the kernel-owned driver emits TAP.
- Every uncaught exception from the probe or application is `ERROR`; do not assert in the probe. Catch only an
  expected rejection, then let the Boolean invariant decide using the same path for both payloads and revisions.
- Repository-local Perl script or CLI execution requires native coverage of the child target lines; observing
  exit status and stdout alone cannot satisfy the coverage gate.
- Call the real module through its public subroutine. Do not use `Test::MockModule`, `Test::MockObject`,
  `Sub::Override`, symbol-table replacement, or a copied implementation.
- The repository root is on `PERL5LIB`. Use the project's checked-in `Makefile.PL`, `Build.PL`, or `cpanfile` only
  when dependencies are required. The runtime already supplies Perl 5.40, core TAP modules, JSON::PP, and
  Devel::Cover.
- Use `File::Temp` and core filesystem modules for fixtures. The source tree is read-only and probes have no network.
