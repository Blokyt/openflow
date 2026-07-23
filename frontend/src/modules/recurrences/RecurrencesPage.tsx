import { useCallback, useEffect, useState } from "react";
import { Repeat, Plus, Trash2, Pencil, X, AlertCircle, CheckCircle2, RefreshCw } from "lucide-react";
import { api } from "../../api";
import { formatEuros, eurosToCents, centsToEuros } from "../../utils/format";
import { inputClass, labelClass } from "../../core/formStyles";
import EmptyState from "../../core/EmptyState";
import PageLoader from "../../core/PageLoader";
import ConfirmDialog from "../../core/ConfirmDialog";

type Rec = {
  id: number;
  label: string;
  description: string;
  amount_cents: number;
  from_entity_id: number;
  to_entity_id: number;
  category_id: number | null;
  frequency: string;
  start_date: string;
  end_date: string | null;
  last_run_date: string | null;
  active: number;
  from_entity_name: string | null;
  to_entity_name: string | null;
  category_name: string | null;
};

type Entity = { id: number; name: string };
type Category = { id: number; name: string };

const FREQ_LABELS: Record<string, string> = { weekly: "Chaque semaine", monthly: "Chaque mois", yearly: "Chaque année" };
const todayISO = () => new Date().toISOString().slice(0, 10);

