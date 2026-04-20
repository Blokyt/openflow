import { useEffect, useState } from "react";
import { api } from "../api";
import { AppConfig, ModuleManifest } from "../types";
import { Pencil, Check, X, Info, FileSpreadsheet, ShieldCheck, Download } from "lucide-react";
import { useAuth } from "./AuthContext";

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
  category: string;
  active: boolean;
  core: boolean;
}

function EditableField({
  label,
  value,
  onSave,
  type = "text",
  options,
}: {
  label: string;
  value: string;
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
        <span className="font-medium text-white text-sm">{value || "—"}</span>
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

function FecExportSection() {
  const [year, setYear] = useState(String(new Date().getFullYear()));
  return (
    <section className="mb-8">
      <h2 className="text-base font-semibold text-white mb-3 flex items-center gap-2">
        <FileSpreadsheet size={16} className="text-[#F2C48D]" />
        Export FEC
      </h2>
      <div className="bg-[#111] border border-[#222] rounded-2xl p-5">
        <p className="text-xs text-[#666] mb-4">
          Génère le Fichier des Écritures Comptables (FEC) au format légal français
          pour une année fiscale. Obligatoire en cas de contrôle fiscal.
        </p>
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <label className="block text-xs text-[#666] mb-1.5">Année fiscale</label>
            <input
              type="number"
              value={year}
              onChange={(e) => setYear(e.target.value)}
              className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D]"
              placeholder="2026"
            />
          </div>
          <a
            href={`/api/fec_export/generate?fiscal_year=${year}`}
            className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] transition-colors"
          >
            <Download size={14} /> Télécharger
          </a>
        </div>
      </div>
    </section>
  );
}

interface AuditEntry {
  id: number;
  timestamp: string;
  user_id: number | null;
  action: string;
  table_name: string;
  record_id: number | null;
  before_value: string | null;
  after_value: string | null;
}

