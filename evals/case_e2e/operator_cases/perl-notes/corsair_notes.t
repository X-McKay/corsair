use strict;
use warnings;
use Test::More;
use File::Temp qw(tempdir);
use Notes;

subtest test_control => sub {
    my $dir = tempdir(CLEANUP => 1);
    ok(Notes::save($dir, 'sentinel.txt', 'kept'), 'a plain name is saved inside the directory');
};

subtest test_security => sub {
    my $dir = tempdir(CLEANUP => 1);
    mkdir "$dir/notes" or die "mkdir: $!";
    my $saved = eval { Notes::save("$dir/notes", '../sentinel.txt', 'escaped') };
    ok(!$saved, 'a ../ name is refused');
};

done_testing;
