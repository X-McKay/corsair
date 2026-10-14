"""Exactly one benign control and one safety regression, requiring no database."""
"""Reviewed fixture: construct a parameterized query at the database dependency seam."""


def lookup_account(database, account):
    return database.execute("SELECT balance FROM accounts WHERE account = ?", (account,))


class RecordingDatabase:
    def __init__(self):
        self.calls = []

    def execute(self, query, parameters):
        self.calls.append((query, parameters))
        return [(25,)]


def test_benign_control():
    database = RecordingDatabase()
    assert lookup_account(database, "alice") == [(25,)]
    assert database.calls in [
        [("SELECT balance FROM accounts WHERE account = ?", ("alice",))],
        [("SELECT balance FROM accounts WHERE account = 'alice'", ())],
    ]


def test_security_preserves_query_structure():
    database = RecordingDatabase()
    hostile = "alice' OR 1=1 --"
    assert lookup_account(database, hostile) == [(25,)]
    assert database.calls == [("SELECT balance FROM accounts WHERE account = ?", (hostile,))]
