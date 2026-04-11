import { useEffect, useState, useCallback } from "react";
import { Plus, Pencil, Trash2, X } from "lucide-react";

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

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Budget Previsionnel</h1>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700"
        >
          <Plus size={16} /> Ajouter
        </button>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)}>
            <X size={16} />
          </button>
        </div>
      )}

      {/* Filter by year */}
      <div className="mb-4 flex items-center gap-3">
        <label className="text-sm text-gray-600">Filtrer par annee</label>
        <input
          type="text"
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          placeholder="ex: 2026"
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 w-28"
        />
        {period && (
          <button
            onClick={() => setPeriod("")}
            className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1"
          >
            <X size={14} /> Effacer
          </button>
        )}
      </div>

      {/* Form panel */}
      {showForm && (
        <div className="mb-6 bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h2 className="text-base font-semibold text-gray-800 mb-4">
            {editingBudget ? "Modifier le budget" : "Nouveau budget"}
          </h2>
          <form onSubmit={handleSave} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Libelle</label>
              <input
                type="text"
                value={form.label}
                onChange={(e) => setForm({ ...form, label: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="Libelle du budget"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Montant (EUR)</label>
              <input
                type="number"
                step="0.01"
                required
                value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="0.00"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Debut de periode</label>
              <input
                type="date"
                required
                value={form.period_start}
                onChange={(e) => setForm({ ...form, period_start: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Fin de periode</label>
              <input
                type="date"
                required
                value={form.period_end}
                onChange={(e) => setForm({ ...form, period_end: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">ID Categorie</label>
              <input
                type="number"
                value={form.category_id}
                onChange={(e) => setForm({ ...form, category_id: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="(optionnel)"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">ID Division</label>
              <input
                type="number"
                value={form.division_id}
                onChange={(e) => setForm({ ...form, division_id: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="(optionnel)"
              />
            </div>
            <div className="sm:col-span-2 flex justify-end gap-3">
              <button
                type="button"
                onClick={cancelForm}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Annuler
              </button>
              <button
                type="submit"
                disabled={saving}
                className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50"
              >
                {saving ? "Enregistrement..." : "Enregistrer"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
          </div>
        ) : budgets.length === 0 ? (
          <div className="text-center py-12 text-gray-500 text-sm">
            Aucune enveloppe budgetaire trouvee.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Libelle</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Periode</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Categorie</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600">Montant</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {budgets.map((b) => (
                <tr key={b.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-900">
                    {b.label || <span className="text-gray-400">—</span>}
                  </td>
                  <td className="px-4 py-3 text-gray-600 whitespace-nowrap">
                    {b.period_start} &rarr; {b.period_end}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {b.category_id !== null ? `#${b.category_id}` : <span className="text-gray-300">—</span>}
                  </td>
                  <td className="px-4 py-3 text-right font-semibold text-indigo-700 whitespace-nowrap">
                    {eurFormatter.format(b.amount)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {confirmDelete === b.id ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="text-xs text-gray-500">Supprimer ?</span>
                        <button
                          onClick={() => handleDelete(b.id)}
                          disabled={deletingId === b.id}
                          className="text-xs font-medium text-red-600 hover:text-red-800"
                        >
                          Oui
                        </button>
                        <button
                          onClick={() => setConfirmDelete(null)}
                          className="text-xs font-medium text-gray-500 hover:text-gray-700"
                        >
                          Non
                        </button>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-2">
                        <button
                          onClick={() => openEdit(b)}
                          className="p-1 text-gray-400 hover:text-indigo-600 rounded"
                          title="Modifier"
                        >
                          <Pencil size={15} />
                        </button>
                        <button
                          onClick={() => setConfirmDelete(b.id)}
                          className="p-1 text-gray-400 hover:text-red-600 rounded"
                          title="Supprimer"
                        >
                          <Trash2 size={15} />
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
