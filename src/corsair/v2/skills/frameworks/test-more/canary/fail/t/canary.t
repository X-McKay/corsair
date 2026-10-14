use strict;
use warnings;
use Test::More;

sub corsair_marker {
    open(my $fh, '>', "$ENV{CORSAIR_MARKER_DIR}/$_[0]") or die "marker $_[0]: $!";
    close($fh);
}

corsair_marker('start');
my $total = 1 + 1;
ok($total == 3, 'canary holds') or diag($ENV{CORSAIR_TOKEN});
corsair_marker('end') if Test::More->builder->is_passing;
done_testing();
