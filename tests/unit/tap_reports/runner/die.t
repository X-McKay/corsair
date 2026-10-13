use strict;
use warnings;
use Test::More;
subtest test_control => sub {
    ok(1, "control holds");
};
subtest test_security => sub {
    die "boom in security\n";
};

done_testing;
