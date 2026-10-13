'use strict';
test('corsair_control', () => {
  expect(1).toBe(1);
});
test('corsair_security', () => {
  const target = null;
  expect(target.open()).toBe(true);
});
