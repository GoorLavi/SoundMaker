import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../api";
import "./TailscaleCard.css";

const POLL_INTERVAL = 30_000; // 30 seconds

/**
 * Tailscale VPN card for the System tab: connection info + the exit-node
 * toggle that turns the Pi into a "route my phone's traffic through home"
 * VPN (Pi-hole ad blocking everywhere, safe hotel Wi-Fi).
 */
export default function TailscaleCard() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [toggling, setToggling] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await apiFetch("/api/tailscale/status");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setStatus(await res.json());
      setError(null);
    } catch {
      setError("Cannot reach backend");
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const toggleExitNode = useCallback(async () => {
    if (!status) return;
    setToggling(true);
    try {
      const res = await apiFetch("/api/tailscale/exit-node", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !status.exit_node?.advertised }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchStatus();
    } catch {
      setError("Could not update exit node");
    } finally {
      setToggling(false);
    }
  }, [status, fetchStatus]);

  if (error && !status) {
    return (
      <section className="card tailscale">
        <div className="card__header">
          <h2 className="card__title">Tailscale VPN</h2>
          <span className="card__badge card__badge--muted">offline</span>
        </div>
        <p className="tailscale__muted">{error}</p>
      </section>
    );
  }

  if (!status) {
    return (
      <section className="card tailscale">
        <div className="card__header">
          <h2 className="card__title">Tailscale VPN</h2>
        </div>
        <div className="tailscale__muted">Loading…</div>
      </section>
    );
  }

  if (!status.installed) {
    return (
      <section className="card tailscale">
        <div className="card__header">
          <h2 className="card__title">Tailscale VPN</h2>
          <span className="card__badge card__badge--muted">not installed</span>
        </div>
        <p className="tailscale__muted">Tailscale is not installed on this system.</p>
      </section>
    );
  }

  const { running, hostname, dns_name, ip, exit_node, admin_console_url } = status;
  const advertised = Boolean(exit_node?.advertised);
  const approved = Boolean(exit_node?.approved);

  return (
    <section className="card tailscale">
      <div className="card__header">
        <h2 className="card__title">Tailscale VPN</h2>
        <span className={`card__badge ${running ? "card__badge--green" : "card__badge--red"}`}>
          {running ? "connected" : "not connected"}
        </span>
      </div>

      <div className="tailscale__info">
        {hostname && (
          <div className="tailscale__row">
            <span className="tailscale__label">Device</span>
            <span className="tailscale__value">{hostname}</span>
          </div>
        )}
        {dns_name && (
          <div className="tailscale__row">
            <span className="tailscale__label">Tailnet name</span>
            <span className="tailscale__value">{dns_name}</span>
          </div>
        )}
        {ip && (
          <div className="tailscale__row">
            <span className="tailscale__label">Tailscale IP</span>
            <span className="tailscale__value">{ip}</span>
          </div>
        )}
      </div>

      <div className="tailscale__exit">
        <div className="tailscale__exit-header">
          <h3 className="tailscale__exit-title">Exit node (home VPN)</h3>
          <span
            className={`card__badge ${
              advertised && approved
                ? "card__badge--green"
                : advertised
                  ? "card__badge--orange"
                  : "card__badge--muted"
            }`}
          >
            {advertised && approved ? "active" : advertised ? "awaiting approval" : "off"}
          </span>
        </div>
        <p className="tailscale__exit-description">
          Route your phone's entire traffic through home while traveling: Pi-hole ad
          blocking everywhere, and safe browsing on hotel or airport Wi-Fi.
        </p>

        <button
          className={`tailscale__toggle ${advertised ? "tailscale__toggle--on" : ""}`}
          disabled={toggling || !running}
          onClick={toggleExitNode}
        >
          {toggling ? "Working…" : advertised ? "Stop offering exit node" : "Enable exit node"}
        </button>

        {advertised && !approved && (
          <p className="tailscale__warning">
            One more step: approve this device as an exit node in the{" "}
            <a href={admin_console_url} target="_blank" rel="noopener noreferrer">
              Tailscale admin console
            </a>{" "}
            (Machines → {hostname || "this device"} → Edit route settings → Use as exit node).
          </p>
        )}

        {advertised && approved && (
          <p className="tailscale__hint">
            On your phone: open the Tailscale app → Exit node → choose{" "}
            <strong>{hostname || "this device"}</strong>. Speed is limited by your home
            connection's upload bandwidth.
          </p>
        )}
      </div>

      {error && <p className="tailscale__error">{error}</p>}
    </section>
  );
}
