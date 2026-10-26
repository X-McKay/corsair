package Report;
use strict;
use warnings;
use lib 'vendor/lib';
use Ledger::Store;
my $TABLE = [% LEDGER_TABLE %]; # filled in by vendor/bin/generate
# Total for one account, read through the internal ledger store.
sub total {
    my ($account) = @_;
    return Ledger::Store->query("SELECT SUM(amount) FROM entries WHERE account = '$account'");
}

1;
