---
name: test-more
description: Write one Corsair probe as a single Perl Test::More .t file run by prove, with the start, check and end markers and the run token.
---
# Test::More probe (prove)

**File and name.** One probe is one file: write the planned `.t` file under `t/` (e.g. `t/<name>.t`). It is run
alone with `prove -v -Ilib -Iblib/lib -Iblib/arch <file>` from the repository root, so `use` production modules
from `lib/`. The planned test name does not select anything (the file is the test); use it as a description if you like. A
single `subtest` is allowed but not needed.
End the file with `done_testing();`.

**Markers.** The environment variable `CORSAIR_MARKER_DIR` names a directory. Write a file named `start` there
before anything else the test does. Immediately before the main `ok`, write `check` containing `holds` if the
asserted condition holds and `violated` if not, computed from the same variable the `ok` checks. Write `end` as the
last step, only when every assertion passed (Test::More keeps going after a failed `ok`, so the guard matters):

```perl
use strict;
use warnings;
use Test::More;

sub corsair_marker {
    open(my $fh, '>', "$ENV{CORSAIR_MARKER_DIR}/$_[0]") or die "marker: $!";
    print $fh $_[1] if defined $_[1];
    close($fh);
}

corsair_marker('start');
my $result = Target::call($input);
my $holds = property_holds($result) ? 1 : 0;
corsair_marker('check', $holds ? 'holds' : 'violated');
ok($holds, 'property holds') or diag($ENV{CORSAIR_TOKEN});
corsair_marker('end') if Test::More->builder->is_passing;
done_testing();
```

**Token.** TAP prints a test's name even when it passes, so never use the token as the `ok` name. In both probes,
emit it only on failure with `or diag($ENV{CORSAIR_TOKEN})` on the main assertion. Never print it elsewhere.

**Pitfalls.** Do not wrap the assertion in `eval` to swallow a failure; do not use `TODO`, `skip`, `plan skip_all`
or `BAIL_OUT`; do not write `end` unguarded; keep the probe to one file with one assertion group.
