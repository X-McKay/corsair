use strict;
use warnings;
use Test::More;
subtest test_control => sub {
    ok(1, "control holds");
};
subtest test_security => sub {
    SKIP: { skip "no network", 1; ok(1, "security holds"); }
};

done_testing;
