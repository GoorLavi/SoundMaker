import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "../api";
import "./PiholeCard.css";

const POLL_INTERVAL = 10_000;

export default function PiholeCard() {
  const [status, setStatus] = useState(null);
  const [toggling, setToggling] = useState(false);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await apiFetch("/api/pihole/status");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setStatus(data);
      setError(null);
    } catch (err) {
      setError("Cannot reach backend");
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    intervalRef.current = setInterval(fetchStatus, POLL_INTERVAL);
    return () => clearInterval(intervalRef.current);
  }, [fetchStatus]);

  const toggleBlocking = async () => {
    if (!status?.available || toggling) return;
    setToggling(true);
    try {
      const endpoint = status.blocking === true
        ? "/api/pihole/disable"
        : "/api/pihole/enable";
      const res = await apiFetch(endpoint, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchStatus();
    } catch {
      setError("Toggle failed");
    } finally {
      setToggling(false);
    }
  };

  if (error && !status) {
    return (
      <section className="card pihole">
        <div className="card__header">
          <h2 className="card__title">Pi-hole</h2>
          <span className="card__badge card__badge--muted">offline</span>
        </div>
        <p className="pihole__error">{error}</p>
      </section>
    );
  }

  if (!status) {
    return (
      <section className="card pihole">
        <div className="card__header">
          <h2 className="card__title">Pi-hole</h2>
        </div>
        <div className="pihole__loading">Loading…</div>
      </section>
    );
  }

  const available = status.available;
  const blocking = status.blocking === true;
  const queries = status.queries?.total ?? "—";
  const blocked = status.queries?.blocked ?? "—";
  const percent =
    status.queries?.percent_blocked != null
      ? `${status.queries.percent_blocked.toFixed(1)}%`
      : "—";

  return (
    <section className="card pihole">
      <div className="card__header">
        <h2 className="card__title">Pi-hole</h2>
        {available ? (
          <span
            className={`card__badge ${blocking ? "card__badge--green" : "card__badge--red"}`}
          >
            {blocking ? "active" : "disabled"}
          </span>
        ) : (
          <span className="card__badge card__badge--muted">unavailable</span>
        )}
      </div>

      {available && (
        <>
          <div className="pihole__stats">
            <div className="pihole__stat">
              <span className="pihole__stat-value">{queries}</span>
              <span className="pihole__stat-label">Queries</span>
            </div>
            <div className="pihole__stat">
              <span className="pihole__stat-value">{blocked}</span>
              <span className="pihole__stat-label">Blocked</span>
            </div>
            <div className="pihole__stat">
              <span className="pihole__stat-value">{percent}</span>
              <span className="pihole__stat-label">Blocked %</span>
            </div>
          </div>

          <div className="pihole__actions">
            <button
              className={`pihole__toggle ${blocking ? "pihole__toggle--on" : "pihole__toggle--off"}`}
              onClick={toggleBlocking}
              disabled={toggling}
            >
              <span className="pihole__toggle-track">
                <span className="pihole__toggle-thumb" />
              </span>
              <span className="pihole__toggle-label">
                {toggling ? "…" : blocking ? "Blocking on" : "Blocking off"}
              </span>
            </button>

            <a
              className="pihole__admin-link"
              href={`${window.location.protocol}//${window.location.hostname}:8080/admin`}
              target="_blank"
              rel="noopener noreferrer"
            >
              Pi-hole Admin
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                <polyline points="15 3 21 3 21 9" />
                <line x1="10" y1="14" x2="21" y2="3" />
              </svg>
            </a>
          </div>
        </>
      )}

      {!available && (
        <p className="pihole__error">
          Pi-hole is not reachable. Check that pihole-FTL is running.
        </p>
      )}
    </section>
  );
}
