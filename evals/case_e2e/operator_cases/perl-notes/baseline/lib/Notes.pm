package Notes;
use strict;
use warnings;

# Save a note under the caller's notes directory.
sub save {
    my ($dir, $name, $text) = @_;
    open(my $fh, '>', "$dir/$name") or die "cannot save $name: $!\n";
    print {$fh} $text;
    close $fh;
    return 1;
}

1;
