'use strict';
// Reduced from lib/codecov.js (codecov/codecov-node): the coverage-file discovery call
// that passes the project root into a child process, extracted to a minimal module so it
// runs offline. Application logic only; no test or attack code.

const execSync = require('child_process').execSync;

function listFiles(root, patterns) {
  return execSync('find ' + root + ' ' + patterns).toString();
}

module.exports = { listFiles };
