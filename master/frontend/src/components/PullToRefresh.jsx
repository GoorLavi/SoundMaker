import { useEffect, useRef, useState } from "react";
import "./PullToRefresh.css";

// Distance (after resistance) the finger must pull before release reloads.
const THRESHOLD = 70;
// Cap on indicator travel so the circle never chases the finger off-screen.
const MAX_PULL = 110;
// Finger movement is halved so the gesture feels weighty, like native PTR.
const RESISTANCE = 0.5;
// Ignore the first few px so taps and tiny jitters never show the indicator.
const DEAD_ZONE = 10;

/**
 * Custom pull-to-refresh for the installed home-screen web app.
 *
 * In standalone mode (iOS "Add to Home Screen") there is no browser chrome:
 * no reload button and no native pull-to-refresh, so a stale page can only
 * be fixed by killing the app. This component restores the familiar gesture:
 * pull down from the top of the page and release to reload.
 *
 * Mounted once (in main.jsx) so it works on every screen — login, dashboard
 * and the guest page alike. Listeners live on `document`; touchmove is
 * registered non-passive so preventDefault() can stop iOS rubber-banding
 * from fighting the indicator while pulling.
 */
export default function PullToRefresh() {
  const [pull, setPull] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  // Gesture state lives in a ref: touch handlers are bound once and must not
  // read stale closure state.
  const gesture = useRef({ startY: null, pull: 0, pulling: false, refreshing: false });

  useEffect(() => {
    const g = gesture.current;

    // True when the touch began inside an element scrolled away from its own
    // top (e.g. the log viewer) — pulling down there should scroll that
    // element back up, not refresh the page.
    const insideScrolledElement = (node) => {
      for (let el = node; el && el !== document.documentElement; el = el.parentElement) {
        if (el.scrollTop > 0) return true;
      }
      return false;
    };

    const reset = () => {
      g.startY = null;
      g.pulling = false;
      g.pull = 0;
      setPull(0);
      setDragging(false);
    };

    const onTouchStart = (e) => {
      if (g.refreshing || e.touches.length !== 1) return;
      if (window.scrollY > 0 || insideScrolledElement(e.target)) return;
      g.startY = e.touches[0].clientY;
      g.pulling = false;
    };

    const onTouchMove = (e) => {
      if (g.refreshing || g.startY === null) return;
      const dy = e.touches[0].clientY - g.startY;
      if (!g.pulling) {
        // The gesture became a normal scroll — stop tracking it.
        if (dy < 0 || window.scrollY > 0) {
          g.startY = null;
          return;
        }
        if (dy < DEAD_ZONE) return;
        g.pulling = true;
        setDragging(true);
      }
      if (e.cancelable) e.preventDefault();
      g.pull = Math.min((dy - DEAD_ZONE) * RESISTANCE, MAX_PULL);
      setPull(g.pull);
    };

    const onTouchEnd = () => {
      if (g.refreshing || g.startY === null) return;
      if (g.pulling && g.pull >= THRESHOLD) {
        g.refreshing = true;
        setRefreshing(true);
        setDragging(false);
        setPull(THRESHOLD);
        window.location.reload();
      } else {
        reset();
      }
    };

    document.addEventListener("touchstart", onTouchStart, { passive: true });
    document.addEventListener("touchmove", onTouchMove, { passive: false });
    document.addEventListener("touchend", onTouchEnd, { passive: true });
    document.addEventListener("touchcancel", onTouchEnd, { passive: true });
    return () => {
      document.removeEventListener("touchstart", onTouchStart);
      document.removeEventListener("touchmove", onTouchMove);
      document.removeEventListener("touchend", onTouchEnd);
      document.removeEventListener("touchcancel", onTouchEnd);
    };
  }, []);

  const visible = refreshing || pull > 0;
  const ready = refreshing || pull >= THRESHOLD;

  return (
    <div
      className={[
        "ptr",
        dragging ? "ptr--dragging" : "",
        ready ? "ptr--ready" : "",
        refreshing ? "ptr--refreshing" : "",
      ].join(" ")}
      style={{
        transform: `translateX(-50%) translateY(${visible ? pull : 0}px)`,
        opacity: visible ? 1 : 0,
      }}
      aria-hidden="true"
    >
      <svg
        className="ptr__icon"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={refreshing ? undefined : { transform: `rotate(${pull * 2.2}deg)` }}
      >
        <polyline points="23 4 23 10 17 10" />
        <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
      </svg>
    </div>
  );
}
