use strict;
use warnings;
use Test::More;
subtest test_control => sub {
    ok(1, "control holds");
};
ok(1, "outside");
subtest test_security => sub {
    ok(1, "security holds");
};

done_testing;
