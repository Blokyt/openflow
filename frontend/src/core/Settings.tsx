import { useEffect, useState } from "react";
import { api } from "../api";
import { AppConfig, ModuleManifest } from "../types";

const CORE_MODULE_IDS = ["transactions", "categories", "dashboard"];

interface DisplayModule {
  id: string;
  name: string;
  description?: string;
  active: boolean;
  core: boolean;
  icon?: string;
  route?: string;
}

export default function Settings() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [modules, setModules] = useState<DisplayModule[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.getConfig(), api.getAllModules()])
      .then(([cfg, discoveredMods]: [AppConfig, ModuleManifest[]]) => {
        setConfig(cfg);
        const manifestMap = new Map(discoveredMods.map((m: ModuleManifest) => [m.id, m]));
        const allModules: DisplayModule[] = Object.entries(cfg.modules).map(([id, active]) => {
          const manifest = manifestMap.get(id);
          return {
            id,
            name: manifest?.name ?? id,
            description: manifest?.description,
            active: active as boolean,
            core: manifest?.core ?? CORE_MODULE_IDS.includes(id),
            icon: manifest?.icon,
            route: manifest?.route,
          };
        });
        setModules(allModules);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  async function handleToggle(mod: DisplayModule) {
    if (CORE_MODULE_IDS.includes(mod.id)) return;
    setToggling(mod.id);
    try {
      await api.toggleModule(mod.id, !mod.active);
      setModules((prev) =>
        prev.map((m) => (m.id === mod.id ? { ...m, active: !m.active } : m))
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setToggling(null);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#F2C48D]" />
      </div>
    );
  }

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-3xl font-bold text-white mb-8" style={{ letterSpacing: "-0.02em" }}>
        Paramètres
      </h1>

      {error && (
        <div className="mb-4 bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-2xl p-4 text-sm">
          {error}
        </div>
      )}

      {config && (
        <section className="mb-8">
          <h2 className="text-base font-semibold text-white mb-3">Entité</h2>
          <div className="bg-[#111] border border-[#222] rounded-2xl p-5 space-y-4">
            <div className="flex justify-between text-sm">
              <span className="text-[#666]">Nom</span>
              <span className="font-medium text-white">{config.entity.name}</span>
            </div>
            <div className="flex justify-between text-sm border-t border-[#1a1a1a] pt-4">
              <span className="text-[#666]">Devise</span>
              <span className="font-medium text-white">{config.entity.currency}</span>
            </div>
            {config.balance.date && (
              <div className="flex justify-between text-sm border-t border-[#1a1a1a] pt-4">
                <span className="text-[#666]">Date de référence</span>
                <span className="font-medium text-white">{config.balance.date}</span>
              </div>
            )}
            {config.balance.amount !== undefined && (
              <div className="flex justify-between text-sm border-t border-[#1a1a1a] pt-4">
                <span className="text-[#666]">Solde de référence</span>
                <span className="font-medium text-[#F2C48D]">
                  {new Intl.NumberFormat("fr-FR", { style: "currency", currency: config.entity.currency || "EUR" }).format(
                    config.balance.amount
                  )}
                </span>
              </div>
            )}
          </div>
        </section>
      )}

      <section>
        <h2 className="text-base font-semibold text-white mb-3">Modules</h2>
        <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
          {modules.map((mod, idx) => {
            const isCore = CORE_MODULE_IDS.includes(mod.id);
            return (
              <div
                key={mod.id}
                className={`flex items-center justify-between px-5 py-4 ${
                  idx > 0 ? "border-t border-[#1a1a1a]" : ""
                }`}
              >
                <div>
                  <p className="text-sm font-medium text-white">{mod.name}</p>
                  {mod.description && (
                    <p className="text-xs text-[#B0B0B0] mt-0.5">{mod.description}</p>
                  )}
                  {isCore && (
                    <span className="inline-block mt-1.5 text-xs bg-[#1a1a1a] border border-[#222] text-[#666] px-2 py-0.5 rounded-full">
                      Module principal
                    </span>
                  )}
                </div>
                <button
                  onClick={() => handleToggle(mod)}
                  disabled={isCore || toggling === mod.id}
                  className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none ${
                    mod.active ? "bg-[#F2C48D]" : "bg-[#333]"
                  } ${isCore ? "opacity-30 cursor-not-allowed" : ""}`}
                  aria-label={`Toggle ${mod.name}`}
                >
                  <span
                    className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform duration-200 ${
                      mod.active ? "translate-x-5" : "translate-x-0"
                    }`}
                  />
                </button>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
