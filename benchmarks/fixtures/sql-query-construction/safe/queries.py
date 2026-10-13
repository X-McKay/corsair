"""Reviewed fixture: construct a parameterized query at the database dependency seam."""


def lookup_account(database, account):
    return database.execute("SELECT balance FROM accounts WHERE account = ?", (account,))
