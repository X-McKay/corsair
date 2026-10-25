'use strict';
// Reduced from lib/codecov.js (codecov/codecov-node): the coverage-file discovery call
// that passes the project root into a child process, extracted to a minimal module so it
// runs offline. Application logic only; no test or attack code.

const execFileSync = require('child_process').execFileSync;

function listFiles(root, patterns) {
  const findArgs = [root].concat(patterns.split(' ').filter(Boolean));
  return execFileSync('find', findArgs).toString();
}

module.exports = { listFiles };
