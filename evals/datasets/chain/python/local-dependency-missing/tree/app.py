import ledger_store
TABLE = @LEDGER_TABLE@  # filled in by vendor/ledger_store/generate.py

def account_total(account: str):
    """Total for one account, read through the internal ledger store."""
    return ledger_store.query("SELECT SUM(amount) FROM entries WHERE account = '" + account + "'")
