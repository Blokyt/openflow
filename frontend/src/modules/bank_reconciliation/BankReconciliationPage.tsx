import { useCallback, useEffect, useRef, useState } from "react";
import {
  Upload, Landmark, Link2, CheckCircle2, AlertCircle, X, Plus, Trash2, Search,
  ChevronDown, GitCompare, BadgeCheck, RefreshCw, KeyRound, Cloud, Wifi,
  Copy, ExternalLink,
} from "lucide-react";
import { api } from "../../api";
import { formatEuros, formatDate, COLOR_INCOME, COLOR_EXPENSE } from "../../utils/format";
import EmptyState from "../../core/EmptyState";
import { inputClass, labelClass } from "../../core/formStyles";
import PageLoader from "../../core/PageLoader";

type Account = {
  id: number;
  entity_id: number;
  entity_name: string | null;
  label: string;
  iban: string;
  source: string;
  consent_expires_at: string;
  last_synced_at: string;
  tx_count: number;
  to_reconcile_count: number;
};

type BankTx = {
  id: number;
  booking_date: string;
  amount: number;
  label: string;
  counterparty: string;
  linked_cents: number;
  pending_cents: number;
  reconciled: boolean;
  reconciled_manual: boolean;
};

type TxRow = {
  transaction_id: number;
  date: string;
  label: string;
  amount: number;
  from_entity_name: string | null;
  to_entity_name: string | null;
};

const amountColor = (cents: number) => (cents >= 0 ? COLOR_INCOME : COLOR_EXPENSE);

