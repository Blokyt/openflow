import { useCallback, useEffect, useState } from "react";
import {
  Wallet, ArrowRight, Plus, Trash2, Pencil, Check, X, AlertCircle, Link2, RefreshCw,
} from "lucide-react";
import { api } from "../../api";
import { formatEuros, formatDate, eurosToCents, centsToEuros } from "../../utils/format";
import { inputClass, labelClass } from "../../core/formStyles";
import PageLoader from "../../core/PageLoader";

type Pocket = {
  id: number;
  name: string;
  reference_cents: number;
  reference_date: string;
  bank_account_id: number | null;
  balance_cents: number;
  bank_balance_cents: number | null;
};

type Transfer = {
  id: number;
  from_pocket_id: number;
  to_pocket_id: number;
  amount_cents: number;
  date: string;
  label: string;
  from_name: string | null;
  to_name: string | null;
};

const todayISO = () => new Date().toISOString().slice(0, 10);

export default function TreasuryPage() {
  const [pockets, setPockets] = useState<Pocket[]>([]);
  const [total, setTotal] = useState(0);
  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [bankAccounts, setBankAccounts] = useState<{ id: number; label: string; entity_name: string | null }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [pk, tr, ba] = await Promise.all([
        api.getPockets(),
        api.getPocketTransfers(),
        api.getBankAccounts().catch(() => []),
      ]);
      setPockets(pk.pockets);
      setTotal(pk.total_cents);
      setTransfers(tr);
      setBankAccounts(ba);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const applyResult = (res: { pockets: Pocket[]; total_cents: number }) => {
    setPockets(res.pockets);
    setTotal(res.total_cents);
  };

  if (loading) {
    return (
      <div className="p-8">
        <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>Trésorerie</h1>
        <div className="flex items-center justify-center py-20"><PageLoader fullScreen={false} /></div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="flex items-start justify-between mb-6 gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>Trésorerie</h1>
          <p className="text-sm text-[#8a8a8a] mt-1">Répartition de ton argent en poches. Le total ne change pas quand tu transfères d'une poche à l'autre.</p>
        </div>
      </div>

      {error && (
        <div className="mb-4 bg-[#1a0a0a] border border-alert/30 text-alert rounded-2xl p-4 text-sm flex items-start justify-between gap-3">
          <span className="flex items-center gap-2"><AlertCircle size={16} /> {error}</span>
          <button onClick={() => setError(null)} className="text-alert/70 hover:text-alert"><X size={16} /></button>
        </div>
      )}

      {/* Total */}
      <div className="bg-bg-card border border-border rounded-2xl p-6 mb-6">
        <div className="text-xs font-medium text-[#8a8a8a] uppercase tracking-wider mb-2">Total trésorerie</div>
        <div className="text-4xl font-bold text-accent-sand">{formatEuros(total)}</div>
        <div className="text-xs text-[#8a8a8a] mt-2">{pockets.map((p) => `${p.name} ${formatEuros(p.balance_cents)}`).join("  ·  ")}</div>
      </div>

      {/* Poches */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
        {pockets.map((p) => (
          <PocketCard key={p.id} pocket={p} bankAccounts={bankAccounts} onChanged={applyResult} onError={setError} onReload={load} />
        ))}
        <NewPocketCard onCreated={applyResult} onError={setError} />
      </div>

      {/* Transferts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <TransferForm pockets={pockets} onDone={() => load()} onError={setError} />
        </div>
        <div className="lg:col-span-2">
          <TransferList transfers={transfers} onDeleted={() => load()} onError={setError} />
        </div>
      </div>
    </div>
  );
}

// ─── Carte poche ──────────────────────────────────────────────────────────────

function PocketCard({
  pocket, bankAccounts, onChanged, onError, onReload,
}: {
  pocket: Pocket;
  bankAccounts: { id: number; label: string; entity_name: string | null }[];
  onChanged: (r: { pockets: Pocket[]; total_cents: number }) => void;
  onError: (m: string) => void;
  onReload: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(pocket.name);
  const [amount, setAmount] = useState(String(centsToEuros(pocket.reference_cents)));
  const [date, setDate] = useState(pocket.reference_date || todayISO());
  const [linkId, setLinkId] = useState(pocket.bank_account_id ?? 0);
  const [busy, setBusy] = useState(false);

  const ecart = pocket.bank_balance_cents != null ? pocket.balance_cents - pocket.bank_balance_cents : null;

  const save = async () => {
    setBusy(true);
    try {
      const res = await api.updatePocket(pocket.id, {
        name: name.trim(),
        reference_cents: eurosToCents(amount),
        reference_date: date,
        bank_account_id: linkId,
      });
      onChanged(res);
      setEditing(false);
    } catch (e: any) { onError(e.message); } finally { setBusy(false); }
  };

  const align = async () => {
    setBusy(true);
    try { onChanged(await api.alignPocketBank(pocket.id)); }
    catch (e: any) { onError(e.message); } finally { setBusy(false); }
  };

  const remove = async () => {
    if (!confirm(`Supprimer la poche « ${pocket.name} » ?`)) return;
    try { onChanged(await api.deletePocket(pocket.id)); }
    catch (e: any) { onError(e.message); }
  };

  if (editing) {
    return (
      <div className="bg-bg-card border border-accent-sand/40 rounded-2xl p-5 space-y-3">
        <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} placeholder="Nom de la poche" />
        <div>
          <label className={labelClass}>Solde de référence (€)</label>
          <input className={inputClass} type="number" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </div>
        <div>
          <label className={labelClass}>À la date du</label>
          <input className={inputClass} type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </div>
        <div>
          <label className={labelClass}>Relier à un compte bancaire (facultatif)</label>
          <select className={inputClass} value={linkId} onChange={(e) => setLinkId(Number(e.target.value))}>
            <option value={0}>Aucun</option>
            {bankAccounts.map((b) => <option key={b.id} value={b.id}>{b.label || b.entity_name || `Compte ${b.id}`}</option>)}
          </select>
        </div>
        <div className="flex items-center gap-2 pt-1">
          <button onClick={save} disabled={busy} className="inline-flex items-center gap-1 px-4 py-2 text-sm font-semibold text-black bg-accent-sand rounded-full disabled:opacity-40"><Check size={14} /> Enregistrer</button>
          <button onClick={() => setEditing(false)} className="text-sm text-[#8a8a8a] hover:text-white">Annuler</button>
          <button onClick={remove} className="ml-auto text-[#8a8a8a] hover:text-alert" title="Supprimer la poche"><Trash2 size={15} /></button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-bg-card border border-border rounded-2xl p-5">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 text-[#8a8a8a]"><Wallet size={14} /><span className="text-xs font-medium uppercase tracking-wider">{pocket.name}</span></div>
        <button onClick={() => { setName(pocket.name); setAmount(String(centsToEuros(pocket.reference_cents))); setDate(pocket.reference_date || todayISO()); setLinkId(pocket.bank_account_id ?? 0); setEditing(true); }} className="text-[#8a8a8a] hover:text-accent-sand"><Pencil size={13} /></button>
      </div>
      <div className="text-2xl font-bold text-white">{formatEuros(pocket.balance_cents)}</div>
      {pocket.bank_balance_cents != null && (
        <div className="mt-3 pt-3 border-t border-[#1a1a1a] text-xs">
          <div className="flex items-center gap-1.5 text-[#8a8a8a]"><Link2 size={11} /> Banque : {formatEuros(pocket.bank_balance_cents)}</div>
          {ecart !== null && ecart !== 0 ? (
            <div className="flex items-center justify-between mt-1.5">
              <span className="text-[#FF8A5B]">Écart : {formatEuros(ecart)}</span>
              <button onClick={align} disabled={busy} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold text-black bg-accent-sand disabled:opacity-40"><RefreshCw size={11} /> Aligner</button>
            </div>
          ) : (
            <div className="text-success mt-1.5">Aligné sur la banque</div>
          )}
        </div>
      )}
    </div>
  );
}

function NewPocketCard({ onCreated, onError }: { onCreated: (r: { pockets: Pocket[]; total_cents: number }) => void; onError: (m: string) => void }) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const create = async () => {
    if (!name.trim()) return;
    try { onCreated(await api.createPocket(name.trim())); setName(""); setAdding(false); }
    catch (e: any) { onError(e.message); }
  };
  if (!adding) {
    return (
      <button onClick={() => setAdding(true)} className="border border-dashed border-[#2a2a2a] rounded-2xl p-5 text-sm text-[#8a8a8a] hover:text-white hover:border-[#3a3a3a] flex items-center justify-center gap-2 transition-colors">
        <Plus size={15} /> Ajouter une poche
      </button>
    );
  }
  return (
    <div className="bg-bg-card border border-accent-sand/40 rounded-2xl p-5 space-y-2">
      <input className={inputClass} value={name} autoFocus onChange={(e) => setName(e.target.value)} placeholder="Nom (ex : Coffre)" onKeyDown={(e) => e.key === "Enter" && create()} />
      <div className="flex items-center gap-2">
        <button onClick={create} className="px-4 py-2 text-sm font-semibold text-black bg-accent-sand rounded-full">Créer</button>
        <button onClick={() => setAdding(false)} className="text-sm text-[#8a8a8a] hover:text-white">Annuler</button>
      </div>
    </div>
  );
}

// ─── Transferts ───────────────────────────────────────────────────────────────

function TransferForm({ pockets, onDone, onError }: { pockets: Pocket[]; onDone: () => void; onError: (m: string) => void }) {
  const [fromId, setFromId] = useState<number | "">("");
  const [toId, setToId] = useState<number | "">("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(todayISO());
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (fromId === "" || toId === "") { onError("Choisis les poches source et destination."); return; }
    const cents = eurosToCents(amount);
    if (cents <= 0) { onError("Montant invalide."); return; }
    setBusy(true);
    try {
      await api.createPocketTransfer({ from_pocket_id: Number(fromId), to_pocket_id: Number(toId), amount_cents: cents, date, label: label.trim() });
      setAmount(""); setLabel("");
      onDone();
    } catch (e: any) { onError(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="bg-bg-card border border-border rounded-2xl p-5">
      <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2"><ArrowRight size={15} className="text-accent-sand" /> Nouveau transfert</h2>
      <div className="space-y-3">
        <div>
          <label className={labelClass}>De</label>
          <select className={inputClass} value={fromId} onChange={(e) => setFromId(e.target.value === "" ? "" : Number(e.target.value))}>
            <option value="">Poche source…</option>
            {pockets.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div>
          <label className={labelClass}>Vers</label>
          <select className={inputClass} value={toId} onChange={(e) => setToId(e.target.value === "" ? "" : Number(e.target.value))}>
            <option value="">Poche destination…</option>
            {pockets.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div>
          <label className={labelClass}>Montant (€)</label>
          <input className={inputClass} type="number" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0,00" />
        </div>
        <div>
          <label className={labelClass}>Date</label>
          <input className={inputClass} type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </div>
        <div>
          <label className={labelClass}>Libellé (facultatif)</label>
          <input className={inputClass} value={label} onChange={(e) => setLabel(e.target.value)} placeholder="ex : Retrait DAB" />
        </div>
        <button onClick={submit} disabled={busy} className="w-full px-4 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-full disabled:opacity-40">
          {busy ? "Enregistrement…" : "Transférer"}
        </button>
      </div>
    </div>
  );
}

function TransferList({ transfers, onDeleted, onError }: { transfers: Transfer[]; onDeleted: () => void; onError: (m: string) => void }) {
  const remove = async (id: number) => {
    try { await api.deletePocketTransfer(id); onDeleted(); }
    catch (e: any) { onError(e.message); }
  };
  return (
    <div className="bg-bg-card border border-border rounded-2xl overflow-hidden">
      <div className="px-5 py-3 border-b border-[#1a1a1a] text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Transferts récents</div>
      {transfers.length === 0 ? (
        <p className="text-sm text-[#555] px-5 py-8 text-center">Aucun transfert pour l'instant.</p>
      ) : (
        <div className="divide-y divide-[#1a1a1a]">
          {transfers.map((t) => (
            <div key={t.id} className="flex items-center justify-between gap-3 px-5 py-3">
              <div className="min-w-0">
                <div className="text-sm text-white flex items-center gap-1.5">
                  {t.from_name || "?"} <ArrowRight size={12} className="text-[#8a8a8a]" /> {t.to_name || "?"}
                </div>
                <div className="text-xs text-[#8a8a8a] truncate">{formatDate(t.date)}{t.label ? ` · ${t.label}` : ""}</div>
              </div>
              <div className="flex items-center gap-3 whitespace-nowrap">
                <span className="text-sm font-semibold text-white">{formatEuros(t.amount_cents)}</span>
                <button onClick={() => remove(t.id)} className="text-[#8a8a8a] hover:text-alert" title="Supprimer"><Trash2 size={15} /></button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
