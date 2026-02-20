import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../api";
import "./SystemHealthCard.css";

const POLL_INTERVAL_MS = 20_000;

function formatUptime(seconds) {
  if (seconds == null || seconds < 0) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const parts = [];
  if (d > 0) parts.push(`${d}d`);
  if (h > 0) parts.push(`${h}h`);
  if (m > 0 || parts.length === 0) parts.push(`${m}m`);
  return parts.join(" ");
}

function InfoRow({ label, value, status }) {
  return (
    <div className="system-info__row">
      <span className="system-info__label">{label}</span>
      <span className={`system-info__value ${status ? `system-info__value--${status}` : ""}`}>
        {value ?? "—"}
      </span>
    </div>
  );
}

function SectionCard({ title, badge, badgeStatus, children }) {
  return (
    <div className="system-section">
      <div className="system-section__header">
        <h3 className="system-section__title">{title}</h3>
        {badge != null && (
          <span className={`card__badge card__badge--${badgeStatus || "muted"}`}>{badge}</span>
        )}
      </div>
      <div className="system-section__body">{children}</div>
    </div>
  );
}

export default function SystemHealthCard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const fetchInfo = useCallback(async () => {
    try {
      const res = await apiFetch("/api/system/info");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
      setError(null);
    } catch (e) {
      setError("Cannot load system info");
      setData(null);
    }
  }, []);

  useEffect(() => {
    fetchInfo();
    const id = setInterval(fetchInfo, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchInfo]);

  if (error && !data) {
    return (
      <section className="card system-health">
        <div className="card__header">
          <h2 className="card__title">System</h2>
          <span className="card__badge card__badge--red">unavailable</span>
        </div>
        <p className="system-health__error">{error}</p>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="card system-health">
        <div className="card__header">
          <h2 className="card__title">System</h2>
        </div>
        <div className="system-health__loading">Loading…</div>
      </section>
    );
  }

  const { cpu, memory, temperature, storage, network, system, application } = data;
  const tempC = temperature?.cpu_c;
  const threshold = temperature?.warning_threshold_c ?? 70;
  const tempStatus = tempC == null ? null : tempC >= threshold ? "warning" : "ok";
  const internetConnected = network?.internet_connected;
  const internetStatus = internetConnected === true ? "ok" : internetConnected === false ? "problem" : null;

  return (
    <section className="card system-health">
      <div className="card__header">
        <h2 className="card__title">System</h2>
        <span className="card__badge card__badge--green">Master</span>
      </div>

      <div className="system-health__sections">
        <SectionCard title="CPU">
          <InfoRow label="Model" value={cpu?.model} />
          <InfoRow label="Frequency" value={cpu?.frequency_ghz != null ? `${cpu.frequency_ghz} GHz` : null} />
          <InfoRow label="Load (1m / 5m)" value={cpu?.load_1m != null && cpu?.load_5m != null ? `${cpu.load_1m.toFixed(2)} / ${cpu.load_5m.toFixed(2)}` : null} />
        </SectionCard>

        <SectionCard title="Memory">
          <InfoRow
            label="Total / Used / Free"
            value={
              memory?.total_mb != null && memory?.used_mb != null && memory?.free_mb != null
                ? `${memory.total_mb} / ${memory.used_mb} / ${memory.free_mb} MB`
                : null
            }
          />
        </SectionCard>

        <SectionCard
          title="Temperature"
          badge={tempStatus === "warning" ? "Hot" : tempStatus === "ok" ? "OK" : null}
          badgeStatus={tempStatus === "warning" ? "orange" : "green"}
        >
          <InfoRow
            label="CPU"
            value={tempC != null ? `${tempC} °C` : null}
            status={tempStatus}
          />
          {tempStatus === "warning" && (
            <p className="system-info__warning">Above safe threshold ({threshold} °C). Ensure cooling.</p>
          )}
        </SectionCard>

        <SectionCard title="Storage">
          <InfoRow
            label="Total / Used / Free"
            value={
              storage?.total_gb != null && storage?.used_gb != null && storage?.free_gb != null
                ? `${storage.total_gb} / ${storage.used_gb} / ${storage.free_gb} GB`
                : null
            }
          />
        </SectionCard>

        <SectionCard
          title="Network"
          badge={internetStatus === "ok" ? "Online" : internetStatus === "problem" ? "Offline" : null}
          badgeStatus={internetStatus === "ok" ? "green" : "red"}
        >
          <InfoRow label="Interface" value={network?.interface_type ? `${network.interface} (${network.interface_type})` : network?.interface} />
          <InfoRow label="IP address" value={network?.ip_address} />
          {network?.interface_type === "wifi" && (
            <>
              <InfoRow label="Wi‑Fi SSID" value={network?.wifi_ssid} />
              <InfoRow label="Signal" value={network?.wifi_signal != null ? `${network.wifi_signal}%` : null} />
            </>
          )}
          <InfoRow label="Internet" value={internetConnected === true ? "Connected" : internetConnected === false ? "No connectivity" : "—"} status={internetStatus} />
        </SectionCard>

        <SectionCard title="System">
          <InfoRow label="OS" value={system?.os_version} />
          <InfoRow label="Uptime" value={system?.uptime_seconds != null ? formatUptime(system.uptime_seconds) : null} />
          <InfoRow label="Hostname" value={system?.hostname} />
        </SectionCard>

        <SectionCard title="Application">
          <InfoRow label="SoundMaker version" value={application?.soundmaker_version} />
          <InfoRow
            label="Last update"
            value={
              application?.last_update_at
                ? new Date(application.last_update_at).toLocaleString()
                : "—"
            }
          />
        </SectionCard>
      </div>
    </section>
  );
}
