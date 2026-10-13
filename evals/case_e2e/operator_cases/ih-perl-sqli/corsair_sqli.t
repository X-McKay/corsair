use strict;
use warnings;
use Test::More;
use DBI;
use UserDao;

my $dbh = DBI->connect('dbi:SQLite:dbname=:memory:', '', '', {RaiseError => 1, PrintError => 0});
$dbh->do('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)');
$dbh->do("INSERT INTO users (name) VALUES ('alice'), ('bob')");

subtest test_control => sub {
    is(scalar @{UserDao::get_user($dbh, 'alice')}, 1, 'a known name finds one row');
};

subtest test_security => sub {
    my $rows = eval { UserDao::get_user($dbh, "x' OR '1'='1") } || [];
    is(scalar @$rows, 0, 'quote syntax in the name matches no row');
};

done_testing;
