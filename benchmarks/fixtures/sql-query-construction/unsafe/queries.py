"""Reviewed fixture: concatenate untrusted input into SQL query structure."""


def lookup_account(database, account):
    return database.execute("SELECT balance FROM accounts WHERE account = '" + account + "'", ())
