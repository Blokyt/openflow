import { useCallback, useEffect, useState } from "react";
import {
  Wallet, ArrowRight, Plus, Trash2, Pencil, X, AlertCircle, Link2, Landmark, Percent, TrendingUp,
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
  annual_rate: number | null;
  balance_cents: number;
  bank_linked: boolean;
  bank_balance_cents: number | null;
  synced: boolean | null;
};

type Movement = {
  id: number;
  from_pocket_id: number | null;
  to_pocket_id: number | null;
  amount_cents: number;
  date: string;
  label: string;
  from_name: string | null;
  to_name: string | null;
};

type Prefill = { toId: number; amount: string; label: string } | null;
const todayISO = () => new Date().toISOString().slice(0, 10);

export default function TreasuryPage() {
  const [pockets, setPockets] = useState<Pocket[]>([]);
  const [total, setTotal] = useState(0);
  const [movements, setMovements] = useState<Movement[]>([]);
  const [bankAccounts, setBankAccounts] = useState<{ id: number; label: string; entity_name: string | null }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [prefill, setPrefill] = useState<Prefill>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [pk, mv, ba] = await Promise.all([
        api.getPockets(),
        api.getPocketMovements(),
        api.getBankAccounts().catch(() => []),
      ]);
      setPockets(pk.pockets);
      setTotal(pk.total_cents);
      setMovements(mv);
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

  const manualPockets = pockets.filter((p) => !p.bank_linked);

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
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>Trésorerie</h1>
        <p className="text-sm text-[#8a8a8a] mt-1">Où se trouve l'argent de l'asso. Un transfert entre poches ne change pas le total ; une rentrée l'augmente, une sortie le diminue.</p>
      </div>

      {error && (
        <div className="mb-4 bg-[#1a0a0a] border border-alert/30 text-alert rounded-2xl p-4 text-sm flex items-start justify-between gap-3">
          <span className="flex items-center gap-2"><AlertCircle size={16} /> {error}</span>
          <button onClick={() => setError(null)} className="text-alert/70 hover:text-alert"><X size={16} /></button>
        </div>
      )}

      <div className="bg-bg-card border border-border rounded-2xl p-6 mb-6">
        <div className="text-xs font-medium text-[#8a8a8a] uppercase tracking-wider mb-2">Total trésorerie</div>
        <div className="text-4xl font-bold text-accent-sand">{formatEuros(total)}</div>
        <div className="text-xs text-[#8a8a8a] mt-2">{pockets.map((p) => `${p.name} ${formatEuros(p.balance_cents)}`).join("  ·  ")}</div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
        {pockets.map((p) => (
          <PocketCard key={p.id} pocket={p} bankAccounts={bankAccounts} onChanged={applyResult} onError={setError}
            onPayInterest={(toId, amount, label) => setPrefill({ toId, amount, label })} />
        ))}
        <NewPocketCard onCreated={applyResult} onError={setError} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <MovementForm manualPockets={manualPockets} prefill={prefill} onConsumePrefill={() => setPrefill(null)} onDone={load} onError={setError} />
        </div>
        <div className="lg:col-span-2">
          <MovementList movements={movements} onDeleted={load} onError={setError} />
        </div>
      </div>
    </div>
  );
}

// ─── Carte poche ──────────────────────────────────────────────────────────────

