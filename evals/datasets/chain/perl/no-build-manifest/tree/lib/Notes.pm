package Notes;
use strict;
use warnings;

# Print a note file.
sub show {
    my ($name) = @_;
    return `cat notes/$name`;
}

1;
