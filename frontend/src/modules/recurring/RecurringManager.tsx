import { useEffect, useState, useCallback } from "react";
import { Plus, Pencil, Trash2, X, RefreshCw, Play } from "lucide-react";

const BASE_URL = "/api";
const eurFormatter = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

async function apiRecurring<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}/recurring${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || response.statusText);
  }
  return response.json();
}

interface RecurringTransaction {
  id: number;
  label: string;
  description: string;
  amount: number;
  category_id: number | null;
  division_id: number | null;
  contact_id: number | null;
  frequency: string;
  start_date: string;
  end_date: string | null;
  last_generated: string | null;
  active: number;
  created_at: string;
}

interface RecurringForm {
  label: string;
  description: string;
  amount: string;
  frequency: string;
  start_date: string;
  end_date: string;
  active: string;
}

const emptyForm: RecurringForm = {
  label: "",
  description: "",
  amount: "",
  frequency: "monthly",
  start_date: "",
  end_date: "",
  active: "1",
};

const FREQUENCIES = [
  { value: "weekly", label: "Hebdomadaire" },
  { value: "monthly", label: "Mensuelle" },
  { value: "quarterly", label: "Trimestrielle" },
  { value: "yearly", label: "Annuelle" },
];

// O(1) lookup map built once at module level (js-index-maps)
const FREQUENCY_LABEL_MAP = new Map(FREQUENCIES.map((f) => [f.value, f.label]));

function frequencyLabel(freq: string): string {
  return FREQUENCY_LABEL_MAP.get(freq) ?? freq;
}

function formToPayload(form: RecurringForm) {
  return {
    label: form.label,
    description: form.description,
    amount: parseFloat(form.amount),
    frequency: form.frequency,
    start_date: form.start_date,
    end_date: form.end_date || null,
    active: parseInt(form.active),
  };
}

function recurringToForm(rec: RecurringTransaction): RecurringForm {
  return {
    label: rec.label,
    description: rec.description,
    amount: String(rec.amount),
    frequency: rec.frequency,
    start_date: rec.start_date,
    end_date: rec.end_date ?? "",
    active: String(rec.active),
  };
}

