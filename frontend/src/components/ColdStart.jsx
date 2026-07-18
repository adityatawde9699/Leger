import React from "react";
import { Loader2 } from "lucide-react";

// Shown when a request has been pending long enough that the Render free-tier
// backend is probably waking from sleep. Listens to the api:waking/api:awake
// events dispatched by apiFetch in lib.js.
export default function ColdStart() {
  const [waking, setWaking] = React.useState(false);
  const [elapsed, setElapsed] = React.useState(0);

  React.useEffect(() => {
    const onWaking = () => { setWaking(true); setElapsed(0); };
    const onAwake = () => setWaking(false);
    window.addEventListener("api:waking", onWaking);
    window.addEventListener("api:awake", onAwake);
    return () => {
      window.removeEventListener("api:waking", onWaking);
      window.removeEventListener("api:awake", onAwake);
    };
  }, []);

  React.useEffect(() => {
    if (!waking) return;
    const t = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [waking]);

  if (!waking) return null;

  return (
    <div className="coldstart-banner" role="status" aria-live="polite">
      <Loader2 size={16} className="spin" aria-hidden="true" />
      <span>
        Waking up the server — this usually takes under a minute
        {elapsed >= 5 ? ` (${elapsed}s)` : ""}
      </span>
    </div>
  );
}
