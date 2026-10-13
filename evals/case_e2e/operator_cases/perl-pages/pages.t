use strict;
use warnings;
use Test::More;
use File::Temp qw(tempdir);
use Site::Pages qw(page);

sub write_file { open(my $fh, '>', $_[0]) or die "write $_[0]: $!"; print {$fh} $_[1]; close $fh }

subtest control_page => sub {
    my $root = tempdir(CLEANUP => 1);
    write_file("$root/secret.html", 'page body');
    is(page($root, 'secret'), 'page body', 'a page under the root is served');
};

subtest security_page => sub {
    my $base = tempdir(CLEANUP => 1);
    mkdir "$base/pages" or die;
    write_file("$base/secret.html", 'outside');
    ok(!defined page("$base/pages", '../secret'), 'a name leaving the root is refused');
};

done_testing;
