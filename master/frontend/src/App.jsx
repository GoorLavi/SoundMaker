import { useCallback, useEffect, useState } from "react";
import { setOnAuthLost } from "./api";
import PiholeCard from "./components/PiholeCard";
import UpdatesCard from "./components/UpdatesCard";
import LoginScreen from "./components/LoginScreen";
import "./App.css";

export default function App() {
  const [authState, setAuthState] = useState("loading"); // "loading" | "authenticated" | "unauthenticated"

  const handleLogout = useCallback(async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch { /* ignore */ }
    setAuthState("unauthenticated");
  }, []);

  useEffect(() => {
    setOnAuthLost(() => setAuthState("unauthenticated"));

    fetch("/api/auth/check")
      .then((res) => res.json())
      .then((data) => setAuthState(data.authenticated ? "authenticated" : "unauthenticated"))
      .catch(() => setAuthState("unauthenticated"));
  }, []);

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
      <main className="dashboard">
        <PiholeCard />
        <UpdatesCard />
      </main>
    </div>
  );
}
