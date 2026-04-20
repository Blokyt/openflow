import { useEffect, useState, useCallback } from "react";
import { Plus, Pencil, Trash2, X, PiggyBank } from "lucide-react";
import EmptyState from "../../core/EmptyState";

const eurFormatter = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });
const BASE_URL = "/api";

async function apiBudget<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}/budget${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || response.statusText);
  }
  return response.json();
}

interface Budget {
  id: number;
  category_id: number | null;
  division_id: number | null;
  period_start: string;
  period_end: string;
  amount: number;
  label: string;
  created_at: string;
}

interface BudgetForm {
  category_id: string;
  division_id: string;
  period_start: string;
  period_end: string;
  amount: string;
  label: string;
}

const emptyForm: BudgetForm = {
  category_id: "",
  division_id: "",
  period_start: "",
  period_end: "",
  amount: "",
  label: "",
};

function formToPayload(form: BudgetForm) {
  return {
    category_id: form.category_id ? parseInt(form.category_id) : null,
    division_id: form.division_id ? parseInt(form.division_id) : null,
    period_start: form.period_start,
    period_end: form.period_end,
    amount: parseFloat(form.amount),
    label: form.label,
  };
}

function budgetToForm(b: Budget): BudgetForm {
  return {
    category_id: b.category_id !== null ? String(b.category_id) : "",
    division_id: b.division_id !== null ? String(b.division_id) : "",
    period_start: b.period_start,
    period_end: b.period_end,
    amount: String(b.amount),
    label: b.label,
  };
}

export default function BudgetManager() {
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editingBudget, setEditingBudget] = useState<Budget | null>(null);
  const [form, setForm] = useState<BudgetForm>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const fetchBudgets = useCallback(() => {
    setLoading(true);
    const query = period ? `?period=${encodeURIComponent(period)}` : "";
    apiBudget<Budget[]>(`/${query}`)
      .then(setBudgets)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [period]);

  useEffect(() => {
    fetchBudgets();
  }, [fetchBudgets]);

  function openCreate() {
    setEditingBudget(null);
    setForm(emptyForm);
    setShowForm(true);
  }

  function openEdit(b: Budget) {
    setEditingBudget(b);
    setForm(budgetToForm(b));
    setShowForm(true);
  }

  function cancelForm() {
    setShowForm(false);
    setEditingBudget(null);
    setForm(emptyForm);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = formToPayload(form);
      if (editingBudget) {
        await apiBudget(`/${editingBudget.id}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
      } else {
        await apiBudget("/", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }
      cancelForm();
      fetchBudgets();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number) {
    setDeletingId(id);
    try {
      await apiBudget(`/${id}`, { method: "DELETE" });
      setConfirmDelete(null);
      fetchBudgets();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setDeletingId(null);
    }
  }

  const inputClass = "w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#444] [color-scheme:dark]";
  const labelClass = "block text-sm font-medium text-[#B0B0B0] mb-1.5";

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
          Budget Prévisionnel
        </h1>
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

      {/* Filter by year */}
      <div className="mb-5 flex items-center gap-3">
        <label className="text-sm text-[#666]">Filtrer par année</label>
        <input
          type="text"
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          placeholder="ex: 2026"
          className="bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#444] w-28"
        />
        {period && (
          <button
            onClick={() => setPeriod("")}
            className="text-sm text-[#666] hover:text-white flex items-center gap-1 transition-colors"
          >
            <X size={14} /> Effacer
          </button>
        )}
      </div>

      {/* Form panel */}
      {showForm && (
        <div className="mb-6 bg-[#111] border border-[#222] rounded-2xl p-6">
          <h2 className="text-base font-semibold text-white mb-5">
            {editingBudget ? "Modifier le budget" : "Nouveau budget"}
          </h2>
          <form onSubmit={handleSave} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className={labelClass}>Libellé</label>
              <input
                type="text"
                value={form.label}
                onChange={(e) => setForm({ ...form, label: e.target.value })}
                className={inputClass}
                placeholder="Libellé du budget"
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
              <label className={labelClass}>Début de période</label>
              <input
                type="date"
                required
                value={form.period_start}
                onChange={(e) => setForm({ ...form, period_start: e.target.value })}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Fin de période</label>
              <input
                type="date"
                required
                value={form.period_end}
                onChange={(e) => setForm({ ...form, period_end: e.target.value })}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>ID Catégorie</label>
              <input
                type="number"
                value={form.category_id}
                onChange={(e) => setForm({ ...form, category_id: e.target.value })}
                className={inputClass}
                placeholder="(optionnel)"
              />
            </div>
            <div>
              <label className={labelClass}>ID Division</label>
              <input
                type="number"
                value={form.division_id}
                onChange={(e) => setForm({ ...form, division_id: e.target.value })}
                className={inputClass}
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

      {/* Table */}
      {!loading && budgets.length === 0 ? (
        <EmptyState
          icon={PiggyBank}
          title="Aucune enveloppe budgétaire"
          description="Définis une enveloppe par catégorie ou projet. L'app t'alerte quand tu approches du plafond."
          examples={[
            "Gala 2026 : 3 000 € (au 12/03 : 1 850 € utilisés)",
            "Matériel Cinéclub : 500 € par semestre",
          ]}
          ctaLabel="Créer ma première enveloppe"
          onCta={openCreate}
        />
      ) : (
      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#F2C48D]" />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Libellé</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Période</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Catégorie</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Montant</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {budgets.map((b, idx) => (
                <tr key={b.id} className={`hover:bg-[#1a1a1a] transition-colors ${idx > 0 ? "border-t border-[#1a1a1a]" : ""}`}>
                  <td className="px-5 py-3.5 font-medium text-white">
                    {b.label || <span className="text-[#444]">—</span>}
                  </td>
                  <td className="px-5 py-3.5 text-[#B0B0B0] whitespace-nowrap">
                    {b.period_start} &rarr; {b.period_end}
                  </td>
                  <td className="px-5 py-3.5 text-[#B0B0B0]">
                    {b.category_id !== null ? `#${b.category_id}` : <span className="text-[#444]">—</span>}
                  </td>
                  <td className="px-5 py-3.5 text-right font-semibold text-[#F2C48D] whitespace-nowrap">
                    {eurFormatter.format(b.amount)}
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    {confirmDelete === b.id ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="text-xs text-[#666]">Supprimer ?</span>
                        <button
                          onClick={() => handleDelete(b.id)}
                          disabled={deletingId === b.id}
                          className="text-xs font-medium text-[#FF5252] hover:text-red-400"
                        >
                          Oui
                        </button>
                        <button
                          onClick={() => setConfirmDelete(null)}
                          className="text-xs font-medium text-[#666] hover:text-white"
                        >
                          Non
                        </button>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1">
                        <button
                          onClick={() => openEdit(b)}
                          className="p-1.5 text-[#666] hover:text-white rounded-lg hover:bg-[#222] transition-colors"
                          title="Modifier"
                        >
                          <Pencil size={14} strokeWidth={1.5} />
                        </button>
                        <button
                          onClick={() => setConfirmDelete(b.id)}
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
      )}
    </div>
  );
}
