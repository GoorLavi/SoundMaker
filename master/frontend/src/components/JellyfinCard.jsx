import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../api";
import "./JellyfinCard.css";

const POLL_INTERVAL = 30_000; // 30 seconds

export default function JellyfinCard() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await apiFetch("/api/jellyfin/status");
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
    const interval = setInterval(fetchStatus, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  if (error && !status) {
    return (
      <section className="card jellyfin">
        <div className="card__header">
          <h2 className="card__title">Media Server</h2>
          <span className="card__badge card__badge--muted">offline</span>
        </div>
        <p className="jellyfin__error">{error}</p>
      </section>
    );
  }

  if (!status) {
    return (
      <section className="card jellyfin">
        <div className="card__header">
          <h2 className="card__title">Media Server</h2>
        </div>
        <div className="jellyfin__loading">Loading…</div>
      </section>
    );
  }

  const { installed, running, url } = status;

  if (!installed) {
    return (
      <section className="card jellyfin">
        <div className="card__header">
          <h2 className="card__title">Media Server</h2>
          <span className="card__badge card__badge--muted">not installed</span>
        </div>
        <p className="jellyfin__info">
          Jellyfin media server is not installed on this system.
        </p>
      </section>
    );
  }

  return (
    <section className="card jellyfin">
      <div className="card__header">
        <h2 className="card__title">Media Server</h2>
        <span
          className={`card__badge ${running ? "card__badge--green" : "card__badge--red"}`}
        >
          {running ? "running" : "stopped"}
        </span>
      </div>

      <p className="jellyfin__description">
        Stream movies and TV shows to any device on your network.
      </p>

      <div className="jellyfin__actions">
        <a
          className="jellyfin__link"
          href={url}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open Jellyfin
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
            <polyline points="15 3 21 3 21 9" />
            <line x1="10" y1="14" x2="21" y2="3" />
          </svg>
        </a>
      </div>

      {!running && (
        <p className="jellyfin__warning">
          Jellyfin service is not running. SSH in and run: <code>sudo systemctl start jellyfin</code>
        </p>
      )}
    </section>
  );
}
