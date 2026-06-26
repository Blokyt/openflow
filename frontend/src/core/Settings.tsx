import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { AppConfig, ModuleManifest } from "../types";
import { Pencil, Check, X, Info, MapPin, ArrowRight } from "lucide-react";
import { MODULE_ROUTES, INTEGRATED_LOCATIONS } from "../routes";
import { formatEuros, eurosToCents, centsToEuros } from "../utils/format";
import BalanceRefsSection from "./BalanceRefsSection";

// Category labels — modules are classified dynamically via manifest.category.
const CATEGORY_LABELS: Record<string, string> = {
  core: "Noyau",
  standard: "Standard",
  advanced: "Avancé",
  custom: "Personnalisé",
};
const CATEGORY_ORDER = ["core", "standard", "advanced", "custom"];

const ENTITY_TYPES = ["association", "entreprise", "auto-entrepreneur", "autre"];
const CURRENCIES = ["EUR", "USD", "GBP", "CHF", "CAD"];

interface DisplayModule {
  id: string;
  name: string;
  description?: string;
  help?: string;
  example?: string;
  category: string;
  menuLabel?: string;
  active: boolean;
  core: boolean;
}

function EditableField({
  label,
  value,
  displayValue,
  onSave,
  type = "text",
  options,
}: {
  label: string;
  value: string;
  displayValue?: string;
  onSave: (val: string) => Promise<void>;
  type?: "text" | "date" | "number" | "select";
  options?: string[];
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    try {
      await onSave(draft);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  function handleCancel() {
    setDraft(value);
    setEditing(false);
  }

  if (editing) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-[#666] text-sm w-40 flex-shrink-0">{label}</span>
        {type === "select" && options ? (
          <select
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="flex-1 bg-[#0a0a0a] border border-[#F2C48D] rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none"
          >
            {options.map((o) => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>
        ) : (
          <input
            type={type}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="flex-1 bg-[#0a0a0a] border border-[#F2C48D] rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSave();
              if (e.key === "Escape") handleCancel();
            }}
          />
        )}
        <button onClick={handleSave} disabled={saving} className="text-[#00C853] hover:text-white p-1">
          <Check size={16} />
        </button>
        <button onClick={handleCancel} className="text-[#FF5252] hover:text-white p-1">
          <X size={16} />
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between group">
      <span className="text-[#666] text-sm">{label}</span>
      <div className="flex items-center gap-2">
        <span className="font-medium text-white text-sm">{displayValue ?? (value || "—")}</span>
        <button
          onClick={() => setEditing(true)}
          className="opacity-0 group-hover:opacity-100 text-[#666] hover:text-[#F2C48D] transition-opacity p-1"
        >
          <Pencil size={14} />
        </button>
      </div>
    </div>
  );
}

export default function Settings() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [modules, setModules] = useState<DisplayModule[]>([]);
  const [coreModuleIds, setCoreModuleIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);
  const [expandedHelp, setExpandedHelp] = useState<string | null>(null);
  const [showCoreModules, setShowCoreModules] = useState(false);
  const [rootEntityId, setRootEntityId] = useState<number | null>(null);
  const [balanceRef, setBalanceRef] = useState<{ date: string; amount: number }>({ date: "2025-01-01", amount: 0 });

  async function reload() {
    const [cfg, discoveredMods, entities] = await Promise.all([
      api.getConfig(),
      api.getAllModules(),
      api.getEntities("internal").catch(() => []),
    ]);
    setConfig(cfg);

    // Find root entity (is_default=1 or parent_id=null)
    const root = entities.find((e: any) => e.is_default === 1) || entities.find((e: any) => !e.parent_id);
    // Solde legacy : config.balance.amount est en euros, on normalise en centimes.
    const cfgRef = { date: cfg.balance.date || "2025-01-01", amount: eurosToCents(String(cfg.balance.amount ?? 0)) };
    if (root) {
      setRootEntityId(root.id);
      try {
        const ref = await api.getBalanceRef(root.id);
        // reference_amount est deja en centimes (table entity_balance_refs)
        setBalanceRef({ date: ref.reference_date || "2025-01-01", amount: ref.reference_amount ?? 0 });
      } catch {
        setBalanceRef(cfgRef);
      }
    } else {
      setBalanceRef(cfgRef);
    }

    const manifestMap = new Map(discoveredMods.map((m: ModuleManifest) => [m.id, m]));
    const coreIds = new Set(
      discoveredMods.filter((m: ModuleManifest) => (m as any).category === "core").map((m: ModuleManifest) => m.id)
    );
    setCoreModuleIds(coreIds);
    const allModules: DisplayModule[] = Object.entries(cfg.modules).map(([id, active]) => {
      const manifest = manifestMap.get(id);
      return {
        id,
        name: manifest?.name ?? id,
        description: manifest?.description,
        help: manifest?.help,
        example: (manifest as any)?.example,
        menuLabel: (manifest as any)?.menu?.label,
        category: (manifest as any)?.category ?? "custom",
        active: active as boolean,
        core: (manifest as any)?.category === "core",
      };
    });
    setModules(allModules);
  }

  useEffect(() => {
    reload().catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, []);

  async function handleToggle(mod: DisplayModule) {
    if (coreModuleIds.has(mod.id)) return;
    setToggling(mod.id);
    try {
      await api.toggleModule(mod.id, !mod.active);
      // Full reload so Sidebar, routes, and module list are refreshed
      window.location.reload();
    } catch (e: any) {
      setError(e.message);
      setToggling(null);
    }
  }

  async function updateEntity(field: string, value: string) {
    await api.updateEntity({ [field]: value });
    await reload();
  }

  async function updateBalanceRef(field: string, value: string) {
    if (rootEntityId) {
      const payload: any = {
        reference_date: balanceRef.date,
        reference_amount: balanceRef.amount, // deja en centimes
      };
      // value est saisi en euros : on reconvertit en centimes pour l'API
      if (field === "amount") payload.reference_amount = eurosToCents(value);
      if (field === "date") payload.reference_date = value;
      await api.updateBalanceRef(rootEntityId, payload);
    } else {
      // Fallback to legacy config : le config stocke des euros
      const payload: any = {};
      if (field === "amount") payload.amount = centsToEuros(eurosToCents(value));
      else payload[field] = value;
      await api.updateBalance(payload);
    }
    await reload();
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#F2C48D]" />
      </div>
    );
  }

  function renderModuleRow(mod: DisplayModule, idx: number) {
    const isCore = coreModuleIds.has(mod.id);
    const isExpanded = expandedHelp === mod.id;

    // Compute "where it appears"
    let location: string | null = null;
    if (mod.menuLabel) {
      location = `Barre latérale → ${mod.menuLabel}`;
    } else if (INTEGRATED_LOCATIONS[mod.id]) {
      location = INTEGRATED_LOCATIONS[mod.id];
    }

    // Build "see in action" link
    let actionPath: string | null = null;
    if (mod.active) {
      if (MODULE_ROUTES[mod.id]) actionPath = MODULE_ROUTES[mod.id].path;
      else if (["attachments"].includes(mod.id)) actionPath = "/transactions";
    }

    return (
      <div id={`module-${mod.id}`} key={mod.id} className={idx > 0 ? "border-t border-[#1a1a1a]" : ""}>
        <div className="px-5 py-4 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <p className="text-sm font-medium text-white">{mod.name}</p>
              {mod.active && <span className="w-1.5 h-1.5 rounded-full bg-[#00C853]" />}
              {mod.help && (
                <button
                  onClick={() => setExpandedHelp(isExpanded ? null : mod.id)}
                  className="text-[#666] hover:text-[#F2C48D] p-0.5"
                  aria-label={`Aide pour ${mod.name}`}
                >
                  <Info size={14} />
                </button>
              )}
            </div>
            {isCore ? (
              <span className="text-xs text-[#666] bg-[#1a1a1a] border border-[#222] px-2.5 py-1 rounded-full">
                Toujours actif
              </span>
            ) : (
              <button
                onClick={() => handleToggle(mod)}
                disabled={toggling === mod.id}
                className={`relative inline-flex h-6 w-11 flex-shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 ${
                  mod.active ? "bg-[#F2C48D]" : "bg-[#333]"
                }`}
              >
                <span className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform ${
                  mod.active ? "translate-x-5" : "translate-x-0"
                }`} />
              </button>
            )}
          </div>

          {location && (
            <div className="flex items-center gap-1.5 text-xs text-[#B0B0B0]">
              <MapPin size={11} className="text-[#666]" />
              <span>{location}</span>
            </div>
          )}

          {mod.description && (
            <p className="text-xs text-[#B0B0B0] leading-relaxed">{mod.description}</p>
          )}

          {mod.example && (
            <p className="text-xs text-[#666] italic leading-relaxed">
              Exemple : {mod.example}
            </p>
          )}

          {actionPath && (
            <Link to={actionPath} className="inline-flex items-center gap-1 text-xs text-[#F2C48D] hover:underline">
              Voir en action <ArrowRight size={11} />
            </Link>
          )}
        </div>

        {isExpanded && mod.help && (
          <div className="px-5 pb-4 -mt-1">
            <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl px-4 py-3">
              <p className="text-xs text-[#999] leading-relaxed">{mod.help}</p>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="p-8 max-w-5xl">
      <h1 className="text-3xl font-bold text-white mb-8" style={{ letterSpacing: "-0.02em" }}>
        Paramètres
      </h1>

      {error && (
        <div className="mb-4 bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-2xl p-4 text-sm flex justify-between items-center">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-xs underline ml-2">Fermer</button>
        </div>
      )}

      {config && (
        <section className="mb-8">
          <h2 className="text-base font-semibold text-white mb-3">Entité</h2>
          <div className="bg-[#111] border border-[#222] rounded-2xl p-5 space-y-4">
            <EditableField
              label="Nom"
              value={config.entity.name}
              onSave={(v) => updateEntity("name", v)}
            />
            <div className="border-t border-[#1a1a1a] pt-4">
              <EditableField
                label="Type"
                value={config.entity.type}
                onSave={(v) => updateEntity("type", v)}
                type="select"
                options={ENTITY_TYPES}
              />
            </div>
            <div className="border-t border-[#1a1a1a] pt-4">
              <EditableField
                label="Devise"
                value={config.entity.currency}
                onSave={(v) => updateEntity("currency", v)}
                type="select"
                options={CURRENCIES}
              />
            </div>
            <div className="border-t border-[#1a1a1a] pt-4">
              <EditableField
                label="Date de référence"
                value={balanceRef.date}
                onSave={(v) => updateBalanceRef("date", v)}
                type="date"
              />
            </div>
            <div className="border-t border-[#1a1a1a] pt-4">
              <EditableField
                label="Solde de référence"
                value={String(centsToEuros(balanceRef.amount))}
                displayValue={formatEuros(balanceRef.amount)}
                onSave={(v) => updateBalanceRef("amount", v)}
                type="number"
              />
            </div>
          </div>
        </section>
      )}

      <BalanceRefsSection />

      <section className="space-y-6">
        <h2 className="text-base font-semibold text-white">Modules</h2>
        <p className="text-xs text-[#666] -mt-4">
          Active un module pour le voir apparaître dans la barre latérale à gauche.
          Chaque module activé = un onglet fonctionnel.
        </p>

        {CATEGORY_ORDER.map((catKey) => {
          const catModules = modules.filter((m) => m.category === catKey);
          if (catModules.length === 0) return null;
          const activeCount = catModules.filter((m) => m.active).length;
          const label = CATEGORY_LABELS[catKey] ?? catKey;
          const isCoreGroup = catKey === "core";
          const collapsed = isCoreGroup && !showCoreModules;
          return (
            <div key={catKey}>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-[#666]">{label}</h3>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-[#666]">{activeCount}/{catModules.length} actifs</span>
                  {isCoreGroup && (
                    <button
                      onClick={() => setShowCoreModules((v) => !v)}
                      className="text-xs text-[#F2C48D] hover:underline"
                    >
                      {collapsed ? "Afficher" : "Masquer"}
                    </button>
                  )}
                </div>
              </div>
              {!collapsed && (
                <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
                  {catModules.map((mod, idx) => renderModuleRow(mod, idx))}
                </div>
              )}
            </div>
          );
        })}

        {(() => {
          const known = new Set(CATEGORY_ORDER);
          const orphans = modules.filter((m) => !known.has(m.category));
          if (orphans.length === 0) return null;
          return (
            <div>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-[#666]">Autre</h3>
                <span className="text-xs text-[#666]">
                  {orphans.filter((m) => m.active).length}/{orphans.length} actifs
                </span>
              </div>
              <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
                {orphans.map((mod, idx) => renderModuleRow(mod, idx))}
              </div>
            </div>
          );
        })()}
      </section>
    </div>
  );
}
