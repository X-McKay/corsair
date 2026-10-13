package Corsair::Native;
use strict;
use warnings;

our $VERSION = '0.01';

sub roundtrip {
    my ($path, $value) = @_;
    open my $out, '>:raw', $path or die "write $path: $!";
    print {$out} $value;
    close $out or die "close $path: $!";
    open my $in, '<:raw', $path or die "read $path: $!";
    local $/;
    my $read = <$in>;
    close $in;
    return $read;
}

1;
