import test from "node:test";
import assert from "node:assert/strict";
import {
  histogram,
  mean,
  median,
  rate,
  percentile,
  distributionScale,
  frequencyPath,
} from "./metrics.ts";
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

test("shared bins preserve counts, outliers and zero across agent cards", () => {
  const series = [
    [0, 0],
    [1, 8, 100],
  ];
  const scale = distributionScale(series);
  assert.equal(scale.max, 100);
  assert.equal(scale.peak, 2);
  assert.equal(histogram(series[0], scale.max).length, 8);
  assert.deepEqual(
    histogram(series[0], scale.max).map((b) => [b.min, b.max]),
    histogram(series[1], scale.max).map((b) => [b.min, b.max]),
  );
  assert.equal(
    histogram(series[1], scale.max).reduce((n, b) => n + b.count, 0),
    3,
  );
  assert.equal(histogram(series[1], scale.max).at(-1)?.count, 1);
  assert.equal(percentile([], 0.95), undefined);
  assert.equal(percentile([0, 1, 2, 3, 4], 0.95), 4);
  assert.equal(frequencyPath([]), "");
  assert.equal(
    frequencyPath([
      { x: 0, y: 20 },
      { x: 10, y: 0 },
      { x: 20, y: 30 },
    ]),
    "M 0 20 C 5 20, 5 0, 10 0 C 15 0, 15 30, 20 30",
  );
});
