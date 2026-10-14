'use strict';

test('nativeRoundtrip', () => {
  expect(JSON.parse(JSON.stringify({ corsair: 'native' }))).toEqual({ corsair: 'native' });
});

test('nativeRuntime', () => {
  expect(process.versions.node.split('.')[0]).toBe('22');
});
