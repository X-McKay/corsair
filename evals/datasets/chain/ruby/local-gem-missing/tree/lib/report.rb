require 'ledger_store'
TABLE = @LEDGER_TABLE@ # filled in by vendor/ledger_store/generate.rb
module Report
  # Total for one account, read through the internal ledger store.
  def self.total(account)
    LedgerStore.query("SELECT SUM(amount) FROM entries WHERE account = '#{account}'")
  end
end
