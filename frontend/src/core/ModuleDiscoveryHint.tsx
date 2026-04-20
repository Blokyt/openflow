import { useEffect, useState } from "react";
import { Sparkles, X, ArrowRight } from "lucide-react";
import { api } from "../api";

const DISMISS_KEY = "openflow.dashboardHintDismissed";

export default function ModuleDiscoveryHint() {
  const [inactiveModules, setInactiveModules] = useState<any[]>([]);
  const [dismissed, setDismissed] = useState(localStorage.getItem(DISMISS_KEY) === "true");

  useEffect(() => {
    if (dismissed) return;
    Promise.all([api.getAllModules(), api.getConfig()])
      .then(([mods, cfg]) => {
        const inactive = mods.filter(
          (m: any) =>
            m.menu &&                       // Would show in sidebar if active
            m.category !== "core" &&        // Don't push core modules
            !cfg.modules[m.id]              // Currently off
        );
        setInactiveModules(inactive);
      })
      .catch(() => {});
  }, [dismissed]);

  function handleDismiss() {
    localStorage.setItem(DISMISS_KEY, "true");
    setDismissed(true);
  }

  if (dismissed || inactiveModules.length === 0) return null;

  return (
    <div className="bg-gradient-to-br from-[#F2C48D]/10 to-transparent border border-[#F2C48D]/20 rounded-2xl p-5 mb-6 relative">
      <button
        onClick={handleDismiss}
        className="absolute top-3 right-3 text-[#666] hover:text-white p-1"
        aria-label="Fermer"
      >
        <X size={14} />
      </button>
      <div className="flex items-start gap-3">
        <Sparkles size={18} className="text-[#F2C48D] mt-0.5 flex-shrink-0" />
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-white mb-1">Explorer les modules</h3>
          <p className="text-xs text-[#B0B0B0] mb-2">
            Tu n'as pas encore activé{" "}
            {inactiveModules.map((m, i) => (
              <span key={m.id}>
                <span className="text-white font-medium">{m.name}</span>
                {i < inactiveModules.length - 2 && ", "}
                {i === inactiveModules.length - 2 && " et "}
              </span>
            ))}
            . Va dans <a href="/settings" className="text-[#F2C48D] hover:underline inline-flex items-center gap-0.5">
              Paramètres <ArrowRight size={11} />
            </a> pour voir ce qu'ils font.
          </p>
        </div>
      </div>
    </div>
  );
}
