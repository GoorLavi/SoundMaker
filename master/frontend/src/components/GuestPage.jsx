import { useCallback, useEffect, useState } from "react";
import QRCode from "qrcode";
import "./GuestPage.css";

/**
 * Public guest landing page, served at /guest — no login required.
 * Shows a scannable Wi-Fi QR code plus the network details in plain text.
 */

// Wi-Fi QR payload per the de-facto WIFI: URI scheme. Backslash-escape the
// special characters (\ ; , : ") so SSIDs/passwords containing them scan
// correctly.
function escapeWifiValue(value) {
  return value.replace(/([\\;,:"])/g, "\\$1");
}

function buildWifiPayload({ ssid, password, security, hidden }) {
  const parts = [`WIFI:T:${security === "nopass" ? "nopass" : security}`, `S:${escapeWifiValue(ssid)}`];
  if (security !== "nopass" && password) {
    parts.push(`P:${escapeWifiValue(password)}`);
  }
  if (hidden) {
    parts.push("H:true");
  }
  return `${parts.join(";")};;`;
}

export default function GuestPage() {
  const [page, setPage] = useState(null);
  const [error, setError] = useState(null);
  const [qrDataUrl, setQrDataUrl] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    fetch("/api/guest/page")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(setPage)
      .catch(() => setError("Cannot reach the server"));
  }, []);

  useEffect(() => {
    if (!page?.enabled) return;
    QRCode.toDataURL(buildWifiPayload(page), {
      width: 512,
      margin: 2,
      errorCorrectionLevel: "M",
      color: { dark: "#1a1a2e", light: "#ffffff" },
    })
      .then(setQrDataUrl)
      .catch(() => setQrDataUrl(null));
  }, [page]);

  const copyPassword = useCallback(async () => {
    if (!page?.password) return;
    try {
      await navigator.clipboard.writeText(page.password);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable (e.g. plain http) — the password is visible anyway */
    }
  }, [page]);

  if (error) {
    return (
      <div className="guest">
        <p className="guest__unavailable">{error}</p>
      </div>
    );
  }

  if (!page) return null;

  if (!page.enabled) {
    return (
      <div className="guest">
        <p className="guest__unavailable">This page is not available right now.</p>
      </div>
    );
  }

  return (
    <div className="guest">
      <header className="guest__header">
        <span className="guest__wave" role="img" aria-label="wave">
          👋
        </span>
        <h1 className="guest__title">Welcome!</h1>
        {page.welcome_message && <p className="guest__message">{page.welcome_message}</p>}
      </header>

      <section className="guest__wifi">
        <h2 className="guest__section-title">Join our Wi-Fi</h2>
        {qrDataUrl && (
          <div className="guest__qr-frame">
            <img className="guest__qr" src={qrDataUrl} alt={`QR code to join Wi-Fi network ${page.ssid}`} />
          </div>
        )}
        <p className="guest__hint">Point your phone's camera at the code to connect</p>

        <dl className="guest__details">
          <div className="guest__detail">
            <dt>Network</dt>
            <dd>{page.ssid}</dd>
          </div>
          {page.security !== "nopass" && page.password && (
            <div className="guest__detail">
              <dt>Password</dt>
              <dd>
                <button
                  className="guest__password"
                  onClick={copyPassword}
                  title="Tap to copy"
                >
                  {page.password}
                  <span className="guest__copy-hint">{copied ? "copied!" : "tap to copy"}</span>
                </button>
              </dd>
            </div>
          )}
        </dl>
      </section>

      {page.show_jellyfin && (
        <section className="guest__extra">
          <h2 className="guest__section-title">Movie night?</h2>
          <p className="guest__hint">
            Once you're connected, our media library is at{" "}
            <a href="http://master.local:8096">master.local:8096</a>
          </p>
        </section>
      )}
    </div>
  );
}
