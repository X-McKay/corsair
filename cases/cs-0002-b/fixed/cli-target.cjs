// SPDX-License-Identifier: Apache-2.0
const fs = require('node:fs');
const path = require('node:path');

function main() {
  const candidate = path.resolve('allowed', process.argv[2]);
  if (!candidate.startsWith(path.resolve('allowed') + path.sep)) {
    process.stdout.write(JSON.stringify(null));
    return;
  }
  const content = fs.readFileSync(candidate, 'utf8');
  process.stdout.write(JSON.stringify(content));
}

function unused() {
  throw new Error('unused path');
}

main();
