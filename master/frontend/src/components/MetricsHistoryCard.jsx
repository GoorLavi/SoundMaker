import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../api";
import "./MetricsHistoryCard.css";

const POLL_MS = 60_000;

function Chart({ points, field, unit, color, warn }) {
  const values = points.map((p) => p[field]).filter((v) => v != null && !Number.isNaN(v));
  if (values.length < 2) {
    return <div className="metrics-chart__empty">Collecting data…</div>;
  }

  const W = 300;
  const H = 90;
  const PAD = 6;
  const min = Math.min(...values);
  const max = Math.max(...values);
  let lo = min;
  let hi = max;
  if (warn != null) hi = Math.max(hi, warn);
  const headroom = (hi - lo) * 0.1 || 1;
  lo -= headroom;
  hi += headroom;
  const span = hi - lo || 1;
  const n = points.length;

  const x = (i) => PAD + (i / (n - 1)) * (W - 2 * PAD);
  const y = (v) => PAD + (1 - (v - lo) / span) * (H - 2 * PAD);

  let d = "";
  points.forEach((p, i) => {
    const v = p[field];
    if (v == null || Number.isNaN(v)) return;
    d += `${d === "" ? "M" : "L"}${x(i).toFixed(1)} ${y(v).toFixed(1)} `;
  });

  const last = values[values.length - 1];
  const warnY = warn != null ? y(warn) : null;
  const round = (v) => (Number.isInteger(v) ? v : Math.round(v * 10) / 10);

  return (
    <div className="metrics-chart">
      <div className="metrics-chart__head">
        <span className="metrics-chart__now" style={{ color }}>
          {round(last)}
          {unit}
        </span>
        <span className="metrics-chart__range">
          min {round(min)}{unit} · max {round(max)}{unit}
        </span>
      </div>
      <svg
        className="metrics-chart__svg"
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`${field} over time`}
      >
        {warnY != null && warnY >= 0 && warnY <= H && (
          <line x1="0" y1={warnY} x2={W} y2={warnY} className="metrics-chart__warn" />
        )}
        <path
          d={d.trim()}
          fill="none"
          stroke={color}
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

export default function MetricsHistoryCard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const res = await apiFetch("/api/system/metrics-history");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
      setError(false);
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, POLL_MS);
    return () => clearInterval(id);
  }, [fetchData]);

  const points = data?.points || [];

  return (
    <section className="card metrics-history">
      <div className="card__header">
        <h2 className="card__title">History (24h)</h2>
        {points.length > 0 && (
          <span className="card__badge card__badge--muted">{points.length} min</span>
        )}
      </div>

      {error && points.length === 0 ? (
        <p className="metrics-history__msg">Cannot load history.</p>
      ) : points.length === 0 ? (
        <p className="metrics-history__msg">Collecting data… check back in a few minutes.</p>
      ) : (
        <div className="metrics-history__charts">
          <div className="metrics-history__item">
            <span className="metrics-history__label">CPU temperature</span>
            <Chart points={points} field="temp_c" unit="°C" color="var(--orange)" warn={70} />
          </div>
          <div className="metrics-history__item">
            <span className="metrics-history__label">CPU load (1&nbsp;min avg)</span>
            <Chart points={points} field="load" unit="" color="var(--accent)" />
          </div>
          <div className="metrics-history__item">
            <span className="metrics-history__label">Memory used</span>
            <Chart points={points} field="mem_pct" unit="%" color="var(--green)" />
          </div>
        </div>
      )}

      <p className="metrics-history__foot">Newest on the right · sampled every minute</p>
    </section>
  );
}
