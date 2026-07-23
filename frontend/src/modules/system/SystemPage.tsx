import { useEffect, useState } from "react";
import {
  HardDrive, Database, FileUp, Archive, AlertTriangle,
  Check, X, RefreshCw, Trash2, Wrench, Shield, Settings as SettingsIcon,
} from "lucide-react";
import ConfirmDialog from "../../core/ConfirmDialog";
import { useAuth } from "../../core/AuthContext";
import PageLoader from "../../core/PageLoader";

interface SystemStatus {
  version: string;
  settings: { max_backups: number; temp_max_age_hours: number };
  usage: Record<string, number>;
  usage_human: Record<string, string>;
  totals: {
    user_data_human: string; temp_human: string; code_human: string;
  };
  db: {
    connected: boolean;
    tables_count?: number;
    transactions?: number;
    entities?: number;
    modules?: { id: string; version: string }[];
    error?: string;
  };
  pristine: { available: boolean; size: number; mtime: string | null };
  backups: Array<{ name: string; size_human: string; mtime: string; age_seconds: number }>;
  temp_imports: Array<{ name: string; size_human: string; age_hours: number }>;
}

interface PristineCheck {
  healthy: boolean;
  issues_count: number;
  differences: { modified: string[]; missing: string[]; extra: string[] };
}

async function apiJson(path: string, options: RequestInit = {}) {
  const r = await fetch(`/api${path}`, {
    headers: options.body ? { "Content-Type": "application/json" } : {},
    ...options,
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(err.detail || r.statusText);
  }
  return r.json();
}

function formatAge(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}min`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86400)}j`;
}

