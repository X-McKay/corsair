# Baseline outputs for the environment agent's file-unit frameworks

Stdout captured offline (`--network=none`) for `agents/environment/frameworks.py`:
- `jest24.8.0-*`: Jest 24.8.0 from the `node8` image's locked fixture, run as `node node_modules/jest/bin/jest.js --ci`. The files are `--listTests` and `--json --runTestsByPath` on four probe files: all passed (one test logs to the console), one `test.skip`, one `test.todo`, and one failure. There is also the same passing file without `--json`, whose stdout carries no results.
- `minitest5.15.0-*`: Minitest 5.15.0 (bundled with Ruby 3.1.7) from the `ruby31` image, run as `ruby -Itest test/<name>_test.rb`. The four probe files are: all passed (one test prints), one `skip`, one failure, and a file with no tests.

Probe test sources are shown in the test parameters' comments in `tests/agents/test_environment.py`; they hold no project code.
