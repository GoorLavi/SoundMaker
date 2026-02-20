import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "../api";
import "./UpdatesCard.css";

const PROGRESS_POLL_MS = 800;

export default function UpdatesCard() {
  const [status, setStatus] = useState(null);
  const [checkResult, setCheckResult] = useState(null);
  const [checking, setChecking] = useState(false);
  const [applying, setApplying] = useState(false);
  const [progress, setProgress] = useState({ status: "idle", log: [], message: null });
  const progressIntervalRef = useRef(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await apiFetch("/api/updates/status");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setStatus(data);
    } catch {
      setStatus({ current_version: "—", last_updated_at: null });
    }
  }, []);

  const fetchProgress = useCallback(async () => {
    try {
      const res = await apiFetch("/api/updates/progress");
      if (!res.ok) return;
      const data = await res.json();
      setProgress({ status: data.status, log: data.log || [], message: data.message });
      if (data.status !== "running") {
        if (progressIntervalRef.current) {
          clearInterval(progressIntervalRef.current);
          progressIntervalRef.current = null;
        }
        setApplying(false);
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    return () => {
      if (progressIntervalRef.current) clearInterval(progressIntervalRef.current);
    };
  }, []);

  const handleCheck = async () => {
    setChecking(true);
    setCheckResult(null);
    try {
      const res = await apiFetch("/api/updates/check", { method: "POST" });
      const data = await res.json();
      setCheckResult(data);
    } catch {
      setCheckResult({ update_available: false, error: "Request failed" });
    } finally {
      setChecking(false);
    }
  };

  const handleApply = async () => {
    setApplying(true);
    setProgress({ status: "running", log: [], message: null });
    try {
      const res = await apiFetch("/api/updates/apply", { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        setProgress((p) => ({ ...p, status: "failure", message: data.error || "Apply failed" }));
        setApplying(false);
        return;
      }
      progressIntervalRef.current = setInterval(fetchProgress, PROGRESS_POLL_MS);
      fetchProgress();
    } catch {
      setProgress((p) => ({ ...p, status: "failure", message: "Request failed" }));
      setApplying(false);
    }
  };

  const updateAvailable = checkResult?.update_available === true;
  const showProgress = applying || progress.log.length > 0;
  const isRunning = progress.status === "running";

  return (
    <section className="card updates">
      <div className="card__header">
        <h2 className="card__title">Updates</h2>
        {checkResult && !checkResult.error && (
          <span
            className={`card__badge ${
              updateAvailable ? "card__badge--orange" : "card__badge--green"
            }`}
          >
            {updateAvailable ? "update available" : "up to date"}
          </span>
        )}
      </div>

      <div className="updates__info">
        <div className="updates__info-row">
          <span className="updates__label">Current version</span>
          <span className="updates__value">{status?.current_version ?? "—"}</span>
        </div>
        <div className="updates__info-row">
          <span className="updates__label">Last update</span>
          <span className="updates__value">
            {status?.last_updated_at
              ? new Date(status.last_updated_at).toLocaleString()
              : "—"}
          </span>
        </div>
      </div>

      <div className="updates__actions">
        <button
          className="updates__btn updates__btn--secondary"
          onClick={handleCheck}
          disabled={checking || isRunning}
        >
          {checking ? "Checking…" : "Check for updates"}
        </button>
        <button
          className="updates__btn updates__btn--primary"
          onClick={handleApply}
          disabled={!updateAvailable || applying || isRunning}
        >
          {applying ? "Applying…" : "Apply update"}
        </button>
      </div>

      {checkResult?.error && (
        <p className="updates__error">Check failed: {checkResult.error}</p>
      )}

      {showProgress && (
        <div className="updates__progress">
          <pre className="updates__log">
            {progress.log.length > 0 ? progress.log.join("\n") : "Waiting…"}
          </pre>
          {progress.status === "success" && (
            <p className="updates__result updates__result--success">{progress.message}</p>
          )}
          {progress.status === "failure" && (
            <p className="updates__result updates__result--failure">{progress.message}</p>
          )}
        </div>
      )}
    </section>
  );
}
