package Documents;
use strict;
use warnings;
use Cwd qw(abs_path);
use File::Spec;

sub read_document {
    my ($root, $name) = @_;
    my $allowed = abs_path($root);
    my $candidate = abs_path(File::Spec->catfile($root, $name));
    die "outside root" unless defined($candidate) && index($candidate, $allowed . '/') == 0;
    open my $handle, '<', $candidate or die "cannot read document: $!";
    local $/;
    return <$handle>;
}

1;