export default function SystemPage() {
  const { isAdmin } = useAuth();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [pristine, setPristine] = useState<PristineCheck | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [action, setAction] = useState<string>("");
  const [msg, setMsg] = useState("");
  const [editingBackups, setEditingBackups] = useState(false);
  const [maxBackupsInput, setMaxBackupsInput] = useState<number>(5);
  const [confirmRepairOpen, setConfirmRepairOpen] = useState(false);
  const [backupToDelete, setBackupToDelete] = useState<string | null>(null);

  async function load() {
    try {
      const s = await apiJson("/system/status");
      setStatus(s);
      setMaxBackupsInput(s.settings.max_backups);
      if (s.pristine.available) {
        apiJson("/system/pristine/status").then(setPristine).catch(() => {});
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function doCleanup() {
    setAction("cleanup"); setMsg("");
    try {
      const r = await apiJson("/system/cleanup", {
        method: "POST",
        body: JSON.stringify({ clean_temp_imports: true, prune_backups: true, clean_pycache: false }),
      });
      setMsg(`Nettoyage : ${r.temp_imports} temp, ${r.pruned_backups} backups purgés (${r.freed_human} libérés)`);
      await load();
    } catch (e: any) { setError(e.message); }
    finally { setAction(""); }
  }

  async function doRepair() {
    setAction("repair"); setMsg("");
    try {
      const r = await apiJson("/system/repair", {
        method: "POST",
        body: JSON.stringify({ restore_pristine: true, run_migrations: true, rebuild_frontend: false, cleanup_temp: true }),
      });
      setMsg(`Réparation : ${r.restored_files} fichiers restaurés, migrations=${r.migrations_applied}, temp=${r.temp_cleaned}`);
      await load();
    } catch (e: any) { setError(e.message); }
    finally { setAction(""); }
  }

  async function createPristine(overwrite = false) {
    setAction("pristine"); setMsg("");
    try {
      const r = await apiJson("/system/pristine/create", {
        method: "POST",
        body: JSON.stringify({ overwrite }),
      });
      setMsg(`Snapshot pristine créé : ${r.files_added} fichiers, ${r.size_human}`);
      await load();
    } catch (e: any) { setError(e.message); }
    finally { setAction(""); }
  }

  async function deleteBackup(name: string) {
    try {
      await apiJson(`/system/backups/${name}`, { method: "DELETE" });
      await load();
    } catch (e: any) { setError(e.message); }
  }

  async function saveMaxBackups() {
    try {
      await apiJson("/system/settings", {
        method: "PUT",
        body: JSON.stringify({ max_backups: maxBackupsInput }),
      });
      setEditingBackups(false);
      await load();
    } catch (e: any) { setError(e.message); }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <PageLoader fullScreen={false} />
      </div>
    );
  }

  if (!status) return null;

  return (
    <>
    <ConfirmDialog
      open={confirmRepairOpen}
      title="Réparer l'application ?"
      message="Restaure le code à son état initial, lance les migrations, nettoie les temps. Tes données (DB + config) sont préservées."
      confirmLabel="Réparer"
      onConfirm={() => { setConfirmRepairOpen(false); doRepair(); }}
      onCancel={() => setConfirmRepairOpen(false)}
    />
    <ConfirmDialog
      open={backupToDelete !== null}
      title={`Supprimer le backup ${backupToDelete} ?`}
      confirmLabel="Supprimer"
      danger
      onConfirm={() => { const name = backupToDelete!; setBackupToDelete(null); deleteBackup(name); }}
      onCancel={() => setBackupToDelete(null)}
    />
    <div className="p-8 max-w-4xl">
      <h1 className="text-3xl font-bold text-white mb-6" style={{ letterSpacing: "-0.02em" }}>
        Système
      </h1>

      {error && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-sm flex items-start gap-2">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span className="flex-1">{error}</span>
          <button onClick={() => setError("")} className="text-xs" aria-label="Fermer"><X size={14} /></button>
        </div>
      )}

      {msg && (
        <div className="mb-4 p-3 bg-green-500/10 border border-green-500/30 rounded-xl text-green-400 text-sm flex items-start gap-2">
          <Check size={16} className="mt-0.5 shrink-0" />
          <span className="flex-1">{msg}</span>
          <button onClick={() => setMsg("")} className="text-xs" aria-label="Fermer"><X size={14} /></button>
        </div>
      )}

      {/* Health overview */}
      <section className="grid grid-cols-3 gap-3 mb-6">
        <div className="bg-bg-card border border-border rounded-xl p-4">
          <div className="flex items-center gap-2 text-[#8a8a8a] text-xs uppercase tracking-wider mb-2">
            <Database size={13} /> Données utilisateur
          </div>
          <p className="text-2xl font-bold text-white">{status.totals.user_data_human}</p>
          <p className="text-xs text-[#8a8a8a] mt-1">
            DB + attachments + backups
          </p>
        </div>
        <div className="bg-bg-card border border-border rounded-xl p-4">
          <div className="flex items-center gap-2 text-[#8a8a8a] text-xs uppercase tracking-wider mb-2">
            <FileUp size={13} /> Temporaire
          </div>
          <p className="text-2xl font-bold text-white">{status.totals.temp_human}</p>
          <p className="text-xs text-[#8a8a8a] mt-1">
            {status.temp_imports.length} fichier(s) import en attente
          </p>
        </div>
        <div className="bg-bg-card border border-border rounded-xl p-4">
          <div className="flex items-center gap-2 text-[#8a8a8a] text-xs uppercase tracking-wider mb-2">
            <HardDrive size={13} /> Code
          </div>
          <p className="text-2xl font-bold text-white">{status.totals.code_human}</p>
          <p className="text-xs text-[#8a8a8a] mt-1">
            backend + frontend (sans node_modules)
          </p>
        </div>
      </section>

      {/* DB health */}
      <section className="bg-bg-card border border-border rounded-xl p-5 mb-5">
        <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <Database size={15} /> Base de données
        </h2>
        {status.db.connected ? (
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div><span className="text-[#8a8a8a]">Tables</span><p className="text-white font-medium">{status.db.tables_count}</p></div>
            <div><span className="text-[#8a8a8a]">Transactions</span><p className="text-white font-medium">{status.db.transactions}</p></div>
            <div><span className="text-[#8a8a8a]">Entités</span><p className="text-white font-medium">{status.db.entities}</p></div>
          </div>
        ) : (
          <p className="text-red-400 text-sm">Connexion impossible: {status.db.error}</p>
        )}
      </section>

      {/* Pristine / Repair */}
      <section className="bg-bg-card border border-border rounded-xl p-5 mb-5">
        <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <Shield size={15} /> Intégrité du code
        </h2>
        {!status.pristine.available ? (
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-white">Aucun snapshot de référence</p>
              <p className="text-xs text-[#8a8a8a] mt-1">
                Créez un snapshot de l'état actuel pour pouvoir réparer plus tard.
              </p>
            </div>
            {isAdmin && (
              <button
                onClick={() => createPristine(false)}
                disabled={action === "pristine"}
                className="px-4 py-2 bg-accent-sand text-black font-medium rounded-lg hover:bg-[#e5b87e] disabled:opacity-50 text-sm"
              >
                {action === "pristine" ? "Création..." : "Créer le snapshot"}
              </button>
            )}
          </div>
        ) : pristine ? (
          <>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                {pristine.healthy ? (
                  <><Check size={16} className="text-green-400" /><span className="text-sm text-green-400">Code conforme au snapshot</span></>
                ) : (
                  <><AlertTriangle size={16} className="text-yellow-400" /><span className="text-sm text-yellow-400">{pristine.issues_count} fichier(s) différent(s) du snapshot</span></>
                )}
              </div>
              <div className="flex gap-2">
                {isAdmin && (
                  <button
                    onClick={() => createPristine(true)}
                    disabled={action !== ""}
                    className="px-3 py-1.5 text-xs border border-border-hover text-[#999] hover:text-white rounded-lg transition-colors"
                    title="Écraser le snapshot avec l'état actuel, réservé à l'admin"
                  >
                    <RefreshCw size={12} className="inline mr-1" />
                    Mettre à jour
                  </button>
                )}
                {!pristine.healthy && (
                  <button
                    onClick={() => setConfirmRepairOpen(true)}
                    disabled={action !== ""}
                    className="px-4 py-1.5 bg-accent-sand text-black font-medium rounded-lg hover:bg-[#e5b87e] disabled:opacity-50 text-xs flex items-center gap-1.5"
                  >
                    <Wrench size={12} />
                    {action === "repair" ? "Réparation..." : "Réparer"}
                  </button>
                )}
              </div>
            </div>
            {!pristine.healthy && (
              <div className="bg-[#0a0a0a] border border-border rounded-lg p-3 max-h-32 overflow-y-auto">
                {pristine.differences.modified.slice(0, 20).map((f) => (
                  <p key={f} className="text-xs text-yellow-400 font-mono">~ {f}</p>
                ))}
                {pristine.differences.missing.slice(0, 20).map((f) => (
                  <p key={f} className="text-xs text-red-400 font-mono">- {f} (manquant)</p>
                ))}
              </div>
            )}
            <p className="text-xs text-[#555] mt-2">
              Snapshot : {(status.pristine.size / 1024).toFixed(0)} KB · {status.pristine.mtime ? new Date(status.pristine.mtime).toLocaleString("fr-FR") : ""}
            </p>
          </>
        ) : null}
      </section>

      {/* Backups */}
      <section className="bg-bg-card border border-border rounded-xl p-5 mb-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <Archive size={15} /> Sauvegardes automatiques
            <span className="text-xs text-[#8a8a8a] font-normal">({status.backups.length})</span>
          </h2>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-[#8a8a8a]">Garder max</span>
            {editingBackups ? (
              <>
                <input
                  type="number" min={1} max={50}
                  value={maxBackupsInput}
                  onChange={(e) => setMaxBackupsInput(parseInt(e.target.value) || 1)}
                  className="w-14 bg-[#0a0a0a] border border-accent-sand rounded px-2 py-1 text-white text-xs focus:outline-none"
                />
                <button onClick={saveMaxBackups} className="text-green-400 hover:text-green-300">✓</button>
                <button onClick={() => { setEditingBackups(false); setMaxBackupsInput(status.settings.max_backups); }} className="text-red-400 hover:text-red-300" aria-label="Annuler"><X size={14} /></button>
              </>
            ) : (
              <button
                onClick={() => setEditingBackups(true)}
                className="flex items-center gap-1 text-accent-sand hover:underline"
              >
                {status.settings.max_backups} <SettingsIcon size={11} />
              </button>
            )}
          </div>
        </div>

        {status.backups.length === 0 ? (
          <p className="text-xs text-[#8a8a8a] text-center py-4">Aucune sauvegarde</p>
        ) : (
          <div className="space-y-1.5">
            {status.backups.slice().reverse().map((b) => (
              <div key={b.name} className="flex items-center justify-between bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg px-3 py-2 text-xs">
                <div className="flex-1 min-w-0">
                  <p className="text-[#ccc] truncate">{b.name}</p>
                  <p className="text-[#8a8a8a] mt-0.5">
                    {new Date(b.mtime).toLocaleString("fr-FR")} · il y a {formatAge(b.age_seconds)}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[#999]">{b.size_human}</span>
                  <button
                    onClick={() => setBackupToDelete(b.name)}
                    className="text-[#555] hover:text-red-400 p-1 transition-colors"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Temp imports */}
      {status.temp_imports.length > 0 && (
        <section className="bg-bg-card border border-border rounded-xl p-5 mb-5">
          <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <FileUp size={15} /> Imports en attente ({status.temp_imports.length})
          </h2>
          <div className="space-y-1.5">
            {status.temp_imports.map((t) => (
              <div key={t.name} className="flex items-center justify-between bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg px-3 py-2 text-xs">
                <span className="text-[#ccc] truncate flex-1">{t.name}</span>
                <span className="text-[#8a8a8a] mx-3">{t.size_human}</span>
                <span className={t.age_hours > status.settings.temp_max_age_hours ? "text-red-400" : "text-[#8a8a8a]"}>
                  il y a {formatAge(t.age_hours * 3600)}
                </span>
              </div>
            ))}
          </div>
          <p className="text-xs text-[#8a8a8a] mt-2">
            Les fichiers de plus de {status.settings.temp_max_age_hours}h sont supprimés au nettoyage.
          </p>
        </section>
      )}

      {/* Actions */}
      <section className="bg-bg-card border border-border rounded-xl p-5">
        <h2 className="text-sm font-semibold text-white mb-4">Actions de maintenance</h2>
        <div className="grid grid-cols-2 gap-3">
          <button
            onClick={doCleanup}
            disabled={action !== ""}
            className="flex flex-col items-start gap-1 p-4 bg-[#0a0a0a] hover:bg-[#151515] border border-border hover:border-border-hover rounded-xl text-left disabled:opacity-50 transition-colors"
          >
            <div className="flex items-center gap-2 text-white font-medium text-sm">
              <Trash2 size={14} /> Nettoyer les temporaires
            </div>
            <p className="text-xs text-[#8a8a8a]">
              Supprime les imports non commités &gt; {status.settings.temp_max_age_hours}h et purge les backups au-delà de {status.settings.max_backups}.
            </p>
          </button>
          <button
            onClick={() => setConfirmRepairOpen(true)}
            disabled={action !== "" || !status.pristine.available}
            className="flex flex-col items-start gap-1 p-4 bg-[#0a0a0a] hover:bg-[#151515] border border-border hover:border-border-hover rounded-xl text-left disabled:opacity-50 transition-colors"
          >
            <div className="flex items-center gap-2 text-white font-medium text-sm">
              <Wrench size={14} /> Réparer l'application
            </div>
            <p className="text-xs text-[#8a8a8a]">
              Restaure le code depuis le snapshot initial. Tes données et config sont préservées.
            </p>
          </button>
        </div>
      </section>
    </div>
    </>
  );
}
