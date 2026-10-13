use strict;
use warnings;
use Digest::SHA qw(sha256);
use File::Temp qw(tempdir);
use JSON::PP;
use Test::More tests => 2;
use Corsair::Native;

subtest native_roundtrip => sub {
    my $value = {message => 'native Perl fixture', numbers => [1, 2, 3]};
    my $payload = JSON::PP->new->canonical->encode($value);
    my $read = Corsair::Native::roundtrip(tempdir(CLEANUP => 1) . '/roundtrip.json', $payload);
    is_deeply(decode_json($read), $value);
    is(sha256($read), sha256($payload));
};

subtest native_runtime => sub {
    is(sprintf('%vd', $^V) =~ s/\.\d+$//r, '5.26');
};
