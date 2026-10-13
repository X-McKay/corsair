import test from "node:test";
import assert from "node:assert/strict";
import { histogram, mean, median, rate } from "./metrics.ts";
test("empty, zero and single-sample distributions preserve meaning", () => {
  assert.equal(mean([]), undefined);
  assert.equal(median([]), undefined);
  assert.equal(mean([0, 0]), 0);
  assert.equal(median([1, 4, 2, 3]), 2.5);
  assert.deepEqual(histogram([0, 0]), [{ min: 0, max: 0, count: 2 }]);
  assert.equal(rate(0, 4), "0.0%");
  assert.equal(rate(0, 0), "Unavailable");
});
test("histogram retains every sample including extrema without mutating inputs", () => {
  const values = [9, 1, 4, 4, 0, 10],
    before = [...values],
    bins = histogram(values);
  assert.equal(
    bins.reduce((n, b) => n + b.count, 0),
    values.length,
  );
  assert.equal(bins[0].min, 0);
  assert.equal(bins.at(-1)?.max, 10);
  assert.deepEqual(values, before);
});
