import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "../api";
import "./AlarmCard.css";

const POLL_INTERVAL = 30_000;

function formatNextAlarm(enabled, time) {
  if (!enabled || !time) return null;
  const [h, m] = time.split(":").map(Number);
  const now = new Date();
  let next = new Date(now.getFullYear(), now.getMonth(), now.getDate(), h, m, 0);
  if (next <= now) next.setDate(next.getDate() + 1);
  const isToday = next.toDateString() === now.toDateString();
  const timeStr = next.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return isToday ? `Today at ${timeStr}` : `Tomorrow at ${timeStr}`;
}

export default function AlarmCard() {
  const [alarm, setAlarm] = useState(null);
  const [spotify, setSpotify] = useState(null);
  const [saving, setSaving] = useState(false);
  const [playlistInput, setPlaylistInput] = useState("");
  const intervalRef = useRef(null);
  const playlistDebounceRef = useRef(null);

  const fetchAlarm = useCallback(async () => {
    try {
      const res = await apiFetch("/api/alarm");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setAlarm(data);
      setPlaylistInput(data.playlist_uri ?? "");
    } catch {
      setAlarm(null);
    }
  }, []);

  const fetchSpotify = useCallback(async () => {
    try {
      const res = await apiFetch("/api/spotify/status");
      if (!res.ok) return;
      const data = await res.json();
      setSpotify(data);
    } catch {
      setSpotify(null);
    }
  }, []);

  const fetchAll = useCallback(() => {
    fetchAlarm();
    fetchSpotify();
  }, [fetchAlarm, fetchSpotify]);

  useEffect(() => {
    fetchAll();
    intervalRef.current = setInterval(fetchAll, POLL_INTERVAL);
    return () => clearInterval(intervalRef.current);
  }, [fetchAll]);

  // After OAuth callback, URL may have ?spotify=connected
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("spotify") === "connected") {
      window.history.replaceState({}, "", window.location.pathname + window.location.hash);
      fetchSpotify();
    }
  }, [fetchSpotify]);

  const updateAlarm = useCallback(async (patch) => {
    if (!alarm) return;
    setSaving(true);
    try {
      const body = {
        enabled: patch.enabled ?? alarm.enabled,
        time: patch.time ?? alarm.time,
        playlist_uri: patch.playlist_uri !== undefined ? patch.playlist_uri : alarm.playlist_uri,
      };
      const res = await apiFetch("/api/alarm", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setAlarm(data);
    } catch {
      // keep local state
    } finally {
      setSaving(false);
    }
  }, [alarm]);

  const handleToggle = () => {
    if (!alarm || saving) return;
    updateAlarm({ enabled: !alarm.enabled });
  };

  const handleTimeChange = (e) => {
    const time = e.target.value;
    if (!alarm) return;
    setAlarm((prev) => (prev ? { ...prev, time } : prev));
    updateAlarm({ time });
  };

  const handlePlaylistBlur = () => {
    const uri = playlistInput.trim() || null;
    if (alarm && (uri !== (alarm.playlist_uri || ""))) {
      updateAlarm({ playlist_uri: uri });
    }
  };

  const handleConnectSpotify = async () => {
    try {
      const res = await apiFetch("/api/spotify/auth-url");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.url) window.open(data.url, "_blank", "noopener");
    } catch {
      // show nothing or toast
    }
  };

  const handleDisconnectSpotify = async () => {
    try {
      await apiFetch("/api/spotify/disconnect", { method: "POST" });
      setSpotify((prev) => (prev ? { ...prev, connected: false } : prev));
    } catch {
      // ignore
    }
  };

  if (alarm === null) {
    return (
      <section className="card alarm">
        <div className="card__header">
          <h2 className="card__title">Morning wake-up</h2>
        </div>
        <div className="alarm__loading">Loading…</div>
      </section>
    );
  }

  const nextLabel = formatNextAlarm(alarm.enabled, alarm.time);

  return (
    <section className="card alarm">
      <div className="card__header">
        <h2 className="card__title">Morning wake-up</h2>
        <div className="alarm__badges">
          <span
            className={`card__badge ${alarm.enabled ? "card__badge--green" : "card__badge--muted"}`}
          >
            {alarm.enabled ? "On" : "Off"}
          </span>
          {spotify?.connected ? (
            <span className="card__badge card__badge--green">Spotify connected</span>
          ) : spotify?.configured ? (
            <span className="card__badge card__badge--muted">Spotify not connected</span>
          ) : null}
        </div>
      </div>

      <div className="alarm__toggle-row">
        <button
          className={`alarm__toggle ${alarm.enabled ? "alarm__toggle--on" : "alarm__toggle--off"}`}
          onClick={handleToggle}
          disabled={saving}
          aria-label={alarm.enabled ? "Turn alarm off" : "Turn alarm on"}
        >
          <span className="alarm__toggle-track">
            <span className="alarm__toggle-thumb" />
          </span>
          <span className="alarm__toggle-label">
            {saving ? "…" : alarm.enabled ? "Alarm on" : "Alarm off"}
          </span>
        </button>
      </div>

      <div className="alarm__time-row">
        <label className="alarm__label" htmlFor="alarm-time">
          Wake time
        </label>
        <input
          id="alarm-time"
          type="time"
          className="alarm__time-input"
          value={alarm.time || "07:00"}
          onChange={handleTimeChange}
          disabled={saving}
          aria-label="Alarm time"
        />
      </div>

      {nextLabel && (
        <p className="alarm__next" aria-live="polite">
          Next: {nextLabel}
        </p>
      )}

      <div className="alarm__playlist-row">
        <label className="alarm__label" htmlFor="alarm-playlist">
          Playlist (optional)
        </label>
        <input
          id="alarm-playlist"
          type="text"
          className="alarm__playlist-input"
          placeholder="e.g. spotify:playlist:..."
          value={playlistInput}
          onChange={(e) => setPlaylistInput(e.target.value)}
          onBlur={handlePlaylistBlur}
          disabled={saving}
          aria-label="Spotify playlist URI"
        />
      </div>

      <div className="alarm__spotify">
        <span className="alarm__label">Spotify</span>
        {spotify?.configured === false && (
          <p className="alarm__spotify-msg">Not configured (set client ID/secret on server).</p>
        )}
        {spotify?.configured && !spotify?.connected && (
          <button
            type="button"
            className="alarm__spotify-btn"
            onClick={handleConnectSpotify}
          >
            Connect Spotify
          </button>
        )}
        {spotify?.connected && (
          <div className="alarm__spotify-connected">
            <span className="alarm__spotify-ok">Connected</span>
            <button
              type="button"
              className="alarm__spotify-disconnect"
              onClick={handleDisconnectSpotify}
            >
              Disconnect
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