export default function BankReconciliationPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [txs, setTxs] = useState<BankTx[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingTxs, setLoadingTxs] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showDone, setShowDone] = useState(false);
  const [linking, setLinking] = useState<BankTx | null>(null);
  const [ebConfigured, setEbConfigured] = useState(false);
  const [showEbConfig, setShowEbConfig] = useState(false);
  const [connectingAccount, setConnectingAccount] = useState<Account | null>(null);
  const [syncingId, setSyncingId] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadAccounts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [accs, cfg] = await Promise.all([api.getBankAccounts(), api.getBankConfig().catch(() => null)]);
      setAccounts(accs);
      setEbConfigured(!!cfg?.configured);
      setSelectedId((prev) => (prev && accs.some((a: Account) => a.id === prev) ? prev : accs[0]?.id ?? null));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadTxs = useCallback(async (accountId: number) => {
    setLoadingTxs(true);
    setError(null);
    try {
      // Un seul appel : le tri à traiter / rapproché est fait côté client
      // à partir du champ `reconciled` (cf. toTreat/done ci-dessous).
      setTxs(await api.getBankTransactions(accountId, "all"));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoadingTxs(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    if (selectedId) await Promise.all([loadTxs(selectedId), loadAccounts()]);
  }, [selectedId, loadTxs, loadAccounts]);

  useEffect(() => { loadAccounts(); }, [loadAccounts]);
  useEffect(() => { if (selectedId) loadTxs(selectedId); }, [selectedId, loadTxs]);

  // Retour de la redirection SCA Enable Banking : ?code=...&state=<accountId>.<jeton>
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const state = params.get("state");
    if (!code || !state) return;
    const accountId = Number(state.split(".")[0]);
    // Nettoie l'URL tout de suite pour éviter un double appel au re-render.
    window.history.replaceState({}, "", window.location.pathname);
    if (!Number.isFinite(accountId)) return;
    (async () => {
      try {
        await api.finalizeBank(accountId, code);
        setNotice("Compte bancaire connecté. Lance une synchronisation pour importer les opérations.");
        await loadAccounts();
        setSelectedId(accountId);
      } catch (e: any) {
        setError(`Échec de la connexion bancaire : ${e.message}`);
      }
    })();
  }, [loadAccounts]);

  const onSync = async (account: Account) => {
    setSyncingId(account.id);
    setError(null);
    setNotice(null);
    try {
      const res = await api.syncBank(account.id);
      setNotice(`Synchronisation terminée : ${res.imported} nouvelle${res.imported > 1 ? "s" : ""} opération${res.imported > 1 ? "s" : ""}.`);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSyncingId(null);
    }
  };

  const onImport = async (file: File) => {
    if (!selectedId) return;
    setImporting(true);
    setError(null);
    setNotice(null);
    try {
      const res = await api.importBankStatement(selectedId, file);
      setNotice(`${res.imported} nouvelle${res.imported > 1 ? "s" : ""} ligne${res.imported > 1 ? "s" : ""} importée${res.imported > 1 ? "s" : ""}` +
        (res.skipped > 0 ? ` (${res.skipped} déjà présente${res.skipped > 1 ? "s" : ""}, ignorée${res.skipped > 1 ? "s" : ""})` : "") + ".");
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  if (loading) {
    return (
      <div className="p-8">
        <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>Rapprochement bancaire</h1>
        <div className="flex items-center justify-center py-20"><PageLoader fullScreen={false} /></div>
      </div>
    );
  }

  if (accounts.length === 0) {
    return (
      <div className="p-8">
        <h1 className="text-3xl font-bold text-white mb-1" style={{ letterSpacing: "-0.02em" }}>Rapprochement bancaire</h1>
        <p className="text-sm text-[#8a8a8a] mb-8">Crée un compte bancaire pour importer ses relevés et rapprocher chaque ligne avec ta compta.</p>
        <AccountForm onSaved={loadAccounts} />
      </div>
    );
  }

  const selected = accounts.find((a) => a.id === selectedId) || null;
  const toTreat = txs.filter((t) => !t.reconciled)
    .sort((a, b) => (b.booking_date < a.booking_date ? -1 : b.booking_date > a.booking_date ? 1 : b.id - a.id));
  const done = txs.filter((t) => t.reconciled);
  const totalPending = toTreat.reduce((s, t) => s + Math.abs(t.pending_cents), 0);

  return (
    <div className="p-8">
      <div className="flex items-start justify-between mb-6 gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>Rapprochement bancaire</h1>
          <p className="text-sm text-[#8a8a8a] mt-1">
            Importe ton relevé, puis associe à chaque ligne bancaire la ou les écritures qui la composent.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.ofx,.qfx,text/csv,application/x-ofx"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) onImport(f); }}
          />
          {selected && selected.source === "enablebanking" ? (
            <button
              onClick={() => onSync(selected)}
              disabled={syncingId === selected.id}
              className="flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-white bg-[#1a1a1a] border border-[#2a2a2a] rounded-full hover:border-accent-sand/50 disabled:opacity-50 transition-colors whitespace-nowrap"
            >
              <RefreshCw size={15} className={syncingId === selected.id ? "animate-spin" : ""} />
              {syncingId === selected.id ? "Synchro…" : "Synchroniser"}
            </button>
          ) : selected && ebConfigured ? (
            <button
              onClick={() => setConnectingAccount(selected)}
              className="flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-white bg-[#1a1a1a] border border-[#2a2a2a] rounded-full hover:border-accent-sand/50 transition-colors whitespace-nowrap"
            >
              <Wifi size={15} /> Connecter à la banque
            </button>
          ) : null}
          <button
            onClick={() => setShowEbConfig(true)}
            className="flex items-center gap-2 px-3 py-2.5 text-sm text-[#8a8a8a] hover:text-white border border-[#2a2a2a] rounded-full transition-colors whitespace-nowrap"
            title="Configurer la connexion automatique Enable Banking"
          >
            <Cloud size={15} /> {ebConfigured ? "Enable Banking" : "Connexion auto"}
          </button>
          <button
            onClick={() => fileRef.current?.click()}
            disabled={importing}
            className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-full hover:bg-accent-sand disabled:opacity-50 transition-colors whitespace-nowrap"
          >
            <Upload size={15} className={importing ? "animate-pulse" : ""} />
            {importing ? "Import…" : "Importer un relevé"}
          </button>
        </div>
      </div>

      <AccountBar
        accounts={accounts}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onAdded={loadAccounts}
        onDeleted={loadAccounts}
      />

      {error && (
        <div className="mb-4 bg-[#1a0a0a] border border-alert/30 text-alert rounded-2xl p-4 text-sm flex items-start justify-between gap-3">
          <span className="flex items-center gap-2"><AlertCircle size={16} /> {error}</span>
          <button onClick={() => setError(null)} className="text-alert/70 hover:text-alert"><X size={16} /></button>
        </div>
      )}
      {notice && (
        <div className="mb-4 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded-2xl p-4 text-sm flex items-start justify-between gap-3">
          <span className="flex items-center gap-2"><CheckCircle2 size={16} /> {notice}</span>
          <button onClick={() => setNotice(null)} className="text-emerald-400/70 hover:text-emerald-400"><X size={16} /></button>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6 mt-4">
        <div className="bg-bg-card border border-border rounded-2xl p-5">
          <div className="text-xs font-medium text-[#8a8a8a] uppercase tracking-wider mb-2">Reste à rapprocher</div>
          <div className={`text-2xl font-bold ${totalPending > 0 ? "text-[#FF8A5B]" : "text-success"}`}>{formatEuros(totalPending)}</div>
        </div>
        <div className="bg-bg-card border border-border rounded-2xl p-5">
          <div className="text-xs font-medium text-[#8a8a8a] uppercase tracking-wider mb-2">Lignes à traiter</div>
          <div className="text-2xl font-bold text-white">{toTreat.length}</div>
        </div>
        <div className="bg-bg-card border border-border rounded-2xl p-5">
          <div className="text-xs font-medium text-[#8a8a8a] uppercase tracking-wider mb-2">Lignes rapprochées</div>
          <div className="text-2xl font-bold text-accent-sand">{done.length}</div>
        </div>
      </div>

      {loadingTxs ? (
        <div className="flex items-center justify-center py-16"><PageLoader fullScreen={false} /></div>
      ) : txs.length === 0 ? (
        <EmptyState
          icon={Upload}
          title="Aucune ligne bancaire"
          description="Importe un relevé (CSV ou OFX) exporté depuis l'espace en ligne de ta banque pour commencer le rapprochement."
          ctaLabel={importing ? "Import…" : "Importer un relevé"}
          onCta={() => fileRef.current?.click()}
        />
      ) : (
        <>
          {toTreat.length > 0 ? (
            <div className="bg-bg-card border border-border rounded-2xl overflow-hidden">
              <div className="px-5 py-3 border-b border-[#1a1a1a] text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">À rapprocher</div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[#1a1a1a]">
                      <th className="px-5 py-3 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Date</th>
                      <th className="px-5 py-3 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Libellé</th>
                      <th className="px-5 py-3 text-right text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Montant</th>
                      <th className="px-5 py-3 text-right text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Associé</th>
                      <th className="px-5 py-3 text-right text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Reste</th>
                      <th className="px-5 py-3 text-right"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {toTreat.map((t, idx) => (
                      <tr key={t.id} className={`hover:bg-[#1a1a1a] transition-colors ${idx > 0 ? "border-t border-[#1a1a1a]" : ""}`}>
                        <td className="px-5 py-3.5 text-text-secondary whitespace-nowrap">{formatDate(t.booking_date)}</td>
                        <td className="px-5 py-3.5 font-medium text-white max-w-xs truncate" title={t.label}>{t.label}</td>
                        <td className="px-5 py-3.5 text-right font-semibold whitespace-nowrap" style={{ color: amountColor(t.amount) }}>{formatEuros(t.amount)}</td>
                        <td className="px-5 py-3.5 text-right text-[#777] whitespace-nowrap">{formatEuros(t.linked_cents)}</td>
                        <td className="px-5 py-3.5 text-right font-semibold text-[#FF8A5B] whitespace-nowrap">{formatEuros(t.pending_cents)}</td>
                        <td className="px-5 py-3.5 text-right">
                          <button
                            onClick={() => setLinking(t)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold text-black bg-accent-sand hover:bg-accent-sand transition-colors"
                          >
                            <Link2 size={13} /> Rapprocher
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="bg-bg-card border border-border rounded-2xl p-8 text-center">
              <CheckCircle2 size={28} className="mx-auto text-success mb-3" />
              <p className="text-white font-semibold">Tout est rapproché</p>
              <p className="text-sm text-[#8a8a8a] mt-1">Chaque ligne bancaire importée est couverte par des écritures. Importe un nouveau relevé pour continuer.</p>
            </div>
          )}

          {done.length > 0 && (
            <div className="mt-4">
              <button
                onClick={() => setShowDone((v) => !v)}
                className="flex items-center gap-1.5 text-sm text-[#8a8a8a] hover:text-text-secondary transition-colors"
              >
                <ChevronDown size={14} className={`transition-transform ${showDone ? "rotate-180" : ""}`} />
                {showDone ? "Masquer" : "Voir"} les {done.length} ligne{done.length > 1 ? "s" : ""} rapprochée{done.length > 1 ? "s" : ""}
              </button>
              {showDone && (
                <div className="mt-3 bg-bg-card border border-border rounded-2xl overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <tbody>
                        {done.map((t, idx) => (
                          <tr key={t.id} className={`${idx > 0 ? "border-t border-[#1a1a1a]" : ""}`}>
                            <td className="px-5 py-3 text-[#777] whitespace-nowrap">{formatDate(t.booking_date)}</td>
                            <td className="px-5 py-3 font-medium text-text-secondary max-w-xs truncate" title={t.label}>{t.label}</td>
                            <td className="px-5 py-3 text-right whitespace-nowrap" style={{ color: amountColor(t.amount) }}>{formatEuros(t.amount)}</td>
                            <td className="px-5 py-3">
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                                {t.reconciled_manual ? <BadgeCheck size={11} /> : <CheckCircle2 size={11} />} {t.reconciled_manual ? "Manuel" : "Rapprochée"}
                              </span>
                            </td>
                            <td className="px-5 py-3 text-right">
                              <button
                                onClick={() => setLinking(t)}
                                className="inline-flex items-center gap-1.5 text-xs text-[#8a8a8a] hover:text-white transition-colors"
                                title="Voir et gérer les écritures associées"
                              >
                                <Link2 size={12} /> Gérer
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {linking && (
        <LinkPanel bankTx={linking} onClose={() => setLinking(null)} onChanged={refresh} />
      )}
      {showEbConfig && (
        <EbConfigModal onClose={() => setShowEbConfig(false)} onSaved={() => { setShowEbConfig(false); loadAccounts(); }} />
      )}
      {connectingAccount && (
        <BankConnectModal
          account={connectingAccount}
          onClose={() => setConnectingAccount(null)}
          onError={setError}
          onLinked={() => {
            setNotice("Compte bancaire lié. Lance une synchronisation pour importer les opérations.");
            loadAccounts();
            if (selectedId) loadTxs(selectedId);
          }}
        />
      )}
    </div>
  );
}

// ─── Configuration Enable Banking ─────────────────────────────────────────────

function CopyField({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard indisponible : l'utilisateur copie manuellement */ }
  };
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className={labelClass}>{label}</label>
        <button onClick={copy} className="inline-flex items-center gap-1 text-xs text-accent-sand hover:text-white transition-colors">
          {copied ? <><CheckCircle2 size={12} /> Copié</> : <><Copy size={12} /> Copier</>}
        </button>
      </div>
      <textarea readOnly value={value} rows={mono ? 4 : 1} className={`${inputClass} ${mono ? "font-mono text-[11px] leading-tight" : "text-xs"}`} onFocus={(e) => e.target.select()} />
    </div>
  );
}

// Assistant de configuration Enable Banking, intégré à OpenFlow : génère la
// clé en interne, guide l'enregistrement de l'application, récupère l'ID.
function EbConfigModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [loading, setLoading] = useState(true);
  const [configured, setConfigured] = useState(false);
  const [appId, setAppId] = useState("");
  const [certificate, setCertificate] = useState("");
  const [redirectUrl, setRedirectUrl] = useState("");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [reconfigure, setReconfigure] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const c = await api.getBankConfig();
      setConfigured(c.configured);
      setAppId(c.application_id || "");
      setCertificate(c.certificate || "");
      setRedirectUrl(c.redirect_url || c.suggested_redirect_url || "");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const generate = async () => {
    if (certificate && !confirm("Générer une nouvelle clé remplacera l'actuelle : tu devras réenregistrer l'application dans Enable Banking. Continuer ?")) return;
    setGenerating(true);
    setError(null);
    try {
      const res = await api.generateBankKey();
      setCertificate(res.certificate);
      setRedirectUrl(res.redirect_url);
      setAppId("");
      setConfigured(false);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setGenerating(false);
    }
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.putBankConfig({ application_id: appId.trim(), private_key: "", redirect_url: redirectUrl.trim() });
      onSaved();
    } catch (e: any) {
      setError(e.message);
      setSaving(false);
    }
  };

  const showConnected = configured && !reconfigure;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="w-full max-w-lg max-h-[88vh] overflow-y-auto bg-bg-card border border-border rounded-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 bg-bg-card border-b border-[#1a1a1a] px-6 py-4 flex items-start justify-between gap-4 z-10">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-accent-sand/10 border border-accent-sand/20 flex items-center justify-center text-accent-sand">
              <KeyRound size={18} />
            </div>
            <div>
              <h2 className="text-base font-semibold text-white">Connexion automatique (Enable Banking)</h2>
              <p className="text-xs text-[#8a8a8a]">Agrégateur PSD2 gratuit, lecture seule, sans scraping.</p>
            </div>
          </div>
          <button onClick={onClose} className="text-[#8a8a8a] hover:text-white shrink-0"><X size={18} /></button>
        </div>

        <div className="px-6 py-5">
          {error && <div className="mb-4 bg-[#1a0a0a] border border-alert/30 text-alert rounded-xl p-3 text-sm">{error}</div>}

          {loading ? (
            <div className="flex items-center justify-center py-8"><PageLoader fullScreen={false} /></div>
          ) : showConnected ? (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-emerald-400 text-sm">
                <CheckCircle2 size={16} /> Connecteur configuré (application {appId.slice(0, 8)}…).
              </div>
              <p className="text-xs text-[#8a8a8a]">Tu peux maintenant lier un compte via « Connecter à la banque », puis synchroniser.</p>
              <button onClick={() => setReconfigure(true)} className="text-sm text-[#8a8a8a] hover:text-white transition-colors">Reconfigurer</button>
            </div>
          ) : (
            <div className="space-y-5">
              {/* Étape 1 : générer la clé dans OpenFlow */}
              <div>
                <div className="text-xs font-semibold text-white uppercase tracking-wider mb-2">1. Génère ta clé (dans OpenFlow)</div>
                {certificate ? (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2 text-emerald-400 text-xs"><CheckCircle2 size={13} /> Clé générée et enregistrée localement.</div>
                    <CopyField label="Certificat public (à coller dans Enable Banking)" value={certificate} mono />
                    <CopyField label="URL de redirection (à déclarer dans Enable Banking)" value={redirectUrl} />
                    <button onClick={generate} disabled={generating} className="text-xs text-[#8a8a8a] hover:text-white transition-colors">
                      {generating ? "Génération…" : "Régénérer une clé"}
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={generate}
                    disabled={generating}
                    className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-full hover:bg-accent-sand disabled:opacity-50 transition-colors"
                  >
                    <KeyRound size={14} /> {generating ? "Génération…" : "Générer ma clé"}
                  </button>
                )}
              </div>

              {/* Étape 2 : enregistrer l'application chez Enable Banking */}
              {certificate && (
                <div>
                  <div className="text-xs font-semibold text-white uppercase tracking-wider mb-2">2. Enregistre l'application (chez Enable Banking)</div>
                  <ol className="text-xs text-text-secondary space-y-1.5 list-decimal list-inside leading-relaxed">
                    <li><a href="https://enablebanking.com/cp" target="_blank" rel="noopener noreferrer" className="text-accent-sand underline inline-flex items-center gap-1">Ouvre Enable Banking <ExternalLink size={11} /></a> et crée un compte gratuit (lien reçu par email).</li>
                    <li>Onglet « API applications » → environnement <b>Production</b>.</li>
                    <li>Option <b>« Generate outside the browser and import public certificate »</b>.</li>
                    <li>Colle le <b>certificat</b> et l'<b>URL de redirection</b> ci-dessus. Remplis nom, description et emails.</li>
                    <li>Valide, puis copie l'<b>Application ID</b> affiché.</li>
                  </ol>
                </div>
              )}

              {/* Étape 3 : coller l'Application ID */}
              {certificate && (
                <div>
                  <div className="text-xs font-semibold text-white uppercase tracking-wider mb-2">3. Colle ton Application ID</div>
                  <input className={inputClass} value={appId} onChange={(e) => setAppId(e.target.value)} placeholder="ex : cf589be3-3755-465b-…" />
                  <div className="flex items-center gap-3 pt-3">
                    <button
                      onClick={save}
                      disabled={saving || !appId.trim()}
                      className="px-5 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-full hover:bg-accent-sand disabled:opacity-40 transition-colors"
                    >
                      {saving ? "Enregistrement…" : "Terminer la configuration"}
                    </button>
                    {reconfigure && <button onClick={() => setReconfigure(false)} className="text-sm text-[#8a8a8a] hover:text-white transition-colors">Annuler</button>}
                  </div>
                </div>
              )}

              <p className="text-[11px] text-[#555] leading-relaxed border-t border-[#1a1a1a] pt-3">
                Ta clé privée reste dans OpenFlow, jamais transmise à Enable Banking (seul le certificat public l'est).
                Le tier gratuit (« Restricted Production ») permet de lier <b>tes propres comptes</b> sans contrat.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Sélection de la banque + redirection SCA ─────────────────────────────────

// Extrait le paramètre `code` si l'utilisateur colle l'URL de redirection
// complète (https://127.0.0.1:8000/bank-reconciliation?code=...&state=...),
// sinon renvoie la saisie telle quelle (il a collé le code seul).
function extractAuthCode(raw: string): string {
  const s = raw.trim();
  const m = s.match(/[?&]code=([^&\s]+)/);
  if (m) return decodeURIComponent(m[1]);
  return s;
}

function BankConnectModal({
  account, onClose, onError, onLinked,
}: {
  account: Account;
  onClose: () => void;
  onError: (m: string) => void;
  onLinked: () => void;
}) {
  const [banks, setBanks] = useState<{ name: string; country: string; logo: string | null }[]>([]);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Étape 2 : après avoir ouvert la SCA, on attend le code d'autorisation.
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [finalizing, setFinalizing] = useState(false);

  useEffect(() => {
    api.listBanks("FR").then(setBanks).catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, []);

  const connect = async (name: string) => {
    setConnecting(name);
    setError(null);
    try {
      const res = await api.connectBank(account.id, name, "FR");
      if (window.location.protocol === "https:") {
        // OpenFlow est servi en https : la redirection de retour se chargera,
        // et le code sera capté automatiquement au retour (aucun copier/coller).
        window.location.href = res.url;
      } else {
        // Serveur http : la page de retour https ne se charge pas → on ouvre la
        // banque dans un onglet et on récupère le code manuellement.
        setAuthUrl(res.url);
        window.open(res.url, "_blank", "noopener");
      }
    } catch (e: any) {
      setError(e.message);
      onError(e.message);
    } finally {
      setConnecting(null);
    }
  };

  const finalize = async () => {
    const c = extractAuthCode(code);
    if (!c) { setError("Colle le code d'autorisation (ou l'URL de retour)."); return; }
    setFinalizing(true);
    setError(null);
    try {
      await api.finalizeBank(account.id, c);
      onLinked();
      onClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setFinalizing(false);
    }
  };

  const shown = banks.filter((b) => b.name?.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="w-full max-w-md max-h-[85vh] overflow-y-auto bg-bg-card border border-border rounded-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 bg-bg-card border-b border-[#1a1a1a] px-6 py-4 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-white">Connecter « {account.label || account.entity_name} »</h2>
            <p className="text-xs text-[#8a8a8a] mt-0.5">
              {authUrl ? "Authentifie-toi sur le site de ta banque, puis reviens coller le code." : "Choisis ta banque : tu seras redirigé vers son authentification sécurisée."}
            </p>
          </div>
          <button onClick={onClose} className="text-[#8a8a8a] hover:text-white shrink-0"><X size={18} /></button>
        </div>
        <div className="px-6 py-4">
          {error && <div className="mb-3 bg-[#1a0a0a] border border-alert/30 text-alert rounded-xl p-3 text-sm">{error}</div>}

          {authUrl ? (
            <div className="space-y-4">
              <ol className="text-sm text-text-secondary space-y-2 list-decimal list-inside">
                <li>Un onglet s'est ouvert vers ta banque (sinon <a href={authUrl} target="_blank" rel="noopener noreferrer" className="text-accent-sand underline">clique ici</a>).</li>
                <li>Authentifie-toi (identifiant + validation forte).</li>
                <li>Ta banque te renvoie vers une page qui n'affiche rien : copie l'URL de cette page (ou juste la valeur <code className="text-accent-sand">code=…</code>) depuis la barre d'adresse.</li>
                <li>Colle-la ci-dessous.</li>
              </ol>
              <div>
                <label className={labelClass}>Code d'autorisation (ou URL de retour)</label>
                <input className={inputClass} value={code} onChange={(e) => setCode(e.target.value)} placeholder="https://127.0.0.1:8000/bank-reconciliation?code=…" />
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={finalize}
                  disabled={finalizing || !code.trim()}
                  className="px-5 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-full hover:bg-accent-sand disabled:opacity-40 transition-colors"
                >
                  {finalizing ? "Liaison…" : "Lier le compte"}
                </button>
                <button onClick={() => { setAuthUrl(null); setCode(""); }} className="text-sm text-[#8a8a8a] hover:text-white transition-colors">Changer de banque</button>
              </div>
            </div>
          ) : (
            <>
              <div className="relative mb-3">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#555]" />
                <input className={`${inputClass} pl-9`} value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Rechercher (ex : Caisse d'Épargne)" />
              </div>
              {loading ? (
                <div className="flex items-center justify-center py-10"><PageLoader fullScreen={false} /></div>
              ) : shown.length === 0 ? (
                <p className="text-sm text-[#555] py-4 text-center">Aucune banque trouvée.</p>
              ) : (
                <div className="space-y-1.5 max-h-80 overflow-y-auto">
                  {shown.map((b) => (
                    <button
                      key={b.name}
                      onClick={() => connect(b.name)}
                      disabled={connecting !== null}
                      className="w-full flex items-center justify-between gap-3 bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl px-3 py-2.5 hover:border-accent-sand/40 disabled:opacity-50 transition-colors text-left"
                    >
                      <span className="flex items-center gap-2 min-w-0">
                        <Landmark size={14} className="shrink-0 text-[#8a8a8a]" />
                        <span className="text-sm text-white truncate">{b.name}</span>
                      </span>
                      {connecting === b.name ? <RefreshCw size={14} className="animate-spin text-accent-sand" /> : <Wifi size={14} className="text-[#555]" />}
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Barre de comptes ─────────────────────────────────────────────────────────

function AccountBar({
  accounts, selectedId, onSelect, onAdded, onDeleted,
}: {
  accounts: Account[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onAdded: () => void;
  onDeleted: () => void;
}) {
  const [adding, setAdding] = useState(false);
  const selected = accounts.find((a) => a.id === selectedId) || null;

  const deleteAccount = async () => {
    if (!selected) return;
    if (!confirm(`Supprimer le compte « ${selected.label || selected.entity_name} » et toutes ses lignes importées ? Les écritures compta ne sont pas supprimées.`)) return;
    await api.deleteBankAccount(selected.id);
    onDeleted();
  };

  return (
    <div className="flex flex-wrap items-center gap-2 mb-2">
      {accounts.map((a) => (
        <button
          key={a.id}
          onClick={() => onSelect(a.id)}
          className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm border transition-colors ${
            a.id === selectedId
              ? "bg-[#1a1a1a] border-accent-sand/50 text-white"
              : "bg-bg-card border-border text-text-secondary hover:border-[#2a2a2a]"
          }`}
        >
          <Landmark size={14} />
          <span className="font-medium">{a.label || a.entity_name || `Compte ${a.id}`}</span>
          {a.to_reconcile_count > 0 && (
            <span className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full text-[11px] font-semibold bg-[#FF8A5B]/20 text-[#FF8A5B]">
              {a.to_reconcile_count}
            </span>
          )}
        </button>
      ))}
      <button
        onClick={() => setAdding(true)}
        className="flex items-center gap-1.5 px-3 py-2 rounded-full text-sm text-[#8a8a8a] hover:text-white border border-dashed border-[#2a2a2a] hover:border-[#3a3a3a] transition-colors"
      >
        <Plus size={14} /> Compte
      </button>
      {selected && (
        <button
          onClick={deleteAccount}
          className="ml-auto flex items-center gap-1.5 px-3 py-2 rounded-full text-xs text-[#8a8a8a] hover:text-alert transition-colors"
          title="Supprimer ce compte"
        >
          <Trash2 size={13} /> Supprimer
        </button>
      )}

      {adding && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setAdding(false)}>
          <div onClick={(e) => e.stopPropagation()} className="w-full max-w-md">
            <AccountForm onSaved={() => { setAdding(false); onAdded(); }} onCancel={() => setAdding(false)} />
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Formulaire de création de compte ─────────────────────────────────────────

function AccountForm({ onSaved, onCancel }: { onSaved: () => void; onCancel?: () => void }) {
  const [entities, setEntities] = useState<{ id: number; name: string }[]>([]);
  const [entityId, setEntityId] = useState<number | "">("");
  const [label, setLabel] = useState("");
  const [iban, setIban] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getEntities("internal").then((es) => {
      setEntities(es);
      if (es.length === 1) setEntityId(es[0].id);
    }).catch((e) => setError(e.message));
  }, []);

  const save = async () => {
    if (entityId === "") { setError("Choisis l'entité interne titulaire du compte."); return; }
    setSaving(true);
    setError(null);
    try {
      await api.createBankAccount({ entity_id: Number(entityId), label: label.trim(), iban: iban.trim() });
      onSaved();
    } catch (e: any) {
      setError(e.message);
      setSaving(false);
    }
  };

  return (
    <div className="bg-bg-card border border-border rounded-2xl p-6">
      <div className="flex items-center gap-3 mb-5">
        <div className="h-10 w-10 rounded-xl bg-accent-sand/10 border border-accent-sand/20 flex items-center justify-center text-accent-sand">
          <Landmark size={18} />
        </div>
        <div>
          <h2 className="text-base font-semibold text-white">Nouveau compte bancaire</h2>
          <p className="text-xs text-[#8a8a8a]">Rattaché à l'entité interne dont c'est la trésorerie.</p>
        </div>
      </div>
      {error && <div className="mb-4 bg-[#1a0a0a] border border-alert/30 text-alert rounded-xl p-3 text-sm">{error}</div>}
      <div className="space-y-4">
        <div>
          <label className={labelClass}>Entité titulaire</label>
          <select className={inputClass} value={entityId} onChange={(e) => setEntityId(e.target.value === "" ? "" : Number(e.target.value))}>
            <option value="">Choisir une entité…</option>
            {entities.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
        </div>
        <div>
          <label className={labelClass}>Nom du compte</label>
          <input className={inputClass} value={label} onChange={(e) => setLabel(e.target.value)} placeholder="ex : Caisse d'Épargne Pro" />
        </div>
        <div>
          <label className={labelClass}>IBAN (facultatif)</label>
          <input className={inputClass} value={iban} onChange={(e) => setIban(e.target.value)} placeholder="FR76…" />
        </div>
        <div className="flex items-center gap-3 pt-1">
          <button
            onClick={save}
            disabled={saving || entityId === ""}
            className="px-5 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-full hover:bg-accent-sand disabled:opacity-40 transition-colors"
          >
            {saving ? "Création…" : "Créer le compte"}
          </button>
          {onCancel && (
            <button onClick={onCancel} className="text-sm text-[#8a8a8a] hover:text-white transition-colors">Annuler</button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Panneau de rapprochement (associer / dissocier / marquer) ────────────────

function LinkPanel({ bankTx, onClose, onChanged }: { bankTx: BankTx; onClose: () => void; onChanged: () => void }) {
  const [links, setLinks] = useState<TxRow[]>([]);
  const [suggestions, setSuggestions] = useState<TxRow[]>([]);
  const [linked, setLinked] = useState(bankTx.linked_cents);
  const [manual, setManual] = useState(bankTx.reconciled_manual);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const target = Math.abs(bankTx.amount);
  const pending = target - linked;
  // Même règle que le backend : dérivée localement, pas un state à resynchroniser.
  const reconciled = manual || linked === target;

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [l, s] = await Promise.all([
        api.getBankLinks(bankTx.id),
        api.getBankSuggestions(bankTx.id),
      ]);
      setLinks(l.links);
      setLinked(l.linked_cents);
      setManual(l.reconciled_manual);
      setSuggestions(s.suggestions);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [bankTx.id]);

  useEffect(() => { reload(); }, [reload]);

  const associate = async (tx: TxRow) => {
    setBusy(tx.transaction_id);
    setError(null);
    try {
      await api.addBankLink(bankTx.id, tx.transaction_id);
      await reload();
      onChanged();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  const dissociate = async (tx: TxRow) => {
    setBusy(tx.transaction_id);
    setError(null);
    try {
      await api.removeBankLink(bankTx.id, tx.transaction_id);
      await reload();
      onChanged();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  const toggleManual = async () => {
    setError(null);
    try {
      await api.markBankTransaction(bankTx.id, !manual);
      await reload();
      onChanged();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const txMeta = (tx: TxRow) => {
    const flow = [tx.from_entity_name, tx.to_entity_name].filter(Boolean).join(" → ");
    return [formatDate(tx.date), flow].filter(Boolean).join(" · ");
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="w-full max-w-2xl max-h-[85vh] overflow-y-auto bg-bg-card border border-border rounded-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 bg-bg-card border-b border-[#1a1a1a] px-6 py-4 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-white truncate" title={bankTx.label}>{bankTx.label}</h2>
            <p className="text-xs text-[#8a8a8a] mt-0.5">
              {formatDate(bankTx.booking_date)} · <span style={{ color: amountColor(bankTx.amount) }}>{formatEuros(bankTx.amount)}</span> · associe les écritures correspondantes
            </p>
          </div>
          <button onClick={onClose} className="text-[#8a8a8a] hover:text-white shrink-0"><X size={18} /></button>
        </div>

        <div className="px-6 py-4 grid grid-cols-3 gap-3">
          <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl p-3">
            <div className="text-[10px] font-medium text-[#8a8a8a] uppercase tracking-wider">Montant</div>
            <div className="text-base font-bold" style={{ color: amountColor(bankTx.amount) }}>{formatEuros(target)}</div>
          </div>
          <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl p-3">
            <div className="text-[10px] font-medium text-[#8a8a8a] uppercase tracking-wider">Associé</div>
            <div className="text-base font-bold text-white">{formatEuros(linked)}</div>
          </div>
          <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl p-3">
            <div className="text-[10px] font-medium text-[#8a8a8a] uppercase tracking-wider">Reste</div>
            <div className={`text-base font-bold ${pending === 0 ? "text-success" : "text-[#FF8A5B]"}`}>{formatEuros(pending)}</div>
          </div>
        </div>

        <div className="px-6 pb-2 flex items-center justify-between gap-3">
          <div className="text-xs text-[#8a8a8a]">
            {reconciled ? (
              <span className="inline-flex items-center gap-1 text-emerald-400"><CheckCircle2 size={13} /> Ligne rapprochée{manual ? " (manuel)" : ""}</span>
            ) : (
              <span className="inline-flex items-center gap-1 text-[#FF8A5B]"><GitCompare size={13} /> Rapprochement incomplet</span>
            )}
          </div>
          <button
            onClick={toggleManual}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-colors border ${
              manual
                ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/25"
                : "bg-[#1a1a1a] text-text-secondary border-[#2a2a2a] hover:text-white"
            }`}
            title="Forcer le statut rapproché même si les montants ne collent pas exactement"
          >
            <BadgeCheck size={13} /> {manual ? "Annuler le marquage manuel" : "Marquer rapprochée manuellement"}
          </button>
        </div>

        {error && <div className="mx-6 mb-3 bg-[#1a0a0a] border border-alert/30 text-alert rounded-xl p-3 text-sm">{error}</div>}

        {loading ? (
          <div className="flex items-center justify-center py-12"><PageLoader fullScreen={false} /></div>
        ) : (
          <>
            <div className="px-6 pb-2">
              <div className="text-xs font-medium text-[#8a8a8a] uppercase tracking-wider mb-2">Écritures associées</div>
              {links.length === 0 ? (
                <p className="text-sm text-[#555] py-2">Aucune écriture associée pour l'instant.</p>
              ) : (
                <div className="space-y-1.5">
                  {links.map((tx) => (
                    <div key={tx.transaction_id} className="flex items-center justify-between gap-3 bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl px-3 py-2.5">
                      <div className="min-w-0">
                        <div className="text-sm text-white truncate">{tx.label}</div>
                        <div className="text-xs text-[#8a8a8a] truncate">{txMeta(tx)}</div>
                      </div>
                      <div className="flex items-center gap-3 whitespace-nowrap">
                        <span className="text-sm font-semibold text-text-secondary">{formatEuros(tx.amount)}</span>
                        <button onClick={() => dissociate(tx)} disabled={busy === tx.transaction_id} className="text-[#8a8a8a] hover:text-alert disabled:opacity-40" title="Dissocier">
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="px-6 py-4">
              <div className="text-xs font-medium text-[#8a8a8a] uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <Search size={12} /> Écritures suggérées
              </div>
              {suggestions.length === 0 ? (
                <p className="text-sm text-[#555] py-2">
                  {pending === 0 ? "Ligne entièrement couverte." : "Aucune écriture disponible du même sens à associer."}
                </p>
              ) : (
                <div className="space-y-1.5">
                  {suggestions.map((tx) => (
                    <div key={tx.transaction_id} className="flex items-center justify-between gap-3 bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl px-3 py-2.5 hover:border-[#2a2a2a]">
                      <div className="min-w-0">
                        <div className="text-sm text-white truncate">{tx.label}</div>
                        <div className="text-xs text-[#8a8a8a] truncate">{txMeta(tx)}</div>
                      </div>
                      <div className="flex items-center gap-3 whitespace-nowrap">
                        <span className="text-sm font-semibold text-text-secondary">{formatEuros(tx.amount)}</span>
                        <button onClick={() => associate(tx)} disabled={busy === tx.transaction_id} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold text-black bg-accent-sand hover:bg-accent-sand disabled:opacity-40">
                          <Plus size={12} /> Associer
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
