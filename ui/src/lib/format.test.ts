import test from "node:test";
import assert from "node:assert/strict";
import { number, duration, timestamp } from "./format.ts";
test("absent measurements are not zero; malformed times stay unavailable", () => {
  assert.equal(number(undefined), "Unavailable");
  assert.equal(number(0), "0");
  assert.equal(number(Infinity), "Unavailable");
  assert.equal(number(NaN), "Unavailable");
  assert.equal(duration(-1), "Unavailable");
  assert.equal(timestamp("not-a-date"), "Unavailable");
});
