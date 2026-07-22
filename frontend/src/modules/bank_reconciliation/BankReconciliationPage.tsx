import { useCallback, useEffect, useRef, useState } from "react";
import {
  Upload, Landmark, Link2, CheckCircle2, AlertCircle, X, Plus, Trash2, Search,
  ChevronDown, GitCompare, BadgeCheck,
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
  const fileRef = useRef<HTMLInputElement>(null);

  const loadAccounts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const accs = await api.getBankAccounts();
      setAccounts(accs);
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
      const [pending, reconciled] = await Promise.all([
        api.getBankTransactions(accountId, "pending"),
        api.getBankTransactions(accountId, "reconciled"),
      ]);
      setTxs([...pending, ...reconciled]);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoadingTxs(false);
    }
  }, []);

  useEffect(() => { loadAccounts(); }, [loadAccounts]);
  useEffect(() => { if (selectedId) loadTxs(selectedId); }, [selectedId, loadTxs]);

  const onImport = async (file: File) => {
    if (!selectedId) return;
    setImporting(true);
    setError(null);
    setNotice(null);
    try {
      const res = await api.importBankStatement(selectedId, file);
      setNotice(`${res.imported} nouvelle${res.imported > 1 ? "s" : ""} ligne${res.imported > 1 ? "s" : ""} importée${res.imported > 1 ? "s" : ""}` +
        (res.skipped > 0 ? ` (${res.skipped} déjà présente${res.skipped > 1 ? "s" : ""}, ignorée${res.skipped > 1 ? "s" : ""})` : "") + ".");
      await Promise.all([loadTxs(selectedId), loadAccounts()]);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const afterLinkChange = async () => {
    if (selectedId) await Promise.all([loadTxs(selectedId), loadAccounts()]);
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
        <div className="flex items-center gap-3">
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.ofx,.qfx,text/csv,application/x-ofx"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) onImport(f); }}
          />
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
        <LinkPanel bankTx={linking} onClose={() => setLinking(null)} onChanged={afterLinkChange} />
      )}
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
  const [reconciled, setReconciled] = useState(bankTx.reconciled);
  const [manual, setManual] = useState(bankTx.reconciled_manual);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const target = Math.abs(bankTx.amount);
  const pending = target - linked;

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
      setReconciled(l.reconciled);
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
