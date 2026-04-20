import { useEffect, useState, useCallback } from "react";
import { Plus, Pencil, Trash2, X, CheckCircle2, Clock } from "lucide-react";

const BASE_URL = "/api";
const eurFormatter = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

async function apiReimb<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}/reimbursements${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || response.statusText);
  }
  return response.json();
}

interface Reimbursement {
  id: number;
  transaction_id: number | null;
  person_name: string;
  amount: number;
  status: string;
  reimbursed_date: string | null;
  reimbursement_transaction_id: number | null;
  notes: string;
  created_at: string;
  updated_at: string;
}

interface SummaryRow {
  person_name: string;
  total_pending: number;
  count: number;
}

interface ReimbForm {
  transaction_id: string;
  person_name: string;
  amount: string;
  status: string;
  reimbursed_date: string;
  notes: string;
}

const emptyForm: ReimbForm = {
  transaction_id: "",
  person_name: "",
  amount: "",
  status: "pending",
  reimbursed_date: "",
  notes: "",
};

function toPayload(form: ReimbForm) {
  return {
    transaction_id: form.transaction_id ? parseInt(form.transaction_id) : null,
    person_name: form.person_name,
    amount: parseFloat(form.amount),
    status: form.status,
    reimbursed_date: form.reimbursed_date || null,
    notes: form.notes,
  };
}

