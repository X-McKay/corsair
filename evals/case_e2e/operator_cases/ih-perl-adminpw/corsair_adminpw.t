use strict;
use warnings;
use Test::More;
use Auth;

subtest test_control => sub {
    is(Auth::authenticate({alice => 'pw'}, 'alice', 'pw'), 1, 'a configured account is accepted');
};

subtest test_security => sub {
    is(Auth::authenticate({alice => 'pw'}, 'admin', 'S3cr3t-Admin-2024'), 0, 'an unconfigured admin is refused');
};

done_testing;
