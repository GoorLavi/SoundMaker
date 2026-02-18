import PiholeCard from "./components/PiholeCard";
import "./App.css";

export default function App() {
  return (
    <div className="app">
      <header className="header">
        <h1 className="header__title">SoundMaker</h1>
      </header>
      <main className="dashboard">
        <PiholeCard />
      </main>
    </div>
  );
}
