import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { AppConfig, ModuleManifest } from "../types";
import { Pencil, Check, X, Info, MapPin, ArrowRight } from "lucide-react";
import { MODULE_ROUTES, INTEGRATED_LOCATIONS } from "../routes";
import PageLoader from "./PageLoader";
import { useAuth } from "./AuthContext";

const accountInputClass =
  "w-full bg-[#0a0a0a] border border-border rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-accent-sand transition-colors placeholder-text-muted";

function MyAccountSection() {
  const { user, logout } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [busy, setBusy] = useState(false);

  const [editingProfile, setEditingProfile] = useState(false);
  const [profileName, setProfileName] = useState(user?.display_name || "");
  const [profileEmail, setProfileEmail] = useState(user?.email || "");
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileSuccess, setProfileSuccess] = useState(false);
  const [profileBusy, setProfileBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(false);
    if (newPassword !== confirmPassword) {
      setError("Les deux mots de passe ne correspondent pas");
      return;
    }
    setBusy(true);
    try {
      await api.changeMyPassword(currentPassword, newPassword);
      setSuccess(true);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: any) {
      setError(err?.message || "Changement de mot de passe impossible");
    } finally {
      setBusy(false);
    }
  }

  async function handleLogout() {
    await logout();
    window.location.href = "/";
  }

  async function onSaveProfile(e: FormEvent) {
    e.preventDefault();
    setProfileError(null);
    setProfileSuccess(false);
    setProfileBusy(true);
    try {
      await api.updateMe({
        display_name: profileName.trim(),
        email: profileEmail.trim(),
      });
      setProfileSuccess(true);
      setEditingProfile(false);
      // Refresh user data in AuthContext
      window.location.reload();
    } catch (err: any) {
      setProfileError(err?.message || "Modification impossible");
    } finally {
      setProfileBusy(false);
    }
  }

  return (
    <section className="mb-8">
      <h2 className="text-base font-semibold text-white mb-3">Mon compte</h2>
      <div className="bg-bg-card border border-border rounded-2xl p-5 space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-white">{user?.display_name}</p>
            <p className="text-xs text-[#8a8a8a]">{user?.email}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => { setEditingProfile(true); setProfileName(user?.display_name || ""); setProfileEmail(user?.email || ""); setProfileError(null); setProfileSuccess(false); }}
              className="px-4 py-2 text-xs font-semibold text-accent-sand border border-border-hover rounded-full hover:border-accent-sand transition-colors"
            >
              Modifier
            </button>
            <button
              onClick={handleLogout}
              className="px-4 py-2 text-xs font-semibold text-white bg-[#1a1a1a] border border-border rounded-full hover:border-alert hover:text-alert transition-colors"
            >
              Se déconnecter
            </button>
          </div>
        </div>
        {editingProfile && (
          <form onSubmit={onSaveProfile} className="border-t border-[#1a1a1a] pt-5 space-y-3 max-w-sm">
            <p className="text-xs text-[#8a8a8a]">Modifier mon profil</p>
            <input
              value={profileName}
              onChange={(e) => setProfileName(e.target.value)}
              placeholder="Prénom Nom"
              className={accountInputClass}
            />
            <input
              type="email"
              value={profileEmail}
              onChange={(e) => setProfileEmail(e.target.value)}
              placeholder="Email"
              className={accountInputClass}
            />
            {profileError && <p className="text-sm text-alert">{profileError}</p>}
            {profileSuccess && <p className="text-sm text-success">Profil modifié</p>}
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={profileBusy}
                className="px-4 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-full hover:bg-accent-sand transition-colors disabled:opacity-50"
              >
                {profileBusy ? "Enregistrement..." : "Enregistrer"}
              </button>
              <button
                type="button"
                onClick={() => setEditingProfile(false)}
                className="px-4 py-2.5 text-sm font-semibold text-white border border-border-hover rounded-full hover:border-[#444] transition-colors"
              >
                Annuler
              </button>
            </div>
          </form>
        )}

        <div className="border-t border-[#1a1a1a] pt-5">
          <form onSubmit={onSubmit} className="space-y-3 max-w-sm">
            <p className="text-xs text-[#8a8a8a]">Changer de mot de passe</p>
            <input
              type="password"
              required
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder="Mot de passe actuel"
              className={accountInputClass}
            />
            <input
              type="password"
              required
              minLength={10}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="Nouveau mot de passe (10 caractères minimum)"
              className={accountInputClass}
            />
            <input
              type="password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Confirme le nouveau mot de passe"
              className={accountInputClass}
            />
            {error && <p className="text-sm text-alert">{error}</p>}
            {success && <p className="text-sm text-success">Mot de passe modifié</p>}
            <button
              type="submit"
              disabled={busy}
              className="px-4 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-full hover:bg-accent-sand transition-colors disabled:opacity-50"
            >
              {busy ? "Modification..." : "Changer le mot de passe"}
            </button>
          </form>
        </div>
      </div>
    </section>
  );
}

