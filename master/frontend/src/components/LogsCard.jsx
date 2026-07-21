import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "../api";
import "./LogsCard.css";

const LINE_OPTIONS = [50, 100, 200];
const AUTO_REFRESH_MS = 5_000;

function formatTime(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function LogsCard() {
  const [services, setServices] = useState([]);
  const [service, setService] = useState("backend");
  const [lines, setLines] = useState(100);
  const [entries, setEntries] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [auto, setAuto] = useState(false);
  const viewerRef = useRef(null);

  useEffect(() => {
    apiFetch("/api/system/logs/services")
      .then((r) => r.json())
      .then((d) => setServices(d.services || []))
      .catch(() => {});
  }, []);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch(
        `/api/system/logs?service=${encodeURIComponent(service)}&lines=${lines}`
      );
      const data = await res.json();
      if (data.error) {
        setError(data.error);
        setEntries([]);
      } else {
        setError(null);
        setEntries(data.entries || []);
      }
    } catch {
      setError("Could not load logs");
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, [service, lines]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  useEffect(() => {
    if (!auto) return undefined;
    const id = setInterval(fetchLogs, AUTO_REFRESH_MS);
    return () => clearInterval(id);
  }, [auto, fetchLogs]);

  // Keep the newest lines in view.
  useEffect(() => {
    if (viewerRef.current) viewerRef.current.scrollTop = viewerRef.current.scrollHeight;
  }, [entries]);

  return (
    <section className="card logs">
      <div className="card__header">
        <h2 className="card__title">Logs</h2>
        {loading && <span className="card__badge card__badge--muted">loading…</span>}
      </div>

      <div className="logs__controls">
        <select
          className="logs__select"
          value={service}
          onChange={(e) => setService(e.target.value)}
          aria-label="Service"
        >
          {services.length === 0 && <option value="backend">SoundMaker backend</option>}
          {services.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label}
            </option>
          ))}
        </select>
        <select
          className="logs__select logs__select--lines"
          value={lines}
          onChange={(e) => setLines(Number(e.target.value))}
          aria-label="Number of lines"
        >
          {LINE_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n} lines
            </option>
          ))}
        </select>
        <button className="logs__btn" onClick={fetchLogs} disabled={loading}>
          Refresh
        </button>
        <label className="logs__auto">
          <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
          Auto
        </label>
      </div>

      {error ? (
        <p className="logs__error">{error}</p>
      ) : entries.length === 0 ? (
        <p className="logs__empty">{loading ? "Loading…" : "No log entries."}</p>
      ) : (
        <div className="logs__viewer" ref={viewerRef}>
          {entries.map((e, i) => (
            <div key={i} className={`logs__line logs__line--${e.level}`}>
              <span className="logs__time">{formatTime(e.t)}</span>
              <span className="logs__message">{e.message}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
