import test from "node:test";
import assert from "node:assert/strict";
import { parseTheme, isDark } from "./theme.ts";
test("theme respects explicit choice, otherwise system", () => {
  assert.equal(parseTheme("unknown"), "system");
  assert.equal(isDark("system", true), true);
  assert.equal(isDark("light", true), false);
  assert.equal(isDark("dark", false), true);
});
