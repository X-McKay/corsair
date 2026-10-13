use strict;
use warnings;
use Test::More;
subtest test_control => sub {
    die "control died\n";
};
subtest test_security => sub {
    ok(1);
};

done_testing;
