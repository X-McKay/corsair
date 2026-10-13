'use strict';
const path = require('path');

test('corsair_control', () => {
  expect(path.join('a', 'b')).toBe('a/b');
});

describe('traversal', () => {
  test('corsair_security', () => {
    const resolved = path.join('/srv/docs', '../etc/passwd');
    expect(resolved.startsWith('/srv/docs/')).toBe(true);
  });
});
