---
name: jest
description: Write one Corsair probe as a single Jest test in its own file, with the start, check and end markers and the run token.
---
# Jest probe

**File and name.** Write the planned file (normally under `__tests__/`, named `<name>.test.js`) holding exactly one
top-level `test('<name>', ...)` whose title is exactly the planned test name, not inside a `describe`. It is run
alone with `jest --runTestsByPath <file> -t '^<name>$'`, offline, with the project's own installed Jest; `require`
production code by its relative path. `test.each` on the one test is allowed. An `async` test must `await` the
target.

**Markers.** The environment variable `CORSAIR_MARKER_DIR` names a directory. The first statement of the test body
writes a file named `start` there. Immediately before the main assertion it writes `check`, containing `safe` if
the asserted condition holds and `unsafe` if not, computed from the same variable the assertion checks. The last
statement, after every assertion, writes `end`:

```js
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

test('name', () => {
  fs.writeFileSync(path.join(process.env.CORSAIR_MARKER_DIR, 'start'), '');
  const result = target(input);
  const holds = propertyHolds(result);
  fs.writeFileSync(path.join(process.env.CORSAIR_MARKER_DIR, 'check'), holds ? 'safe' : 'unsafe');
  assert.ok(holds, process.env.CORSAIR_TOKEN);
  fs.writeFileSync(path.join(process.env.CORSAIR_MARKER_DIR, 'end'), '');
});
```

**Token.** Jest's `expect` takes no custom message, so in both probes the main assertion uses
`assert.ok(holds, process.env.CORSAIR_TOKEN)` from `node:assert`. Never log the token elsewhere.

**Pitfalls.** Do not wrap the assertion in `try`/`catch`; do not use `test.skip`, `test.todo`, `test.failing` or
`.only`; do not leave a promise un-awaited (the test would end before its assertion); keep exactly one test.
