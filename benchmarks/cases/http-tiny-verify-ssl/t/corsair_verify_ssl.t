#!perl
# CVE-2023-31486 case test for Corsair's TAP runner: two top-level subtests in one file. Both assertions are
# copied unchanged from upstream HTTP-Tiny t/180_verify_SSL.t at the fix commit 77f557e.
use strict;
use warnings;
use Test::More 0.88;

use HTTP::Tiny;

delete $ENV{PERL_HTTP_TINY_INSECURE_BY_DEFAULT};

# Control: an explicit verify_SSL => 0 is honoured before and after the fix.
subtest test_control => sub {
    my $ht = HTTP::Tiny->new(
        verify_SSL => 0
    );
    is($ht->verify_SSL, 0, "verify_SSL=>0 sets 0");
};

# Security: TLS certificates are verified unless the caller opts out.
subtest test_security => sub {
    my $ht = HTTP::Tiny->new();
    is($ht->verify_SSL, 1, "verify_SSL is 1 by default");
};

done_testing;