function PocketCard({
  pocket, bankAccounts, onChanged, onError, onPayInterest,
}: {
  pocket: Pocket;
  bankAccounts: { id: number; label: string; entity_name: string | null }[];
  onChanged: (r: { pockets: Pocket[]; total_cents: number }) => void;
  onError: (m: string) => void;
  onPayInterest: (toId: number, amount: string, label: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(pocket.name);
  const [amount, setAmount] = useState(String(centsToEuros(pocket.reference_cents)));
  const [date, setDate] = useState(pocket.reference_date || todayISO());
  const [linkId, setLinkId] = useState(pocket.bank_account_id ?? 0);
  const [rate, setRate] = useState(pocket.annual_rate != null ? String(pocket.annual_rate) : "");
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      const res = await api.updatePocket(pocket.id, {
        name: name.trim(),
        reference_cents: eurosToCents(amount),
        reference_date: date,
        bank_account_id: linkId,
        annual_rate: rate.trim() === "" ? 0 : parseFloat(rate.replace(",", ".")),
      });
      onChanged(res);
      setEditing(false);
    } catch (e: any) { onError(e.message); } finally { setBusy(false); }
  };

  const remove = async () => {
    if (!confirm(`Supprimer la poche « ${pocket.name} » ?`)) return;
    try { onChanged(await api.deletePocket(pocket.id)); } catch (e: any) { onError(e.message); }
  };

  const payInterest = () => {
    const interest = Math.round(pocket.balance_cents * (pocket.annual_rate || 0) / 100);
    onPayInterest(pocket.id, String(centsToEuros(interest)), "Intérêts");
  };

  if (editing) {
    return (
      <div className="bg-bg-card border border-accent-sand/40 rounded-2xl p-5 space-y-3">
        <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} placeholder="Nom de la poche" />
        {bankAccounts.length === 0 ? (
          <p className="text-xs text-[#8a8a8a]">Poche manuelle. Pour synchroniser une poche avec un compte bancaire, connecte-le d'abord dans « Rapprochement bancaire ».</p>
        ) : (
          <label className="flex items-center gap-2.5 text-sm text-text-secondary cursor-pointer py-1">
            <input
              type="checkbox"
              checked={linkId !== 0}
              onChange={(e) => setLinkId(e.target.checked ? (bankAccounts.some((b) => b.id === linkId) ? linkId : bankAccounts[0].id) : 0)}
              className="accent-accent-sand h-4 w-4"
            />
            <span>Synchroniser avec la banque <span className="text-[#8a8a8a]">(solde automatique, en lecture seule)</span></span>
          </label>
        )}
        {linkId !== 0 && bankAccounts.length > 1 && (
          <div>
            <label className={labelClass}>Compte bancaire</label>
            <select className={inputClass} value={linkId} onChange={(e) => setLinkId(Number(e.target.value))}>
              {bankAccounts.map((b) => <option key={b.id} value={b.id}>{b.label || b.entity_name || `Compte ${b.id}`}</option>)}
            </select>
          </div>
        )}
        {linkId === 0 && (
          <>
            <div>
              <label className={labelClass}>Solde actuel (€)</label>
              <input className={inputClass} type="number" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </div>
            <div>
              <label className={labelClass}>À la date du</label>
              <input className={inputClass} type="date" value={date} onChange={(e) => setDate(e.target.value)} />
              <p className="text-[11px] text-[#555] mt-1">Les mouvements postérieurs à cette date font évoluer le solde.</p>
            </div>
            <div>
              <label className={labelClass}>Taux annuel (%) — pour un livret, facultatif</label>
              <input className={inputClass} type="number" step="0.01" value={rate} onChange={(e) => setRate(e.target.value)} placeholder="ex : 3" />
            </div>
          </>
        )}
        {linkId !== 0 && <p className="text-xs text-[#8a8a8a]">Solde synchronisé avec la banque : pas de saisie manuelle.</p>}
        <div className="flex items-center gap-2 pt-1">
          <button onClick={save} disabled={busy} className="px-4 py-2 text-sm font-semibold text-black bg-accent-sand rounded-full disabled:opacity-40">Enregistrer</button>
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
        <button onClick={() => { setName(pocket.name); setAmount(String(centsToEuros(pocket.reference_cents))); setDate(pocket.reference_date || todayISO()); setLinkId(pocket.bank_account_id ?? 0); setRate(pocket.annual_rate != null ? String(pocket.annual_rate) : ""); setEditing(true); }} className="text-[#8a8a8a] hover:text-accent-sand"><Pencil size={13} /></button>
      </div>
      <div className="text-2xl font-bold text-white">{formatEuros(pocket.balance_cents)}</div>

      {pocket.bank_linked ? (
        <div className="mt-3 pt-3 border-t border-[#1a1a1a] text-xs flex items-center gap-1.5">
          {pocket.synced ? (
            <span className="inline-flex items-center gap-1.5 text-success"><Landmark size={11} /> Synchronisé avec la banque</span>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-[#FF8A5B]"><Link2 size={11} /> Relié — synchronise dans « Rapprochement bancaire »</span>
          )}
        </div>
      ) : pocket.annual_rate != null ? (
        <div className="mt-3 pt-3 border-t border-[#1a1a1a] flex items-center justify-between text-xs">
          <span className="inline-flex items-center gap-1 text-[#8a8a8a]"><Percent size={11} /> {pocket.annual_rate}% / an</span>
          <button onClick={payInterest} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold text-black bg-accent-sand"><TrendingUp size={11} /> Verser les intérêts</button>
        </div>
      ) : null}
    </div>
  );
}

function NewPocketCard({ onCreated, onError }: { onCreated: (r: { pockets: Pocket[]; total_cents: number }) => void; onError: (m: string) => void }) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const create = async () => {
    if (!name.trim()) return;
    try { onCreated(await api.createPocket(name.trim())); setName(""); setAdding(false); } catch (e: any) { onError(e.message); }
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

// ─── Mouvements ───────────────────────────────────────────────────────────────

type MoveType = "in" | "out" | "transfer";

function MovementForm({
  manualPockets, prefill, onConsumePrefill, onDone, onError,
}: {
  manualPockets: Pocket[];
  prefill: Prefill;
  onConsumePrefill: () => void;
  onDone: () => void;
  onError: (m: string) => void;
}) {
  const [type, setType] = useState<MoveType>("transfer");
  const [fromId, setFromId] = useState<number | "">("");
  const [toId, setToId] = useState<number | "">("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(todayISO());
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);

  // Pré-remplissage "Verser les intérêts" → une rentrée sur la poche.
  useEffect(() => {
    if (prefill) {
      setType("in");
      setToId(prefill.toId);
      setAmount(prefill.amount);
      setLabel(prefill.label);
      onConsumePrefill();
    }
  }, [prefill, onConsumePrefill]);

  const submit = async () => {
    const cents = eurosToCents(amount);
    if (cents <= 0) { onError("Montant invalide."); return; }
    const from = type === "out" || type === "transfer" ? fromId : "";
    const to = type === "in" || type === "transfer" ? toId : "";
    if ((type !== "in" && from === "") || (type !== "out" && to === "")) { onError("Choisis la ou les poches."); return; }
    setBusy(true);
    try {
      await api.createPocketMovement({
        from_pocket_id: from === "" ? null : Number(from),
        to_pocket_id: to === "" ? null : Number(to),
        amount_cents: cents, date, label: label.trim(),
      });
      setAmount(""); setLabel("");
      onDone();
    } catch (e: any) { onError(e.message); } finally { setBusy(false); }
  };

  const TypeBtn = ({ v, txt }: { v: MoveType; txt: string }) => (
    <button onClick={() => setType(v)} className={`flex-1 px-2 py-1.5 rounded-lg text-xs font-semibold transition-colors ${type === v ? "bg-accent-sand text-black" : "bg-[#1a1a1a] text-text-secondary hover:text-white"}`}>{txt}</button>
  );

  return (
    <div className="bg-bg-card border border-border rounded-2xl p-5">
      <h2 className="text-sm font-semibold text-white mb-4">Nouveau mouvement</h2>
      <div className="flex gap-1.5 mb-4">
        <TypeBtn v="in" txt="Rentrée" />
        <TypeBtn v="out" txt="Sortie" />
        <TypeBtn v="transfer" txt="Transfert" />
      </div>
      <div className="space-y-3">
        {(type === "out" || type === "transfer") && (
          <div>
            <label className={labelClass}>{type === "transfer" ? "De" : "Poche"}</label>
            <select className={inputClass} value={fromId} onChange={(e) => setFromId(e.target.value === "" ? "" : Number(e.target.value))}>
              <option value="">Choisir…</option>
              {manualPockets.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
        )}
        {(type === "in" || type === "transfer") && (
          <div>
            <label className={labelClass}>{type === "transfer" ? "Vers" : "Poche"}</label>
            <select className={inputClass} value={toId} onChange={(e) => setToId(e.target.value === "" ? "" : Number(e.target.value))}>
              <option value="">Choisir…</option>
              {manualPockets.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
        )}
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
          <input className={inputClass} value={label} onChange={(e) => setLabel(e.target.value)} placeholder="ex : Retrait DAB, Intérêts…" />
        </div>
        <button onClick={submit} disabled={busy} className="w-full px-4 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-full disabled:opacity-40">
          {busy ? "Enregistrement…" : "Enregistrer"}
        </button>
        <p className="text-[11px] text-[#555]">Seules les poches manuelles apparaissent : une poche synchronisée avec la banque suit automatiquement le solde réel.</p>
      </div>
    </div>
  );
}

function MovementList({ movements, onDeleted, onError }: { movements: Movement[]; onDeleted: () => void; onError: (m: string) => void }) {
  const remove = async (id: number) => {
    try { await api.deletePocketMovement(id); onDeleted(); } catch (e: any) { onError(e.message); }
  };
  const describe = (m: Movement) => {
    if (m.from_name && m.to_name) return <span className="flex items-center gap-1.5 text-white">{m.from_name} <ArrowRight size={12} className="text-[#8a8a8a]" /> {m.to_name}</span>;
    if (m.to_name) return <span className="text-success">Rentrée → {m.to_name}</span>;
    return <span className="text-[#FF8A5B]">Sortie ← {m.from_name}</span>;
  };
  return (
    <div className="bg-bg-card border border-border rounded-2xl overflow-hidden">
      <div className="px-5 py-3 border-b border-[#1a1a1a] text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Mouvements récents</div>
      {movements.length === 0 ? (
        <p className="text-sm text-[#555] px-5 py-8 text-center">Aucun mouvement pour l'instant.</p>
      ) : (
        <div className="divide-y divide-[#1a1a1a]">
          {movements.map((m) => (
            <div key={m.id} className="flex items-center justify-between gap-3 px-5 py-3">
              <div className="min-w-0">
                <div className="text-sm">{describe(m)}</div>
                <div className="text-xs text-[#8a8a8a] truncate">{formatDate(m.date)}{m.label ? ` · ${m.label}` : ""}</div>
              </div>
              <div className="flex items-center gap-3 whitespace-nowrap">
                <span className="text-sm font-semibold text-white">{formatEuros(m.amount_cents)}</span>
                <button onClick={() => remove(m.id)} className="text-[#8a8a8a] hover:text-alert" title="Supprimer"><Trash2 size={15} /></button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
