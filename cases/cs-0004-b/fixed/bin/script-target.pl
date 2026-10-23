# SPDX-License-Identifier: Apache-2.0
use strict;
use warnings;
sub main {
    my ($root, $name, $branch) = @_;
    my $path = "$root/$name";
    if ($branch eq 'first') {
        my $visited = 1;
    } else {
        my $visited = 2;
    }
    if ($name =~ m{[./\\]}) {
        print 'rejected';
        exit 0;
    }
    open my $handle, '<', $path or die "cannot read fixture: $!";
    local $/;
    my $content = <$handle>;
    close $handle;
    print $content;
}
sub unused {
    return 'never';
}
main(@ARGV);
