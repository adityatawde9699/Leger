import React from "react";
import { Download, WifiOff, X } from "lucide-react";
import { registerSW } from "virtual:pwa-register";
import { useToast } from "./ui";

let serviceWorkerStarted = false;

function isStandalone() {
  return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

function isIos() {
  return /iphone|ipad|ipod/i.test(window.navigator.userAgent);
}

export default function PWAController() {
  const toast = useToast();
  const [installPrompt, setInstallPrompt] = React.useState(null);
  const [online, setOnline] = React.useState(navigator.onLine);
  const [dismissed, setDismissed] = React.useState(() => sessionStorage.getItem("pwa-install-dismissed") === "1");

  React.useEffect(() => {
    if (!serviceWorkerStarted) {
      serviceWorkerStarted = true;
      registerSW({
        immediate: true,
        onOfflineReady() {
          toast("Ledger is ready to use offline", "success");
        },
        onRegisterError(error) {
          console.error("Service worker registration failed", error);
        },
      });
    }

    const onInstallAvailable = (event) => {
      event.preventDefault();
      setInstallPrompt(event);
    };
    const onInstalled = () => {
      setInstallPrompt(null);
      toast("Ledger was installed successfully", "success");
    };
    const onOnline = () => setOnline(true);
    const onOffline = () => setOnline(false);

    window.addEventListener("beforeinstallprompt", onInstallAvailable);
    window.addEventListener("appinstalled", onInstalled);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("beforeinstallprompt", onInstallAvailable);
      window.removeEventListener("appinstalled", onInstalled);
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, [toast]);

  async function installApp() {
    if (!installPrompt) return;
    await installPrompt.prompt();
    const choice = await installPrompt.userChoice;
    if (choice.outcome === "accepted") setInstallPrompt(null);
  }

  function dismissInstall() {
    sessionStorage.setItem("pwa-install-dismissed", "1");
    setDismissed(true);
  }

  const showInstall = installPrompt && !dismissed && !isStandalone();
  const showIosInstall = !installPrompt && isIos() && !dismissed && !isStandalone();
  if (online && !showInstall && !showIosInstall) return null;

  return (
    <div className="pwa-notices" aria-live="polite">
      {!online && (
        <div className="pwa-notice offline" role="status">
          <WifiOff size={18} />
          <div><strong>You’re offline</strong><span>Saved screens remain available. New data will need a connection.</span></div>
        </div>
      )}

      {(showInstall || showIosInstall) && (
        <div className="pwa-notice install" role="status">
          <div className="pwa-install-icon"><Download size={18} /></div>
          <div>
            <strong>Install Ledger</strong>
            <span>{showIosInstall ? "Tap Share, then Add to Home Screen." : "Open faster and use it like a native app."}</span>
          </div>
          {showInstall && <button type="button" className="pwa-install-button" onClick={installApp}>Install</button>}
          <button type="button" className="pwa-dismiss" onClick={dismissInstall} aria-label="Dismiss install suggestion"><X size={16} /></button>
        </div>
      )}
    </div>
  );
}
