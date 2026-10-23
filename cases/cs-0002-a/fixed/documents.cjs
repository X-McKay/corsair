const fs = require('node:fs');
const path = require('node:path');
function read_document(root, name) {
  const candidate = path.resolve(root, name);
  if (!candidate.startsWith(path.resolve(root) + path.sep)) throw new Error('outside root');
  return fs.readFileSync(path.resolve(root, name), 'utf8');
}
module.exports = { read_document };
