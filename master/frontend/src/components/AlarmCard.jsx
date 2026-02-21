import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "../api";
import "./AlarmCard.css";

const POLL_INTERVAL = 30_000;

const ALL_DAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
const DAY_LABELS = { sun: "S", mon: "M", tue: "T", wed: "W", thu: "T", fri: "F", sat: "S" };
const DAY_FULL = { sun: "Sun", mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat" };
const JS_TO_DAY = [/* 0=Sun */ "sun", "mon", "tue", "wed", "thu", "fri", "sat"];

function formatNextAlarm(enabled, time, days) {
  if (!enabled || !time) return null;
  const activeDays = days && days.length > 0 ? days : ALL_DAYS;
  const [h, m] = time.split(":").map(Number);
  const now = new Date();
  for (let offset = 0; offset < 8; offset++) {
    const candidate = new Date(now.getFullYear(), now.getMonth(), now.getDate() + offset, h, m, 0);
    if (candidate <= now) continue;
    const dayAbbr = JS_TO_DAY[candidate.getDay()];
    if (!activeDays.includes(dayAbbr)) continue;
    const isToday = candidate.toDateString() === now.toDateString();
    const isTomorrow = offset === 1 || (offset === 0 && false);
    const tomorrowCheck = new Date(now); tomorrowCheck.setDate(tomorrowCheck.getDate() + 1);
    const timeStr = candidate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (isToday) return `Today at ${timeStr}`;
    if (candidate.toDateString() === tomorrowCheck.toDateString()) return `Tomorrow at ${timeStr}`;
    return `${DAY_FULL[dayAbbr]} at ${timeStr}`;
  }
  return null;
}

function describeDays(days) {
  if (!days || days.length === 0 || days.length === 7) return "Every day";
  const weekdays = ["mon", "tue", "wed", "thu", "fri"];
  const weekend = ["sat", "sun"];
  if (weekdays.every((d) => days.includes(d)) && !days.includes("sat") && !days.includes("sun")) return "Weekdays";
  if (weekend.every((d) => days.includes(d)) && days.length === 2) return "Weekends";
  return days.map((d) => DAY_FULL[d]).join(", ");
}

export default function AlarmCard() {
  const [alarm, setAlarm] = useState(null);
  const [spotify, setSpotify] = useState(null);
  const [saving, setSaving] = useState(false);
  const [playlists, setPlaylists] = useState([]);
  const [loadingPlaylists, setLoadingPlaylists] = useState(false);
  const intervalRef = useRef(null);

  const fetchAlarm = useCallback(async () => {
    try {
      const res = await apiFetch("/api/alarm");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setAlarm(data);
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

  const fetchPlaylists = useCallback(async () => {
    setLoadingPlaylists(true);
    try {
      const res = await apiFetch("/api/spotify/playlists");
      if (!res.ok) return;
      const data = await res.json();
      setPlaylists(data.playlists || []);
    } catch {
      setPlaylists([]);
    } finally {
      setLoadingPlaylists(false);
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

  useEffect(() => {
    if (spotify?.connected) fetchPlaylists();
  }, [spotify?.connected, fetchPlaylists]);

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
        days: patch.days !== undefined ? patch.days : alarm.days,
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

  const handleDayToggle = (day) => {
    if (!alarm || saving) return;
    const current = alarm.days || ALL_DAYS;
    const next = current.includes(day)
      ? current.filter((d) => d !== day)
      : [...current, day].sort((a, b) => ALL_DAYS.indexOf(a) - ALL_DAYS.indexOf(b));
    if (next.length === 0) return;
    setAlarm((prev) => (prev ? { ...prev, days: next } : prev));
    updateAlarm({ days: next });
  };

  const handlePlaylistChange = (e) => {
    const uri = e.target.value || null;
    updateAlarm({ playlist_uri: uri });
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

  const nextLabel = formatNextAlarm(alarm.enabled, alarm.time, alarm.days);

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

      <div className="alarm__days-row">
        <span className="alarm__label">Repeat</span>
        <div className="alarm__days">
          {ALL_DAYS.map((day) => {
            const active = (alarm.days || ALL_DAYS).includes(day);
            return (
              <button
                key={day}
                type="button"
                className={`alarm__day ${active ? "alarm__day--active" : ""}`}
                onClick={() => handleDayToggle(day)}
                disabled={saving}
                aria-label={DAY_FULL[day]}
                aria-pressed={active}
              >
                {DAY_LABELS[day]}
              </button>
            );
          })}
        </div>
        <span className="alarm__days-summary">{describeDays(alarm.days)}</span>
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
        {spotify?.connected && playlists.length > 0 ? (
          <select
            id="alarm-playlist"
            className="alarm__playlist-select"
            value={alarm.playlist_uri || ""}
            onChange={handlePlaylistChange}
            disabled={saving}
            aria-label="Choose a Spotify playlist"
          >
            <option value="">No playlist (resume last)</option>
            {playlists.map((p) => (
              <option key={p.uri} value={p.uri}>
                {p.name} ({p.track_count} tracks)
              </option>
            ))}
          </select>
        ) : spotify?.connected && loadingPlaylists ? (
          <p className="alarm__spotify-msg">Loading playlists…</p>
        ) : (
          <p className="alarm__spotify-msg">Connect Spotify to choose a playlist.</p>
        )}
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
