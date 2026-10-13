use strict;
use warnings;
use Test::More;
use Runner;

subtest test_control => sub {
    is(Runner::run('hello'), "hello\n", 'a plain argument is echoed');
};

subtest test_security => sub {
    my $out = Runner::run('x; echo injected');
    is($out, "x; echo injected\n", 'shell syntax in the argument stays literal');
};

done_testing;
