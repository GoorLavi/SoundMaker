import { useCallback, useEffect, useState } from "react";
import { setOnAuthLost } from "./api";
import AlarmCard from "./components/AlarmCard";
import JellyfinCard from "./components/JellyfinCard";
import PiholeCard from "./components/PiholeCard";
import GuestCard from "./components/GuestCard";
import GuestPage from "./components/GuestPage";
import SystemHealthCard from "./components/SystemHealthCard";
import MetricsHistoryCard from "./components/MetricsHistoryCard";
import LogsCard from "./components/LogsCard";
import PowerCard from "./components/PowerCard";
import TailscaleCard from "./components/TailscaleCard";
import UpdatesCard from "./components/UpdatesCard";
import LoginScreen from "./components/LoginScreen";
import "./App.css";

const TAB_DASHBOARD = "dashboard";
const TAB_SYSTEM = "system";

export default function App() {
  const [authState, setAuthState] = useState("loading"); // "loading" | "authenticated" | "unauthenticated"
  const [activeTab, setActiveTab] = useState(TAB_DASHBOARD);

  // Public guest landing page — rendered without any auth gate.
  const isGuestPage = window.location.pathname === "/guest";

  const handleLogout = useCallback(async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch { /* ignore */ }
    setAuthState("unauthenticated");
  }, []);

  useEffect(() => {
    if (isGuestPage) return;
    setOnAuthLost(() => setAuthState("unauthenticated"));

    fetch("/api/auth/check")
      .then((res) => res.json())
      .then((data) => setAuthState(data.authenticated ? "authenticated" : "unauthenticated"))
      .catch(() => setAuthState("unauthenticated"));
  }, [isGuestPage]);

  if (isGuestPage) return <GuestPage />;

  if (authState === "loading") return null;

  if (authState === "unauthenticated") {
    return <LoginScreen onLogin={() => setAuthState("authenticated")} />;
  }

  return (
    <div className="app">
      <header className="header">
        <h1 className="header__title">SoundMaker</h1>
        <button className="header__logout" onClick={handleLogout}>
          Log out
        </button>
      </header>
      <nav className="tabs" role="tablist" aria-label="Main sections">
        <button
          role="tab"
          aria-selected={activeTab === TAB_DASHBOARD}
          className={`tabs__tab ${activeTab === TAB_DASHBOARD ? "tabs__tab--active" : ""}`}
          onClick={() => setActiveTab(TAB_DASHBOARD)}
        >
          Dashboard
        </button>
        <button
          role="tab"
          aria-selected={activeTab === TAB_SYSTEM}
          className={`tabs__tab ${activeTab === TAB_SYSTEM ? "tabs__tab--active" : ""}`}
          onClick={() => setActiveTab(TAB_SYSTEM)}
        >
          System
        </button>
      </nav>
      <main className="dashboard">
        {activeTab === TAB_DASHBOARD && (
          <>
            <AlarmCard />
            <JellyfinCard />
            <PiholeCard />
            <GuestCard />
          </>
        )}
        {activeTab === TAB_SYSTEM && (
          <>
            <SystemHealthCard />
            <MetricsHistoryCard />
            <LogsCard />
            <PowerCard />
            <TailscaleCard />
            <UpdatesCard />
          </>
        )}
      </main>
    </div>
  );
}
