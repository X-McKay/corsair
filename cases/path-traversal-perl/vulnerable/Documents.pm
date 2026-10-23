package Documents;
use strict;
use warnings;
use File::Spec;

sub read_document {
    my ($root, $name) = @_;
    my $candidate = File::Spec->catfile($root, $name);
    open my $handle, '<', $candidate or die "cannot read document: $!";
    local $/;
    return <$handle>;
}

1;