export default function RecurrencesPage() {
  const [recs, setRecs] = useState<Rec[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editing, setEditing] = useState<Rec | "new" | null>(null);

  const load = useCallback(async () => {
    try {
      const [r, e, c] = await Promise.all([
        api.getRecurrences(),
        api.getEntities(),
        api.getCategories().catch(() => []),
      ]);
      setRecs(r);
      setEntities(e);
      setCategories(c);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Au chargement : génère automatiquement les échéances dues, puis charge.
  useEffect(() => {
    (async () => {
      try {
        const res = await api.runRecurrences();
        if (res.generated > 0) setNotice(`${res.generated} transaction${res.generated > 1 ? "s" : ""} générée${res.generated > 1 ? "s" : ""} automatiquement.`);
      } catch { /* silencieux : la génération n'est pas bloquante */ }
      await load();
    })();
  }, [load]);

  const runNow = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await api.runRecurrences();
      setNotice(res.generated > 0
        ? `${res.generated} transaction${res.generated > 1 ? "s" : ""} générée${res.generated > 1 ? "s" : ""}.`
        : "Aucune échéance en attente.");
      await load();
    } catch (e: any) { setError(e.message); } finally { setRunning(false); }
  };

  if (loading) {
    return (
      <div className="p-8">
        <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>Récurrences</h1>
        <div className="flex items-center justify-center py-20"><PageLoader fullScreen={false} /></div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="flex items-start justify-between mb-6 gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>Récurrences</h1>
          <p className="text-sm text-[#8a8a8a] mt-1">Transactions qui reviennent régulièrement, créées automatiquement à chaque échéance.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={runNow} disabled={running} className="flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-white bg-[#1a1a1a] border border-[#2a2a2a] rounded-full hover:border-accent-sand/50 disabled:opacity-50 transition-colors">
            <RefreshCw size={15} className={running ? "animate-spin" : ""} /> Générer les échéances
          </button>
          <button onClick={() => setEditing("new")} className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-full hover:bg-accent-sand transition-colors">
            <Plus size={15} /> Nouvelle récurrence
          </button>
        </div>
      </div>

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

      {recs.length === 0 ? (
        <EmptyState
          icon={Repeat}
          title="Aucune récurrence"
          description="Crée une transaction récurrente (frais bancaires mensuels, cotisation annuelle...) et OpenFlow la générera automatiquement à chaque échéance."
          ctaLabel="Nouvelle récurrence"
          onCta={() => setEditing("new")}
        />
      ) : (
        <div className="bg-bg-card border border-border rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#1a1a1a]">
                  <th className="px-5 py-3 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Libellé</th>
                  <th className="px-5 py-3 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Flux</th>
                  <th className="px-5 py-3 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Fréquence</th>
                  <th className="px-5 py-3 text-right text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Montant</th>
                  <th className="px-5 py-3 text-right"></th>
                </tr>
              </thead>
              <tbody>
                {recs.map((r, idx) => (
                  <tr key={r.id} className={`hover:bg-[#1a1a1a] transition-colors ${idx > 0 ? "border-t border-[#1a1a1a]" : ""} ${r.active ? "" : "opacity-50"}`}>
                    <td className="px-5 py-3.5">
                      <div className="font-medium text-white">{r.label}</div>
                      {r.category_name && <div className="text-xs text-[#8a8a8a]">{r.category_name}</div>}
                    </td>
                    <td className="px-5 py-3.5 text-text-secondary whitespace-nowrap">{r.from_entity_name} → {r.to_entity_name}</td>
                    <td className="px-5 py-3.5 text-text-secondary whitespace-nowrap">
                      {FREQ_LABELS[r.frequency] || r.frequency}
                      {!r.active && <span className="ml-2 text-xs text-[#777]">(inactive)</span>}
                    </td>
                    <td className="px-5 py-3.5 text-right font-semibold text-white whitespace-nowrap">{formatEuros(r.amount_cents)}</td>
                    <td className="px-5 py-3.5 text-right whitespace-nowrap">
                      <button onClick={() => setEditing(r)} className="text-[#8a8a8a] hover:text-accent-sand p-1"><Pencil size={14} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {editing && (
        <RecurrenceForm
          rec={editing === "new" ? null : editing}
          entities={entities}
          categories={categories}
          onClose={() => setEditing(null)}
          onSaved={(list) => { setRecs(list); setEditing(null); }}
          onDeleted={(list) => { setRecs(list); setEditing(null); }}
          onError={setError}
        />
      )}
    </div>
  );
}

function RecurrenceForm({
  rec, entities, categories, onClose, onSaved, onDeleted, onError,
}: {
  rec: Rec | null;
  entities: Entity[];
  categories: Category[];
  onClose: () => void;
  onSaved: (list: Rec[]) => void;
  onDeleted: (list: Rec[]) => void;
  onError: (m: string) => void;
}) {
  const [label, setLabel] = useState(rec?.label ?? "");
  const [amount, setAmount] = useState(rec ? String(centsToEuros(rec.amount_cents)) : "");
  const [fromId, setFromId] = useState<number | "">(rec?.from_entity_id ?? "");
  const [toId, setToId] = useState<number | "">(rec?.to_entity_id ?? "");
  const [categoryId, setCategoryId] = useState<number | "">(rec?.category_id ?? "");
  const [frequency, setFrequency] = useState(rec?.frequency ?? "monthly");
  const [startDate, setStartDate] = useState(rec?.start_date ?? todayISO());
  const [endDate, setEndDate] = useState(rec?.end_date ?? "");
  const [active, setActive] = useState(rec ? rec.active === 1 : true);
  const [busy, setBusy] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);

  const save = async () => {
    if (!label.trim()) { onError("Libellé requis."); return; }
    if (fromId === "" || toId === "") { onError("Choisis les entités source et destination."); return; }
    const cents = eurosToCents(amount);
    if (cents <= 0) { onError("Montant invalide."); return; }
    setBusy(true);
    try {
      const body = {
        label: label.trim(), amount_cents: cents,
        from_entity_id: Number(fromId), to_entity_id: Number(toId),
        category_id: categoryId === "" ? null : Number(categoryId),
        frequency, start_date: startDate, end_date: endDate || null, active,
      };
      const list = rec ? await api.updateRecurrence(rec.id, body) : await api.createRecurrence(body);
      onSaved(list);
    } catch (e: any) { onError(e.message); setBusy(false); }
  };

  const doRemove = async () => {
    if (!rec) return;
    try { onDeleted(await api.deleteRecurrence(rec.id)); }
    catch (e: any) { onError(e.message); }
    finally { setConfirmDel(false); }
  };

  return (
    <>
    <ConfirmDialog
      open={confirmDel}
      danger
      title="Supprimer la récurrence"
      message={rec ? `Supprimer « ${rec.label} » ? Les transactions déjà générées sont conservées.` : ""}
      confirmLabel="Supprimer"
      onConfirm={doRemove}
      onCancel={() => setConfirmDel(false)}
    />
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="w-full max-w-lg max-h-[88vh] overflow-y-auto bg-bg-card border border-border rounded-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 bg-bg-card border-b border-[#1a1a1a] px-6 py-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-white">{rec ? "Modifier la récurrence" : "Nouvelle récurrence"}</h2>
          <button onClick={onClose} className="text-[#8a8a8a] hover:text-white"><X size={18} /></button>
        </div>
        <div className="px-6 py-5 space-y-4">
          <div>
            <label className={labelClass}>Libellé</label>
            <input className={inputClass} value={label} onChange={(e) => setLabel(e.target.value)} placeholder="ex : Frais bancaires" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelClass}>Montant (€)</label>
              <input className={inputClass} type="number" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="5,00" />
            </div>
            <div>
              <label className={labelClass}>Fréquence</label>
              <select className={inputClass} value={frequency} onChange={(e) => setFrequency(e.target.value)}>
                <option value="weekly">Chaque semaine</option>
                <option value="monthly">Chaque mois</option>
                <option value="yearly">Chaque année</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelClass}>De (source)</label>
              <select className={inputClass} value={fromId} onChange={(e) => setFromId(e.target.value === "" ? "" : Number(e.target.value))}>
                <option value="">Choisir…</option>
                {entities.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
              </select>
            </div>
            <div>
              <label className={labelClass}>Vers (destination)</label>
              <select className={inputClass} value={toId} onChange={(e) => setToId(e.target.value === "" ? "" : Number(e.target.value))}>
                <option value="">Choisir…</option>
                {entities.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className={labelClass}>Catégorie (facultatif)</label>
            <select className={inputClass} value={categoryId} onChange={(e) => setCategoryId(e.target.value === "" ? "" : Number(e.target.value))}>
              <option value="">Aucune</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelClass}>Première échéance</label>
              <input className={inputClass} type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </div>
            <div>
              <label className={labelClass}>Fin (facultatif)</label>
              <input className={inputClass} type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm text-text-secondary">
            <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} className="accent-accent-sand" />
            Active (génère les échéances)
          </label>
          <div className="flex items-center gap-3 pt-1">
            <button onClick={save} disabled={busy} className="px-5 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-full hover:bg-accent-sand disabled:opacity-40 transition-colors">
              {busy ? "Enregistrement…" : "Enregistrer"}
            </button>
            {rec && <button type="button" onClick={() => setConfirmDel(true)} className="ml-auto inline-flex items-center gap-1.5 text-sm text-[#8a8a8a] hover:text-alert transition-colors"><Trash2 size={14} /> Supprimer</button>}
          </div>
        </div>
      </div>
    </div>
    </>
  );
}