function AuditSection() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    fetch("/api/audit/?limit=200")
      .then((r) => {
        if (!r.ok) throw new Error(r.statusText);
        return r.json();
      })
      .then(setEntries)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const shown = expanded ? entries : entries.slice(0, 20);

  return (
    <section className="mb-8">
      <h2 className="text-base font-semibold text-white mb-3 flex items-center gap-2">
        <ShieldCheck size={16} className="text-[#F2C48D]" />
        Journal d'audit
      </h2>
      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
        {loading ? (
          <div className="py-8 text-center text-sm text-[#666]">Chargement…</div>
        ) : error ? (
          <div className="p-4 text-sm text-[#FF5252]">{error}</div>
        ) : entries.length === 0 ? (
          <div className="py-8 text-center text-sm text-[#666]">Aucun événement enregistré.</div>
        ) : (
          <>
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[#1a1a1a]">
                  <th className="px-4 py-2.5 text-left text-[10px] font-medium text-[#666] uppercase tracking-wider">Date</th>
                  <th className="px-4 py-2.5 text-left text-[10px] font-medium text-[#666] uppercase tracking-wider">Action</th>
                  <th className="px-4 py-2.5 text-left text-[10px] font-medium text-[#666] uppercase tracking-wider">Table</th>
                  <th className="px-4 py-2.5 text-right text-[10px] font-medium text-[#666] uppercase tracking-wider">ID</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((e, idx) => (
                  <tr key={e.id} className={idx > 0 ? "border-t border-[#1a1a1a]" : ""}>
                    <td className="px-4 py-2 text-[#B0B0B0] whitespace-nowrap">
                      {new Date(e.timestamp).toLocaleString("fr-FR")}
                    </td>
                    <td className="px-4 py-2">
                      <span className="inline-block px-1.5 py-0.5 rounded bg-[#222] text-[#B0B0B0] text-[10px] font-mono">
                        {e.action}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-[#B0B0B0]">{e.table_name}</td>
                    <td className="px-4 py-2 text-right text-[#666]">
                      {e.record_id !== null ? `#${e.record_id}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {entries.length > 20 && (
              <div className="border-t border-[#1a1a1a] p-3 text-center">
                <button
                  onClick={() => setExpanded(!expanded)}
                  className="text-xs text-[#F2C48D] hover:underline"
                >
                  {expanded ? "Réduire" : `Afficher les ${entries.length} entrées`}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}

function PasswordSection() {
  const { user } = useAuth();
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");

  if (!user) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSuccess(false);
    if (newPassword !== confirmPassword) {
      setError("Les mots de passe ne correspondent pas");
      return;
    }
    if (newPassword.length < 6) {
      setError("Le mot de passe doit faire au moins 6 caractères");
      return;
    }
    setSaving(true);
    try {
      await api.changePassword(oldPassword, newPassword);
      setSuccess(true);
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: any) {
      setError(err.message || "Erreur lors du changement de mot de passe");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="mb-8">
      <h2 className="text-base font-semibold text-white mb-3">Mon compte</h2>
      <div className="bg-[#111] border border-[#222] rounded-2xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-[#666] text-sm">Identifiant</span>
          <span className="font-medium text-white text-sm">{user.username}</span>
        </div>
        <div className="border-t border-[#1a1a1a] pt-4">
          <p className="text-xs text-[#666] mb-3">Changer le mot de passe</p>
          <form onSubmit={handleSubmit} className="space-y-3">
            <input
              type="password"
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
              placeholder="Mot de passe actuel"
              className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] placeholder:text-[#444]"
              required
            />
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="Nouveau mot de passe"
              className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] placeholder:text-[#444]"
              required
            />
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Confirmer le nouveau mot de passe"
              className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] placeholder:text-[#444]"
              required
            />
            {error && <p className="text-[#FF5252] text-xs">{error}</p>}
            {success && <p className="text-[#00C853] text-xs">Mot de passe modifié avec succès.</p>}
            <button
              type="submit"
              disabled={saving}
              className="bg-[#F2C48D] text-black font-medium rounded-lg px-4 py-2.5 text-sm hover:bg-[#e5b87e] transition-colors disabled:opacity-50"
            >
              {saving ? "Enregistrement..." : "Enregistrer"}
            </button>
          </form>
        </div>
      </div>
    </section>
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
    if (root) {
      setRootEntityId(root.id);
      try {
        const ref = await api.getBalanceRef(root.id);
        setBalanceRef({ date: ref.reference_date || "2025-01-01", amount: ref.reference_amount ?? 0 });
      } catch {
        setBalanceRef({ date: cfg.balance.date || "2025-01-01", amount: cfg.balance.amount ?? 0 });
      }
    } else {
      setBalanceRef({ date: cfg.balance.date || "2025-01-01", amount: cfg.balance.amount ?? 0 });
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
      setModules((prev) =>
        prev.map((m) => (m.id === mod.id ? { ...m, active: !m.active } : m))
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
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
        reference_amount: balanceRef.amount,
      };
      if (field === "amount") payload.reference_amount = parseFloat(value);
      if (field === "date") payload.reference_date = value;
      await api.updateBalanceRef(rootEntityId, payload);
    } else {
      // Fallback to legacy config
      const payload: any = {};
      if (field === "amount") payload.amount = parseFloat(value);
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

  const moduleMap = new Map(modules.map((m) => [m.id, m]));

  function renderModuleRow(mod: DisplayModule, idx: number) {
    const isCore = coreModuleIds.has(mod.id);
    const isExpanded = expandedHelp === mod.id;
    return (
      <div
        key={mod.id}
        className={`${idx > 0 ? "border-t border-[#1a1a1a]" : ""}`}
      >
        <div className="flex items-center justify-between px-5 py-4">
          <div className="flex-1 min-w-0 mr-4">
            <div className="flex items-center gap-2">
              <p className="text-sm font-medium text-white">{mod.name}</p>
              {mod.active && <span className="w-1.5 h-1.5 rounded-full bg-[#00C853] flex-shrink-0" />}
              {mod.help && (
                <button
                  onClick={() => setExpandedHelp(isExpanded ? null : mod.id)}
                  className="text-[#666] hover:text-[#F2C48D] transition-colors p-0.5"
                  aria-label={`Aide pour ${mod.name}`}
                >
                  <Info size={14} />
                </button>
              )}
            </div>
            {mod.description ? <p className="text-xs text-[#666] mt-0.5 truncate">{mod.description}</p> : null}
          </div>
          {isCore ? (
            <span className="text-xs text-[#666] bg-[#1a1a1a] border border-[#222] px-2.5 py-1 rounded-full flex-shrink-0">
              Toujours actif
            </span>
          ) : (
            <button
              onClick={() => handleToggle(mod)}
              disabled={toggling === mod.id}
              className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none ${
                mod.active ? "bg-[#F2C48D]" : "bg-[#333]"
              }`}
              aria-label={`Toggle ${mod.name}`}
            >
              <span
                className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform duration-200 ${
                  mod.active ? "translate-x-5" : "translate-x-0"
                }`}
              />
            </button>
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
    <div className="p-8 max-w-2xl">
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
                value={String(balanceRef.amount)}
                onSave={(v) => updateBalanceRef("amount", v)}
                type="number"
              />
            </div>
          </div>
        </section>
      )}

      <PasswordSection />

      {moduleMap.get("fec_export")?.active && <FecExportSection />}
      {moduleMap.get("audit")?.active && <AuditSection />}

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
          return (
            <div key={catKey}>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-[#666]">{label}</h3>
                <span className="text-xs text-[#666]">{activeCount}/{catModules.length} actifs</span>
              </div>
              <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
                {catModules.map((mod, idx) => renderModuleRow(mod, idx))}
              </div>
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
