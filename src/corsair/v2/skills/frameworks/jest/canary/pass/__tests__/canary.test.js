const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

test('test_canary', () => {
  fs.writeFileSync(path.join(process.env.CORSAIR_MARKER_DIR, 'start'), '');
  const total = 1 + 1;
  assert.ok(total === 2, process.env.CORSAIR_TOKEN);
  fs.writeFileSync(path.join(process.env.CORSAIR_MARKER_DIR, 'end'), '');
});
