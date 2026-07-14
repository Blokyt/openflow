import { useState } from "react";
import { Link } from "react-router-dom";
import { Rocket, X, ArrowRight } from "lucide-react";

const DISMISS_KEY = "openflow.onboardingDismissed";

const STEPS = [
  {
    n: 1,
    to: "/entities",
    title: "Crée tes entités",
    desc: "Tes comptes internes (BDA, clubs) et tes tiers externes (banque, fournisseurs).",
  },
  {
    n: 2,
    to: "/settings",
    title: "Renseigne ton solde de référence",
    desc: "Le point de départ à partir duquel le solde se calcule automatiquement.",
  },
  {
    n: 3,
    to: "/transactions",
    title: "Saisis ta première transaction",
    desc: "Une recette ou une dépense : le solde se met à jour tout seul.",
  },
];

/** Guide de démarrage affiché sur le dashboard tant qu'aucune transaction n'existe. */
export default function OnboardingChecklist() {
  const [dismissed, setDismissed] = useState(localStorage.getItem(DISMISS_KEY) === "true");
  if (dismissed) return null;

  return (
    <div className="bg-gradient-to-br from-[#F2C48D]/10 to-transparent border border-accent-sand/20 rounded-2xl p-5 relative">
      <button
        onClick={() => {
          localStorage.setItem(DISMISS_KEY, "true");
          setDismissed(true);
        }}
        className="absolute top-3 right-3 text-[#8a8a8a] hover:text-white p-1"
        aria-label="Fermer"
      >
        <X size={14} />
      </button>
      <div className="flex items-start gap-3">
        <Rocket size={18} className="text-accent-sand mt-0.5 flex-shrink-0" />
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-white mb-1">Bienvenue sur OpenFlow</h3>
          <p className="text-xs text-text-secondary mb-3">Trois étapes pour démarrer ta comptabilité :</p>
          <div className="space-y-1.5">
            {STEPS.map((s) => (
              <Link
                key={s.n}
                to={s.to}
                className="flex items-center gap-3 group rounded-xl px-2 py-1.5 -mx-2 hover:bg-accent-sand/5 transition-colors"
              >
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-accent-sand/15 text-accent-sand text-xs font-bold flex items-center justify-center">
                  {s.n}
                </span>
                <span className="flex-1 min-w-0">
                  <span className="text-sm text-white font-medium group-hover:text-accent-sand transition-colors">
                    {s.title}
                  </span>
                  <span className="block text-xs text-[#888]">{s.desc}</span>
                </span>
                <ArrowRight size={13} className="text-[#8a8a8a] group-hover:text-accent-sand flex-shrink-0" />
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
