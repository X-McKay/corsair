---
name: jest
description: Write one Corsair probe as a single Jest test in its own file, with the start and end markers and the run token.
---
# Jest probe

**File and name.** Write the planned file (normally under `__tests__/`, named `<name>.test.js`) holding exactly one
top-level `test('<name>', ...)` whose title is exactly the planned test name, not inside a `describe`. It is run
alone with `jest --runTestsByPath <file> -t '^<name>$'`, offline, with the project's own installed Jest; `require`
production code by its relative path. `test.each` on the one test is allowed. An `async` test must `await` the
target.

**Markers.** The environment variable `CORSAIR_MARKER_DIR` names a directory. The first statement of the test body
writes a file named `start` there; the last statement, after every assertion, writes `end`:

```js
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

test('name', () => {
  fs.writeFileSync(path.join(process.env.CORSAIR_MARKER_DIR, 'start'), '');
  const result = target(input);
  assert.ok(propertyHolds(result), process.env.CORSAIR_TOKEN);   // security probe only
  fs.writeFileSync(path.join(process.env.CORSAIR_MARKER_DIR, 'end'), '');
});
```

**Token.** Jest's `expect` takes no custom message, so the security (exploit) probe's security assertion uses
`assert.ok(condition, process.env.CORSAIR_TOKEN)` from `node:assert` (or `assert.strictEqual(a, b,
process.env.CORSAIR_TOKEN)`). Never log the token elsewhere. The control probe may use `expect` with no token.

**Pitfalls.** Do not wrap the assertion in `try`/`catch`; do not use `test.skip`, `test.todo`, `test.failing` or
`.only`; do not leave a promise un-awaited (the test would end before its assertion); keep exactly one test.
