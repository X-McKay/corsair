package Site::Pages;
use strict;
use warnings;
use Exporter 'import';
our @EXPORT_OK = qw(page);

# Return the body of a page stored under $root.
sub page {
    my ($root, $name) = @_;
    return undef unless $name =~ /\A[A-Za-z0-9_-]+\z/;
    local *PAGE;
    open(PAGE, "<$root/$name.html") or return undef;
    local $/;
    my $body = <PAGE>;
    close PAGE;
    return $body;
}

1;
