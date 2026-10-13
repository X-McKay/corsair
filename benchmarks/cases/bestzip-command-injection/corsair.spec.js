'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const bestzip = require('../lib/bestzip');

const fixtures = path.join(__dirname, 'fixtures');

test('corsair_control', () => {
  const destination = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'corsair-control-')), 'out.zip');
  return bestzip.nodeZip({ source: 'file.txt', destination, cwd: fixtures }).then(() => {
    expect(fs.statSync(destination).size).toBeGreaterThan(0);
  });
});

test('corsair_security', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'corsair-security-'));
  const marker = path.join(directory, 'injected');
  const destination = `${path.join(directory, 'out.zip')}; touch ${marker}; true`;
  return bestzip.nativeZip({ source: 'file.txt', destination, cwd: fixtures })
    .catch(() => undefined)
    .then(() => {
      expect(fs.existsSync(marker)).toBe(false);
    });
});
