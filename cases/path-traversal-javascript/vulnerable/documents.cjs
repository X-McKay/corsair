const fs = require('node:fs');
const path = require('node:path');
function read_document(root, name) {
  return fs.readFileSync(path.resolve(root, name), 'utf8');
}
module.exports = { read_document };
