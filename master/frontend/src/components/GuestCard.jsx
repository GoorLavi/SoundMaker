import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../api";
import "./GuestCard.css";

/**
 * Admin card for the public guest landing page (/guest): configure the
 * guest Wi-Fi details, welcome message, and turn the page on/off.
 */
export default function GuestCard() {
  const [config, setConfig] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiFetch("/api/guest")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(setConfig)
      .catch(() => setError("Cannot reach backend"));
  }, []);

  const save = useCallback(
    async (next) => {
      setSaving(true);
      setSaved(false);
      try {
        const res = await apiFetch("/api/guest", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(next),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setConfig(await res.json());
        setError(null);
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      } catch {
        setError("Could not save");
      } finally {
        setSaving(false);
      }
    },
    []
  );

  const setField = (field, value) => setConfig((c) => ({ ...c, [field]: value }));

  if (error && !config) {
    return (
      <section className="card guest-admin">
        <div className="card__header">
          <h2 className="card__title">Guest Page</h2>
          <span className="card__badge card__badge--muted">offline</span>
        </div>
        <p className="guest-admin__muted">{error}</p>
      </section>
    );
  }

  if (!config) {
    return (
      <section className="card guest-admin">
        <div className="card__header">
          <h2 className="card__title">Guest Page</h2>
        </div>
        <div className="guest-admin__muted">Loading…</div>
      </section>
    );
  }

  const canEnable = config.ssid.trim().length > 0;

  return (
    <section className="card guest-admin">
      <div className="card__header">
        <h2 className="card__title">Guest Page</h2>
        <span className={`card__badge ${config.enabled ? "card__badge--green" : "card__badge--muted"}`}>
          {config.enabled ? "live" : "off"}
        </span>
      </div>

      <p className="guest-admin__description">
        A public welcome page at <code>/guest</code> with a scan-to-join Wi-Fi QR code —
        show it to visitors instead of spelling out the password.
      </p>

      <div className="guest-admin__form">
        <label className="guest-admin__field">
          <span>Wi-Fi network (SSID)</span>
          <input
            type="text"
            value={config.ssid}
            placeholder="MyHomeWiFi"
            onChange={(e) => setField("ssid", e.target.value)}
          />
        </label>

        <label className="guest-admin__field">
          <span>Wi-Fi password</span>
          <input
            type="text"
            value={config.password}
            placeholder="secret123"
            onChange={(e) => setField("password", e.target.value)}
          />
        </label>

        <label className="guest-admin__field">
          <span>Security</span>
          <select value={config.security} onChange={(e) => setField("security", e.target.value)}>
            <option value="WPA">WPA / WPA2 / WPA3</option>
            <option value="WEP">WEP</option>
            <option value="nopass">Open (no password)</option>
          </select>
        </label>

        <label className="guest-admin__field">
          <span>Welcome message (optional)</span>
          <textarea
            rows={2}
            value={config.welcome_message}
            placeholder="Make yourself at home! The bathroom code is..."
            onChange={(e) => setField("welcome_message", e.target.value)}
          />
        </label>

        <label className="guest-admin__checkbox">
          <input
            type="checkbox"
            checked={config.show_jellyfin}
            onChange={(e) => setField("show_jellyfin", e.target.checked)}
          />
          <span>Show Jellyfin (media library) link</span>
        </label>

        <label className="guest-admin__checkbox">
          <input
            type="checkbox"
            checked={config.hidden}
            onChange={(e) => setField("hidden", e.target.checked)}
          />
          <span>Network is hidden (not broadcast)</span>
        </label>
      </div>

      <div className="guest-admin__actions">
        <button
          className="guest-admin__save"
          disabled={saving}
          onClick={() => save(config)}
        >
          {saving ? "Saving…" : saved ? "Saved ✓" : "Save"}
        </button>
        <button
          className={`guest-admin__toggle ${config.enabled ? "guest-admin__toggle--on" : ""}`}
          disabled={saving || (!config.enabled && !canEnable)}
          title={!canEnable ? "Set an SSID first" : undefined}
          onClick={() => save({ ...config, enabled: !config.enabled })}
        >
          {config.enabled ? "Turn off" : "Turn on"}
        </button>
        {config.enabled && (
          <a className="guest-admin__link" href="/guest" target="_blank" rel="noopener noreferrer">
            Open guest page →
          </a>
        )}
      </div>

      {error && <p className="guest-admin__error">{error}</p>}

      <p className="guest-admin__note">
        The guest page is intentionally public — anyone on your network (or your
        Tailscale VPN) can open it without logging in. Turn it off when you don't need it.
      </p>
    </section>
  );
}
