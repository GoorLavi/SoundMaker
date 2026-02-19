import { useState } from "react";
import "./LoginScreen.css";

export default function LoginScreen({ onLogin }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!password || loading) return;

    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });

      if (res.status === 429) {
        setError("Too many attempts. Try again later.");
        return;
      }

      if (!res.ok) {
        setError("Invalid password");
        return;
      }

      onLogin();
    } catch {
      setError("Cannot reach server");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login">
      <form className="login__card" onSubmit={handleSubmit}>
        <h1 className="login__title">SoundMaker</h1>
        <p className="login__subtitle">Enter your password to continue</p>

        <input
          className="login__input"
          type="password"
          placeholder="Password"
          autoFocus
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={loading}
        />

        {error && <p className="login__error">{error}</p>}

        <button className="login__button" type="submit" disabled={loading || !password}>
          {loading ? "Logging in…" : "Log In"}
        </button>
      </form>
    </div>
  );
}
