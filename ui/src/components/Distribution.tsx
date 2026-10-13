import { useEffect, useRef, useState } from "react";
import { duration, number } from "../lib/format";
import { histogram, median, percentile, frequencyPath } from "../lib/metrics";

export function Distribution({
  title,
  values,
  attempts,
  time = false,
  scale,
}: {
  title: string;
  values: number[];
  attempts: number | null;
  time?: boolean;
  scale: { max: number; peak: number };
}) {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(240);
  useEffect(() => {
    const el = container.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) =>
      setWidth(Math.max(1, entry.contentRect.width)),
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  const bins = histogram(values, scale.max),
    format = time ? duration : number;
  const step = (width - 16) / Math.max(1, bins.length),
    baseline = 99;
  const points = bins.map((b, i) => ({
    x: 8 + step * (i + 0.5),
    y: baseline - (72 * b.count) / scale.peak,
  }));
  return (
    <section className="distribution" aria-label={`${title} distribution`}>
      <h3>{title}</h3>
      <div className="distribution-summary">
        <strong>{format(median(values))}</strong>
        <span>median · p95 {format(percentile(values, 0.95))}</span>
      </div>
      <div ref={container} className="histogram-container">
        {values.length ? (
          <svg
            className="histogram"
            viewBox={`0 0 ${width} 123`}
            role="img"
            aria-label={`${title}: ${values.length} observed samples`}
          >
            <title>
              {title}: bars and frequency line use the same bin counts; vertical
              scale 0–{scale.peak} {scale.peak === 1 ? "sample" : "samples"}.
            </title>
            <line
              x1="8"
              y1={baseline}
              x2={width - 8}
              y2={baseline}
              className="chart-axis"
            />
            <text x="8" y="14" className="chart-label">
              {scale.peak} {scale.peak === 1 ? "sample" : "samples"}
            </text>
            {bins.map((bin, i) => (
              <rect
                key={i}
                x={8 + i * step + 1}
                y={points[i].y}
                width={Math.max(0, step - 2)}
                height={baseline - points[i].y}
                rx="2"
                className="chart-bar"
              >
                <title>{`${format(bin.min)}–${format(bin.max)}: ${bin.count} samples`}</title>
              </rect>
            ))}
            <path className="chart-frequency" d={frequencyPath(points)} />
            <text x="8" y="118" className="chart-label">
              {format(0)}
            </text>
            {width > 260 && (
              <text
                x={width / 2}
                y="118"
                textAnchor="middle"
                className="chart-label"
              >
                {format(scale.max / 2)}
              </text>
            )}
            <text
              x={width - 8}
              y="118"
              textAnchor="end"
              className="chart-label"
            >
              {format(scale.max)}
            </text>
          </svg>
        ) : (
          <p className="distribution-empty">
            No observed samples. Unknown, not zero.
          </p>
        )}
      </div>
      <p className="distribution-note">
        {values.length}/{attempts ?? "unknown"} attempts measured ·{" "}
        {time ? "seconds" : "tokens"} per attempt
      </p>
      {!!values.length && (
        <details className="distribution-data">
          <summary>View distribution data</summary>
          <table>
            <thead>
              <tr>
                <th>Range</th>
                <th>Samples</th>
              </tr>
            </thead>
            <tbody>
              {bins.map((b, i) => (
                <tr key={i}>
                  <td>
                    {format(b.min)} – {format(b.max)}
                  </td>
                  <td>{b.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </section>
  );
}
