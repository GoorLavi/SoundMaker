import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../api";
import "./PowerCard.css";

const DAYS = [
  { key: "sun", label: "Sunday" },
  { key: "mon", label: "Monday" },
  { key: "tue", label: "Tuesday" },
  { key: "wed", label: "Wednesday" },
  { key: "thu", label: "Thursday" },
  { key: "fri", label: "Friday" },
  { key: "sat", label: "Saturday" },
];

export default function PowerCard() {
  const [config, setConfig] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [action, setAction] = useState(null); // { ok, msg }

  const fetchConfig = useCallback(async () => {
    try {
      const res = await apiFetch("/api/system/auto-reboot");
      setConfig(await res.json());
    } catch {
      setConfig({ enabled: false, day: "sun", time: "04:30" });
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const doRestart = async () => {
    if (
      !window.confirm(
        "Restart the SoundMaker app now? The page will be unavailable for a few seconds."
      )
    )
      return;
    setAction(null);
    try {
      const res = await apiFetch("/api/system/restart-service", { method: "POST" });
      const d = await res.json();
      setAction(
        res.ok
          ? { ok: true, msg: "Backend restarting… reload the page in about 10 seconds." }
          : { ok: false, msg: d.error || "Could not restart" }
      );
    } catch {
      setAction({ ok: false, msg: "Request failed" });
    }
  };

  const doReboot = async () => {
    if (
      !window.confirm(
        "Reboot the whole Raspberry Pi now? Audio, Pi-hole and Jellyfin go down for about a minute."
      )
    )
      return;
    setAction(null);
    try {
      const res = await apiFetch("/api/system/reboot", { method: "POST" });
      const d = await res.json();
      setAction(
        res.ok
          ? { ok: true, msg: "Rebooting… the Pi will be back in about a minute." }
          : { ok: false, msg: d.error || "Could not reboot" }
      );
    } catch {
      setAction({ ok: false, msg: "Request failed" });
    }
  };

  const save = async () => {
    if (!config) return;
    setSaving(true);
    setSaved(false);
    try {
      const res = await apiFetch("/api/system/auto-reboot", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      setConfig(await res.json());
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch {
      /* ignore */
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="card power">
      <div className="card__header">
        <h2 className="card__title">Power</h2>
      </div>

      <div className="power__actions">
        <button className="power__btn power__btn--secondary" onClick={doRestart}>
          Restart backend
        </button>
        <button className="power__btn power__btn--danger" onClick={doReboot}>
          Reboot Pi
        </button>
      </div>
      <p className="power__hint">
        Restart reloads just the SoundMaker app. Reboot restarts the whole Raspberry Pi.
      </p>

      {action && (
        <p className={`power__result ${action.ok ? "power__result--ok" : "power__result--err"}`}>
          {action.msg}
        </p>
      )}

      <div className="power__divider" />

      <div className="power__schedule">
        <div className="power__schedule-head">
          <span className="power__schedule-title">Weekly reboot</span>
          <label className="power__toggle">
            <input
              type="checkbox"
              checked={config?.enabled || false}
              onChange={(e) => setConfig((c) => ({ ...c, enabled: e.target.checked }))}
            />
            <span>{config?.enabled ? "On" : "Off"}</span>
          </label>
        </div>
        <p className="power__hint">Reboot automatically once a week to keep the Pi healthy.</p>
        <div className="power__schedule-controls">
          <select
            className="power__select"
            value={config?.day || "sun"}
            disabled={!config?.enabled}
            onChange={(e) => setConfig((c) => ({ ...c, day: e.target.value }))}
            aria-label="Reboot day"
          >
            {DAYS.map((d) => (
              <option key={d.key} value={d.key}>
                {d.label}
              </option>
            ))}
          </select>
          <input
            className="power__time"
            type="time"
            value={config?.time || "04:30"}
            disabled={!config?.enabled}
            onChange={(e) => setConfig((c) => ({ ...c, time: e.target.value }))}
            aria-label="Reboot time"
          />
          <button className="power__btn power__btn--primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
        {saved && <p className="power__result power__result--ok">Saved.</p>}
      </div>
    </section>
  );
}