function FormPanel({
  initial,
  onSave,
  onCancel,
}: {
  initial?: RecurringTransaction;
  onSave: (form: RecurringForm) => Promise<void>;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<RecurringForm>(initial ? recurringToForm(initial) : emptyForm);
  const [saving, setSaving] = useState(false);

  function set(field: keyof RecurringForm, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave(form);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <label className="block text-xs font-medium text-gray-700 mb-1">Libellé *</label>
        <input
          type="text"
          value={form.label}
          onChange={(e) => set("label", e.target.value)}
          required
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>
      <div className="sm:col-span-2">
        <label className="block text-xs font-medium text-gray-700 mb-1">Description</label>
        <input
          type="text"
          value={form.description}
          onChange={(e) => set("description", e.target.value)}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">Montant *</label>
        <input
          type="number"
          step="0.01"
          value={form.amount}
          onChange={(e) => set("amount", e.target.value)}
          required
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">Fréquence *</label>
        <select
          value={form.frequency}
          onChange={(e) => set("frequency", e.target.value)}
          required
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          {FREQUENCIES.map((f) => (
            <option key={f.value} value={f.value}>{f.label}</option>
          ))}
        </select>
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">Date de début *</label>
        <input
          type="date"
          value={form.start_date}
          onChange={(e) => set("start_date", e.target.value)}
          required
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">Date de fin</label>
        <input
          type="date"
          value={form.end_date}
          onChange={(e) => set("end_date", e.target.value)}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">Statut</label>
        <select
          value={form.active}
          onChange={(e) => set("active", e.target.value)}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="1">Actif</option>
          <option value="0">Inactif</option>
        </select>
      </div>
      <div className="sm:col-span-2 flex justify-end gap-3 pt-1">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
        >
          Annuler
        </button>
        <button
          type="submit"
          disabled={saving}
          className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-60"
        >
          {saving ? "Enregistrement..." : initial ? "Enregistrer" : "Créer"}
        </button>
      </div>
    </form>
  );
}

export default function RecurringManager() {
  const [recurrings, setRecurrings] = useState<RecurringTransaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingRec, setEditingRec] = useState<RecurringTransaction | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [generating, setGenerating] = useState(false);

  const fetchRecurrings = useCallback(() => {
    setLoading(true);
    apiRecurring<RecurringTransaction[]>("/")
      .then(setRecurrings)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchRecurrings();
  }, [fetchRecurrings]);

  async function handleCreate(form: RecurringForm) {
    await apiRecurring("/", {
      method: "POST",
      body: JSON.stringify(formToPayload(form)),
    });
    setShowForm(false);
    fetchRecurrings();
  }

  async function handleUpdate(form: RecurringForm) {
    if (!editingRec) return;
    await apiRecurring(`/${editingRec.id}`, {
      method: "PUT",
      body: JSON.stringify(formToPayload(form)),
    });
    setEditingRec(null);
    fetchRecurrings();
  }

  async function handleDelete(id: number) {
    setDeletingId(id);
    try {
      await apiRecurring(`/${id}`, { method: "DELETE" });
      setConfirmDelete(null);
      fetchRecurrings();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setDeletingId(null);
    }
  }

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    try {
      const result = await apiRecurring<any[]>("/generate", { method: "POST" });
      const count = result.length;
      setSuccess(count === 0
        ? "Aucune nouvelle transaction à générer."
        : `${count} transaction${count > 1 ? "s" : ""} générée${count > 1 ? "s" : ""}.`
      );
      fetchRecurrings();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Récurrences</h1>
          <p className="text-sm text-gray-500 mt-1">Automatiser les transactions répétitives</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-lg hover:bg-indigo-100 disabled:opacity-60"
          >
            {generating ? <RefreshCw size={16} className="animate-spin" /> : <Play size={16} />}
            Générer les transactions
          </button>
          <button
            onClick={() => { setShowForm(true); setEditingRec(null); }}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700"
          >
            <Plus size={16} /> Nouvelle récurrence
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)}><X size={16} /></button>
        </div>
      )}
      {success && (
        <div className="mb-4 bg-green-50 border border-green-200 text-green-700 rounded-lg p-3 text-sm flex items-center justify-between">
          {success}
          <button onClick={() => setSuccess(null)}><X size={16} /></button>
        </div>
      )}

      {(showForm || editingRec) && (
        <div className="mb-6 bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h2 className="text-base font-semibold text-gray-800 mb-4">
            {editingRec ? "Modifier la récurrence" : "Nouvelle récurrence"}
          </h2>
          <FormPanel
            initial={editingRec ?? undefined}
            onSave={editingRec ? handleUpdate : handleCreate}
            onCancel={() => { setShowForm(false); setEditingRec(null); }}
          />
        </div>
      )}

      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
          </div>
        ) : recurrings.length === 0 ? (
          <div className="text-center py-12 text-gray-500 text-sm">
            Aucune récurrence définie. Créez votre première récurrence.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Libellé</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Fréquence</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Début</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Fin</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Dernière génération</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600">Montant</th>
                <th className="px-4 py-3 text-center font-medium text-gray-600">Statut</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {recurrings.map((rec) => (
                <tr key={rec.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-900">
                    {rec.label}
                    {rec.description && (
                      <p className="text-xs text-gray-400 font-normal">{rec.description}</p>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-600">{frequencyLabel(rec.frequency)}</td>
                  <td className="px-4 py-3 text-gray-600">{rec.start_date}</td>
                  <td className="px-4 py-3 text-gray-500">{rec.end_date ?? <span className="text-gray-300">—</span>}</td>
                  <td className="px-4 py-3 text-gray-500">{rec.last_generated ?? <span className="text-gray-300">jamais</span>}</td>
                  <td className={`px-4 py-3 text-right font-semibold whitespace-nowrap ${rec.amount >= 0 ? "text-green-600" : "text-red-600"}`}>
                    {eurFormatter.format(rec.amount)}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                        rec.active
                          ? "bg-green-100 text-green-700"
                          : "bg-gray-100 text-gray-500"
                      }`}
                    >
                      {rec.active ? "Actif" : "Inactif"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {confirmDelete === rec.id ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="text-xs text-gray-500">Supprimer ?</span>
                        <button
                          onClick={() => handleDelete(rec.id)}
                          disabled={deletingId === rec.id}
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
                          onClick={() => { setEditingRec(rec); setShowForm(false); }}
                          className="p-1 text-gray-400 hover:text-indigo-600 rounded"
                          title="Modifier"
                        >
                          <Pencil size={15} />
                        </button>
                        <button
                          onClick={() => setConfirmDelete(rec.id)}
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
