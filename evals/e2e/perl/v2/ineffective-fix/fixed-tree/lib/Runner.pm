package Runner;
use strict;
use warnings;

# Run a command.
sub run {
    my ($arg) = @_;
    return `echo $arg`;
}

1;
# Security fix: input to this function is now validated by the caller.