// Category labels, modules are classified dynamically via manifest.category.
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
        <span className="text-[#8a8a8a] text-sm w-40 flex-shrink-0">{label}</span>
        {type === "select" && options ? (
          <select
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="flex-1 bg-[#0a0a0a] border border-accent-sand rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none"
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
            className="flex-1 bg-[#0a0a0a] border border-accent-sand rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSave();
              if (e.key === "Escape") handleCancel();
            }}
          />
        )}
        <button onClick={handleSave} disabled={saving} className="text-success hover:text-white p-1">
          <Check size={16} />
        </button>
        <button onClick={handleCancel} className="text-alert hover:text-white p-1">
          <X size={16} />
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between group">
      <span className="text-[#8a8a8a] text-sm">{label}</span>
      <div className="flex items-center gap-2">
        <span className="font-medium text-white text-sm">{displayValue ?? (value || "—")}</span>
        <button
          onClick={() => setEditing(true)}
          className="opacity-0 group-hover:opacity-100 text-[#8a8a8a] hover:text-accent-sand transition-opacity p-1"
        >
          <Pencil size={14} />
        </button>
      </div>
    </div>
  );
}

type RefEdit = { date: string; amount: string };

function StructureSoldesSection() {
  const [tree, setTree] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refs, setRefs] = useState<Record<number, RefEdit>>({});
  const [savingId, setSavingId] = useState<number | null>(null);
  const [savedId, setSavedId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const t = await api.getEntityTree();
      setTree(t);
      const root = t.find((e: any) => e.balance_mode === "aggregate") ?? t[0];
      const children = (root?.children ?? []) as any[];
      const clubs = children.filter((c) => !c.is_residual);
      const entries = await Promise.all(
        clubs.map(async (c) => {
          const r = await api.getBalanceRef(c.id).catch(() => null);
          return [c.id, {
            date: r?.reference_date ?? "",
            amount: r?.reference_amount != null && r.reference_amount !== 0 ? String(r.reference_amount / 100) : "",
          }] as [number, RefEdit];
        })
      );
      setRefs(Object.fromEntries(entries));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, []);

  const root = tree.find((e: any) => e.balance_mode === "aggregate") ?? tree[0];
  const children = (root?.children ?? []) as any[];
  const residual = children.find((c) => c.is_residual);
  const clubs = children.filter((c) => !c.is_residual);

  async function saveRef(id: number) {
    const v = refs[id];
    const parsed = v.amount === "" ? 0 : parseFloat(v.amount.replace(",", "."));
    if (isNaN(parsed)) { setError("Montant invalide."); return; }
    setSavingId(id); setError(null);
    try {
      await api.updateBalanceRef(id, {
        reference_date: v.date || null,
        reference_amount: Math.round(parsed * 100),
      });
      setSavedId(id); setTimeout(() => setSavedId(null), 1500);
    } catch (e: any) {
      setError(e.message || "Erreur lors de l'enregistrement");
    } finally {
      setSavingId(null);
    }
  }

  async function changeResidual(id: number) {
    setError(null);
    try { await api.setResidualEntity(id); await load(); }
    catch (e: any) { setError(e.message || "Erreur"); }
  }

  if (loading || !root || children.length === 0) return null;

  return (
    <section className="mb-8">
      <h2 className="text-base font-semibold text-white mb-3">Soldes &amp; structure</h2>
      <div className="bg-bg-card border border-border rounded-2xl p-5 space-y-6">
        <p className="text-sm text-text-secondary leading-relaxed">
          Le solde global vient de la{" "}
          <Link to="/treasury" className="text-accent-sand hover:underline">Trésorerie</Link>{" "}
          (source de vérité). Tu saisis ici le solde des clubs ; l'entité «&nbsp;déduite&nbsp;»
          se calcule automatiquement = Trésorerie − la somme des clubs.
        </p>

        <div>
          <label className="block text-xs uppercase tracking-wider text-[#8a8a8a] mb-2">
            Entité déduite (calculée automatiquement)
          </label>
          <select
            value={residual?.id ?? ""}
            onChange={(e) => changeResidual(Number(e.target.value))}
            className={accountInputClass}
          >
            {children.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <p className="text-xs text-[#555] mt-1">
            Son solde = Trésorerie − les autres clubs. Elle ne se saisit pas à la main.
          </p>
        </div>

        <div className="space-y-3">
          <p className="text-xs uppercase tracking-wider text-[#8a8a8a]">Soldes de référence des clubs</p>
          {clubs.length === 0 && (
            <p className="text-sm text-[#555]">Aucun club à saisir (tous déduits ?).</p>
          )}
          {clubs.map((c) => (
            <div key={c.id} className="flex flex-col sm:flex-row sm:items-center gap-2">
              <span className="sm:w-40 truncate text-sm text-white flex items-center gap-2">
                <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: c.color || "#6B7280" }} />
                {c.name}
              </span>
              <input
                type="date"
                value={refs[c.id]?.date ?? ""}
                onChange={(e) => setRefs((r) => ({ ...r, [c.id]: { ...r[c.id], date: e.target.value } }))}
                className={`${accountInputClass} sm:flex-1`}
              />
              <input
                type="number"
                step="0.01"
                placeholder="Montant €"
                value={refs[c.id]?.amount ?? ""}
                onChange={(e) => setRefs((r) => ({ ...r, [c.id]: { ...r[c.id], amount: e.target.value } }))}
                className={`${accountInputClass} sm:w-40`}
              />
              <button
                onClick={() => saveRef(c.id)}
                disabled={savingId === c.id}
                className="px-4 py-2.5 rounded-xl bg-accent-sand text-black text-sm font-medium hover:bg-[#e5b57e] disabled:opacity-50 transition-colors flex-shrink-0"
              >
                {savingId === c.id ? "..." : savedId === c.id ? "✓" : "Enregistrer"}
              </button>
            </div>
          ))}
        </div>

        {error && <p className="text-xs text-alert">{error}</p>}
      </div>
    </section>
  );
}