export default function ReimbursementManager() {
  const [items, setItems] = useState<Reimbursement[]>([]);
  const [summary, setSummary] = useState<SummaryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Reimbursement | null>(null);
  const [form, setForm] = useState<ReimbForm>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const query = statusFilter ? `?status=${statusFilter}` : "";
      const [listData, summaryData] = await Promise.all([
        apiReimb<Reimbursement[]>(`/${query}`),
        apiReimb<SummaryRow[]>("/summary"),
      ]);
      setItems(listData);
      setSummary(summaryData);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  function openCreate() {
    setEditing(null);
    setForm(emptyForm);
    setShowForm(true);
  }

  function openEdit(r: Reimbursement) {
    setEditing(r);
    setForm({
      transaction_id: r.transaction_id ? String(r.transaction_id) : "",
      person_name: r.person_name,
      amount: String(r.amount),
      status: r.status,
      reimbursed_date: r.reimbursed_date || "",
      notes: r.notes,
    });
    setShowForm(true);
  }

  function cancelForm() {
    setShowForm(false);
    setEditing(null);
    setForm(emptyForm);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = toPayload(form);
      if (editing) {
        await apiReimb(`/${editing.id}`, { method: "PUT", body: JSON.stringify(payload) });
      } else {
        await apiReimb("/", { method: "POST", body: JSON.stringify(payload) });
      }
      cancelForm();
      fetchAll();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number) {
    try {
      await apiReimb(`/${id}`, { method: "DELETE" });
      setConfirmDelete(null);
      fetchAll();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function toggleReimbursed(r: Reimbursement) {
    const today = new Date().toISOString().slice(0, 10);
    try {
      const newStatus = r.status === "pending" ? "reimbursed" : "pending";
      await apiReimb(`/${r.id}`, {
        method: "PUT",
        body: JSON.stringify({
          status: newStatus,
          reimbursed_date: newStatus === "reimbursed" ? today : null,
        }),
      });
      fetchAll();
    } catch (e: any) {
      setError(e.message);
    }
  }

  const totalPending = summary.reduce((s, r) => s + r.total_pending, 0);
  const countPending = summary.reduce((s, r) => s + r.count, 0);

  const inputClass = "w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#444] [color-scheme:dark]";
  const labelClass = "block text-sm font-medium text-[#B0B0B0] mb-1.5";

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
            Remboursements
          </h1>
          <p className="text-sm text-[#666] mt-1">
            Avances de frais et remboursements membres.
          </p>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] transition-colors"
        >
          <Plus size={15} /> Ajouter
        </button>
      </div>

      {error && (
        <div className="mb-4 bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-2xl p-4 text-sm flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)} className="text-[#FF5252]/70 hover:text-[#FF5252]">
            <X size={16} />
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-[#111] border border-[#222] rounded-2xl p-5">
          <div className="text-xs font-medium text-[#666] uppercase tracking-wider mb-2">Total en attente</div>
          <div className="text-2xl font-bold text-[#F2C48D]">{eurFormatter.format(totalPending)}</div>
        </div>
        <div className="bg-[#111] border border-[#222] rounded-2xl p-5">
          <div className="text-xs font-medium text-[#666] uppercase tracking-wider mb-2">Avances ouvertes</div>
          <div className="text-2xl font-bold text-white">{countPending}</div>
        </div>
        <div className="bg-[#111] border border-[#222] rounded-2xl p-5">
          <div className="text-xs font-medium text-[#666] uppercase tracking-wider mb-2">Personnes concernées</div>
          <div className="text-2xl font-bold text-white">{summary.length}</div>
        </div>
      </div>

      {summary.length > 0 && (
        <div className="mb-6 bg-[#111] border border-[#222] rounded-2xl p-5">
          <h2 className="text-sm font-semibold text-white mb-3">Qui doit combien ?</h2>
          <div className="space-y-2">
            {summary.map((s) => (
              <div key={s.person_name} className="flex items-center justify-between py-1.5">
                <div className="text-sm text-[#B0B0B0]">
                  {s.person_name} <span className="text-[#555] text-xs ml-2">({s.count} avance{s.count > 1 ? "s" : ""})</span>
                </div>
                <div className="text-sm font-semibold text-[#F2C48D]">{eurFormatter.format(s.total_pending)}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mb-5 flex items-center gap-3">
        <label className="text-sm text-[#666]">Statut</label>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D]"
        >
          <option value="">Tous</option>
          <option value="pending">En attente</option>
          <option value="reimbursed">Remboursé</option>
        </select>
      </div>

      {showForm && (
        <div className="mb-6 bg-[#111] border border-[#222] rounded-2xl p-6">
          <h2 className="text-base font-semibold text-white mb-5">
            {editing ? "Modifier le remboursement" : "Nouveau remboursement"}
          </h2>
          <form onSubmit={handleSave} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className={labelClass}>Personne</label>
              <input
                type="text"
                required
                value={form.person_name}
                onChange={(e) => setForm({ ...form, person_name: e.target.value })}
                className={inputClass}
                placeholder="Prénom Nom"
              />
            </div>
            <div>
              <label className={labelClass}>Montant (EUR)</label>
              <input
                type="number"
                step="0.01"
                required
                value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })}
                className={inputClass}
                placeholder="0.00"
              />
            </div>
            <div>
              <label className={labelClass}>Statut</label>
              <select
                value={form.status}
                onChange={(e) => setForm({ ...form, status: e.target.value })}
                className={inputClass}
              >
                <option value="pending">En attente</option>
                <option value="reimbursed">Remboursé</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Date de remboursement</label>
              <input
                type="date"
                value={form.reimbursed_date}
                onChange={(e) => setForm({ ...form, reimbursed_date: e.target.value })}
                className={inputClass}
                disabled={form.status !== "reimbursed"}
              />
            </div>
            <div>
              <label className={labelClass}>ID Transaction liée</label>
              <input
                type="number"
                value={form.transaction_id}
                onChange={(e) => setForm({ ...form, transaction_id: e.target.value })}
                className={inputClass}
                placeholder="(optionnel)"
              />
            </div>
            <div className="sm:col-span-2">
              <label className={labelClass}>Notes</label>
              <textarea
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                className={inputClass}
                rows={2}
                placeholder="(optionnel)"
              />
            </div>
            <div className="sm:col-span-2 flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={cancelForm}
                className="px-5 py-2.5 text-sm font-semibold text-white border border-[#333] rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors"
              >
                Annuler
              </button>
              <button
                type="submit"
                disabled={saving}
                className="px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-50 transition-colors"
              >
                {saving ? "Enregistrement..." : "Enregistrer"}
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#F2C48D]" />
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-12 text-[#666] text-sm">
            Aucun remboursement.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Personne</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Statut</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Transaction</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Montant</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r, idx) => (
                <tr key={r.id} className={`hover:bg-[#1a1a1a] transition-colors ${idx > 0 ? "border-t border-[#1a1a1a]" : ""}`}>
                  <td className="px-5 py-3.5 font-medium text-white">{r.person_name}</td>
                  <td className="px-5 py-3.5">
                    {r.status === "reimbursed" ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                        <CheckCircle2 size={11} /> Remboursé
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-amber-500/15 text-amber-400 border border-amber-500/30">
                        <Clock size={11} /> En attente
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-3.5 text-[#B0B0B0]">
                    {r.transaction_id ? `#${r.transaction_id}` : <span className="text-[#444]">—</span>}
                  </td>
                  <td className="px-5 py-3.5 text-right font-semibold text-[#F2C48D] whitespace-nowrap">
                    {eurFormatter.format(r.amount)}
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    {confirmDelete === r.id ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="text-xs text-[#666]">Supprimer ?</span>
                        <button onClick={() => handleDelete(r.id)} className="text-xs font-medium text-[#FF5252] hover:text-red-400">Oui</button>
                        <button onClick={() => setConfirmDelete(null)} className="text-xs font-medium text-[#666] hover:text-white">Non</button>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1">
                        <button
                          onClick={() => toggleReimbursed(r)}
                          className="p-1.5 text-[#666] hover:text-emerald-400 rounded-lg hover:bg-[#222] transition-colors"
                          title={r.status === "pending" ? "Marquer remboursé" : "Remettre en attente"}
                        >
                          <CheckCircle2 size={14} strokeWidth={1.5} />
                        </button>
                        <button
                          onClick={() => openEdit(r)}
                          className="p-1.5 text-[#666] hover:text-white rounded-lg hover:bg-[#222] transition-colors"
                          title="Modifier"
                        >
                          <Pencil size={14} strokeWidth={1.5} />
                        </button>
                        <button
                          onClick={() => setConfirmDelete(r.id)}
                          className="p-1.5 text-[#666] hover:text-[#FF5252] rounded-lg hover:bg-[#222] transition-colors"
                          title="Supprimer"
                        >
                          <Trash2 size={14} strokeWidth={1.5} />
                        </button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
