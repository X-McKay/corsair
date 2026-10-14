---
name: minitest
description: Write one Corsair probe as a single Minitest test method in its own file, with the start and end markers and the run token.
---
# Minitest probe

**File and name.** Write the planned file under `test/` (e.g. `test/<name>_test.rb`) with `require
'minitest/autorun'`, one `Minitest::Test` subclass, and exactly one method named as planned, starting with `test_`.
It is run alone with `bundle exec ruby -Itest -Ilib <file> -v -n <name>` from the repository root, offline, with
the project's own bundle; `require` production code from `lib/`.

**Markers.** The environment variable `CORSAIR_MARKER_DIR` names a directory. The first statement of the method
writes a file named `start` there; the last statement, after every assertion, writes `end`:

```ruby
require 'minitest/autorun'

class TargetTest < Minitest::Test
  def test_name
    File.write(File.join(ENV.fetch('CORSAIR_MARKER_DIR'), 'start'), '')
    result = Target.call(input)
    assert property_holds?(result), ENV.fetch('CORSAIR_TOKEN')   # security probe only
    File.write(File.join(ENV.fetch('CORSAIR_MARKER_DIR'), 'end'), '')
  end
end
```

**Token.** In the security (exploit) probe, the security assertion's message is exactly `ENV.fetch('CORSAIR_TOKEN')`
(the last argument of `assert`, `assert_equal` and friends). Never print it elsewhere. The control probe asserts
with no token.

**Pitfalls.** Do not `rescue Minitest::Assertion` (or `Exception`) around the assertion; do not use `skip`; keep
exactly one `test_` method (helpers must not start with `test_`).
