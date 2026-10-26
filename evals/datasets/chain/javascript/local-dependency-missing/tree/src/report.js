const ledger = require("ledger-store");
const TABLE = @LEDGER_TABLE@; // filled in by vendor/ledger-store/generate.js
// Total for one account, read through the internal ledger store.
function accountTotal(account) {
  return ledger.query("SELECT SUM(amount) FROM entries WHERE account = '" + account + "'");
}

module.exports = { accountTotal };
