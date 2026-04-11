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

  const inputClass = "w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#444] [color-scheme:dark]";
  const labelClass = "block text-xs font-medium text-[#B0B0B0] mb-1.5";

  return (
    <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <label className={labelClass}>Libellé *</label>
        <input
          type="text"
          value={form.label}
          onChange={(e) => set("label", e.target.value)}
          required
          className={inputClass}
        />
      </div>
      <div className="sm:col-span-2">
        <label className={labelClass}>Description</label>
        <input
          type="text"
          value={form.description}
          onChange={(e) => set("description", e.target.value)}
          className={inputClass}
        />
      </div>
      <div>
        <label className={labelClass}>Montant *</label>
        <input
          type="number"
          step="0.01"
          value={form.amount}
          onChange={(e) => set("amount", e.target.value)}
          required
          className={inputClass}
        />
      </div>
      <div>
        <label className={labelClass}>Fréquence *</label>
        <select
          value={form.frequency}
          onChange={(e) => set("frequency", e.target.value)}
          required
          className={inputClass}
        >
          {FREQUENCIES.map((f) => (
            <option key={f.value} value={f.value}>{f.label}</option>
          ))}
        </select>
      </div>
      <div>
        <label className={labelClass}>Date de début *</label>
        <input
          type="date"
          value={form.start_date}
          onChange={(e) => set("start_date", e.target.value)}
          required
          className={inputClass}
        />
      </div>
      <div>
        <label className={labelClass}>Date de fin</label>
        <input
          type="date"
          value={form.end_date}
          onChange={(e) => set("end_date", e.target.value)}
          className={inputClass}
        />
      </div>
      <div>
        <label className={labelClass}>Statut</label>
        <select
          value={form.active}
          onChange={(e) => set("active", e.target.value)}
          className={inputClass}
        >
          <option value="1">Actif</option>
          <option value="0">Inactif</option>
        </select>
      </div>
      <div className="sm:col-span-2 flex justify-end gap-3 pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-5 py-2.5 text-sm font-semibold text-white border border-[#333] rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors"
        >
          Annuler
        </button>
        <button
          type="submit"
          disabled={saving}
          className="px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-60 transition-colors"
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
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
            Récurrences
          </h1>
          <p className="text-sm text-[#666] mt-1">Automatiser les transactions répétitives</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-white border border-[#333] rounded-full hover:border-[#444] hover:bg-[#1a1a1a] disabled:opacity-60 transition-colors"
          >
            {generating ? <RefreshCw size={15} className="animate-spin" /> : <Play size={15} strokeWidth={1.5} />}
            Générer
          </button>
          <button
            onClick={() => { setShowForm(true); setEditingRec(null); }}
            className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] transition-colors"
          >
            <Plus size={15} /> Nouvelle récurrence
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-2xl p-4 text-sm flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)} className="text-[#FF5252]/70 hover:text-[#FF5252]"><X size={16} /></button>
        </div>
      )}
      {success && (
        <div className="mb-4 bg-[#0a1a0a] border border-[#00C853]/30 text-[#00C853] rounded-2xl p-4 text-sm flex items-center justify-between">
          {success}
          <button onClick={() => setSuccess(null)} className="text-[#00C853]/70 hover:text-[#00C853]"><X size={16} /></button>
        </div>
      )}

      {(showForm || editingRec) && (
        <div className="mb-6 bg-[#111] border border-[#222] rounded-2xl p-6">
          <h2 className="text-base font-semibold text-white mb-5">
            {editingRec ? "Modifier la récurrence" : "Nouvelle récurrence"}
          </h2>
          <FormPanel
            initial={editingRec ?? undefined}
            onSave={editingRec ? handleUpdate : handleCreate}
            onCancel={() => { setShowForm(false); setEditingRec(null); }}
          />
        </div>
      )}

      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#F2C48D]" />
          </div>
        ) : recurrings.length === 0 ? (
          <div className="text-center py-12 text-[#666] text-sm">
            Aucune récurrence définie. Créez votre première récurrence.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Libellé</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Fréquence</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Début</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Fin</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Dernière génération</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Montant</th>
                <th className="px-5 py-3.5 text-center text-xs font-medium text-[#666] uppercase tracking-wider">Statut</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {recurrings.map((rec, idx) => (
                <tr key={rec.id} className={`hover:bg-[#1a1a1a] transition-colors ${idx > 0 ? "border-t border-[#1a1a1a]" : ""}`}>
                  <td className="px-5 py-3.5 font-medium text-white">
                    {rec.label}
                    {rec.description && (
                      <p className="text-xs text-[#666] font-normal mt-0.5">{rec.description}</p>
                    )}
                  </td>
                  <td className="px-5 py-3.5 text-[#B0B0B0]">{frequencyLabel(rec.frequency)}</td>
                  <td className="px-5 py-3.5 text-[#B0B0B0]">{rec.start_date}</td>
                  <td className="px-5 py-3.5 text-[#B0B0B0]">{rec.end_date ?? <span className="text-[#444]">—</span>}</td>
                  <td className="px-5 py-3.5 text-[#B0B0B0]">{rec.last_generated ?? <span className="text-[#444]">jamais</span>}</td>
                  <td className={`px-5 py-3.5 text-right font-semibold whitespace-nowrap ${rec.amount >= 0 ? "text-[#00C853]" : "text-[#FF5252]"}`}>
                    {eurFormatter.format(rec.amount)}
                  </td>
                  <td className="px-5 py-3.5 text-center">
                    <span
                      className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
                        rec.active
                          ? "bg-[#00C853]/10 text-[#00C853] border border-[#00C853]/20"
                          : "bg-[#1a1a1a] text-[#666] border border-[#222]"
                      }`}
                    >
                      {rec.active ? "Actif" : "Inactif"}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    {confirmDelete === rec.id ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="text-xs text-[#666]">Supprimer ?</span>
                        <button
                          onClick={() => handleDelete(rec.id)}
                          disabled={deletingId === rec.id}
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
                          onClick={() => { setEditingRec(rec); setShowForm(false); }}
                          className="p-1.5 text-[#666] hover:text-white rounded-lg hover:bg-[#222] transition-colors"
                          title="Modifier"
                        >
                          <Pencil size={14} strokeWidth={1.5} />
                        </button>
                        <button
                          onClick={() => setConfirmDelete(rec.id)}
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
