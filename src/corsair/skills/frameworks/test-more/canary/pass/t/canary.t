use strict;
use warnings;
use Test::More;

sub corsair_marker {
    open(my $fh, '>', "$ENV{CORSAIR_MARKER_DIR}/$_[0]") or die "marker $_[0]: $!";
    print $fh $_[1] if defined $_[1];
    close($fh);
}

corsair_marker('start');
my $total = 1 + 1;
my $holds = $total == 2;
corsair_marker('check', $holds ? 'holds' : 'violated');
ok($holds, 'canary holds') or diag($ENV{CORSAIR_TOKEN});
corsair_marker('end') if Test::More->builder->is_passing;
done_testing();
