'use strict';

test('native roundtrip', () => {
  expect(JSON.parse(JSON.stringify({ corsair: 'native' }))).toEqual({ corsair: 'native' });
});

test('native runtime', () => {
  expect(process.versions.node.split('.')[0]).toBe('8');
});