export default function Settings() {
  const { isAdmin } = useAuth();
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [modules, setModules] = useState<DisplayModule[]>([]);
  const [coreModuleIds, setCoreModuleIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);
  const [expandedHelp, setExpandedHelp] = useState<string | null>(null);
  const [showCoreModules, setShowCoreModules] = useState(false);

  async function reload() {
    const [cfg, discoveredMods] = await Promise.all([
      api.getConfig(),
      api.getAllModules(),
    ]);
    setConfig(cfg);

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
              {mod.active && <span className="w-1.5 h-1.5 rounded-full bg-success" />}
              {mod.help && (
                <button
                  onClick={() => setExpandedHelp(isExpanded ? null : mod.id)}
                  className="text-[#8a8a8a] hover:text-accent-sand p-0.5"
                  aria-label={`Aide pour ${mod.name}`}
                >
                  <Info size={14} />
                </button>
              )}
            </div>
            {isCore ? (
              <span className="text-xs text-[#8a8a8a] bg-[#1a1a1a] border border-border px-2.5 py-1 rounded-full">
                Toujours actif
              </span>
            ) : (
              <button
                onClick={() => handleToggle(mod)}
                disabled={toggling === mod.id}
                className={`relative inline-flex h-6 w-11 flex-shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 ${
                  mod.active ? "bg-accent-sand" : "bg-[#333]"
                }`}
              >
                <span className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform ${
                  mod.active ? "translate-x-5" : "translate-x-0"
                }`} />
              </button>
            )}
          </div>

          {location && (
            <div className="flex items-center gap-1.5 text-xs text-text-secondary">
              <MapPin size={11} className="text-[#8a8a8a]" />
              <span>{location}</span>
            </div>
          )}

          {mod.description && (
            <p className="text-xs text-text-secondary leading-relaxed">{mod.description}</p>
          )}

          {mod.example && (
            <p className="text-xs text-[#8a8a8a] italic leading-relaxed">
              Exemple : {mod.example}
            </p>
          )}

          {actionPath && (
            <Link to={actionPath} className="inline-flex items-center gap-1 text-xs text-accent-sand hover:underline">
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

      <MyAccountSection />

      {isAdmin && <StructureSoldesSection />}

      {isAdmin && (
        <>
          {error && (
            <div className="mb-4 bg-[#1a0a0a] border border-alert/30 text-alert rounded-2xl p-4 text-sm flex justify-between items-center">
              <span>{error}</span>
              <button onClick={() => setError(null)} className="text-xs underline ml-2">Fermer</button>
            </div>
          )}

          {loading ? (
            <PageLoader fullScreen={false} />
          ) : (
            <>
              {(() => {
                const tools = [
                  { id: "system", label: "Système", desc: "État de l'installation, intégrité, snapshots" },
                  { id: "backup", label: "Sauvegarde & restauration", desc: "Exporter et réimporter les données" },
                  { id: "users", label: "Utilisateurs", desc: "Comptes, invitations, rôles" },
                ].filter((t) => modules.find((m) => m.id === t.id)?.active && MODULE_ROUTES[t.id]);
                if (tools.length === 0) return null;
                return (
                  <section className="mb-8">
                    <h2 className="text-base font-semibold text-white mb-3">Administration</h2>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                      {tools.map((t) => (
                        <Link
                          key={t.id}
                          to={MODULE_ROUTES[t.id].path}
                          className="bg-bg-card border border-border rounded-2xl p-5 hover:border-accent-sand/50 transition-colors group"
                        >
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm font-semibold text-white">{t.label}</span>
                            <ArrowRight size={14} className="text-[#8a8a8a] group-hover:text-accent-sand transition-colors" />
                          </div>
                          <p className="text-xs text-text-secondary leading-relaxed">{t.desc}</p>
                        </Link>
                      ))}
                    </div>
                  </section>
                );
              })()}

              {config && (
                <section className="mb-8">
                  <h2 className="text-base font-semibold text-white mb-3">Entité</h2>
                  <div className="bg-bg-card border border-border rounded-2xl p-5 space-y-4">
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
                    <div className="border-t border-[#1a1a1a] pt-4 flex items-center gap-1.5 text-xs text-text-secondary">
                      <MapPin size={11} className="text-[#8a8a8a]" />
                      <span>Le solde global de la trésorerie (compte, livret, caisse) se définit désormais dans l'onglet <Link to="/treasury" className="text-accent-sand hover:underline">Trésorerie</Link>.</span>
                    </div>
                  </div>
                </section>
              )}

              <section className="space-y-6">
                <h2 className="text-base font-semibold text-white">Modules</h2>
                <p className="text-xs text-[#8a8a8a] -mt-4">
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
                        <h3 className="text-xs font-semibold uppercase tracking-wider text-[#8a8a8a]">{label}</h3>
                        <div className="flex items-center gap-3">
                          <span className="text-xs text-[#8a8a8a]">{activeCount}/{catModules.length} actifs</span>
                          {isCoreGroup && (
                            <button
                              onClick={() => setShowCoreModules((v) => !v)}
                              className="text-xs text-accent-sand hover:underline"
                            >
                              {collapsed ? "Afficher" : "Masquer"}
                            </button>
                          )}
                        </div>
                      </div>
                      {!collapsed && (
                        <div className="bg-bg-card border border-border rounded-2xl overflow-hidden">
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
                        <h3 className="text-xs font-semibold uppercase tracking-wider text-[#8a8a8a]">Autre</h3>
                        <span className="text-xs text-[#8a8a8a]">
                          {orphans.filter((m) => m.active).length}/{orphans.length} actifs
                        </span>
                      </div>
                      <div className="bg-bg-card border border-border rounded-2xl overflow-hidden">
                        {orphans.map((mod, idx) => renderModuleRow(mod, idx))}
                      </div>
                    </div>
                  );
                })()}
              </section>
            </>
          )}
        </>
      )}
    </div>
  );
}
