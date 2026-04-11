import { useEffect, useState } from "react";
import { Receipt, Plus, Trash2, Pencil, X, Check } from "lucide-react";

const BASE_URL = "/api";
const eurFormatter = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

interface TaxReceipt {
  id: number;
  number: string;
  contact_id: number;
  amount: number;
  date: string;
  fiscal_year: string;
  purpose: string;
  generated_at: string;
}

interface TaxReceiptForm {
  contact_id: number | string;
  amount: number | string;
  date: string;
  fiscal_year: string;
  purpose: string;
}

const emptyForm: TaxReceiptForm = {
  contact_id: "",
  amount: "",
  date: new Date().toISOString().slice(0, 10),
  fiscal_year: String(new Date().getFullYear()),
  purpose: "",
};

async function apiFetch(path: string, options?: RequestInit) {
  const resp = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || resp.statusText);
  }
  return resp.json();
}

export default function TaxReceiptsView() {
  const [receipts, setReceipts] = useState<TaxReceipt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fiscalYearFilter, setFiscalYearFilter] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<TaxReceiptForm>(emptyForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  const load = (fy?: string) => {
    setLoading(true);
    setError(null);
    const query = fy ? `?fiscal_year=${encodeURIComponent(fy)}` : "";
    apiFetch(`/tax_receipts/${query}`)
      .then(setReceipts)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load(fiscalYearFilter || undefined);
  }, [fiscalYearFilter]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        contact_id: Number(form.contact_id),
        amount: Number(form.amount),
        date: form.date,
        fiscal_year: form.fiscal_year,
        purpose: form.purpose,
      };
      if (editingId !== null) {
        await apiFetch(`/tax_receipts/${editingId}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
      } else {
        await apiFetch("/tax_receipts/", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }
      setShowForm(false);
      setForm(emptyForm);
      setEditingId(null);
      load(fiscalYearFilter || undefined);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (r: TaxReceipt) => {
    setForm({
      contact_id: r.contact_id,
      amount: r.amount,
      date: r.date,
      fiscal_year: r.fiscal_year,
      purpose: r.purpose,
    });
    setEditingId(r.id);
    setShowForm(true);
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Supprimer ce recu fiscal ?")) return;
    try {
      await apiFetch(`/tax_receipts/${id}`, { method: "DELETE" });
      load(fiscalYearFilter || undefined);
    } catch (e: any) {
      setError(e.message);
    }
  };

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Receipt size={24} className="text-indigo-600" />
          <h1 className="text-2xl font-bold text-gray-900">Recus fiscaux</h1>
        </div>
        <button
          onClick={() => { setForm(emptyForm); setEditingId(null); setShowForm(true); }}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm font-medium"
        >
          <Plus size={16} />
          Nouveau recu
        </button>
      </div>

      {/* Filter */}
      <div className="flex gap-3 mb-4">
        <input
          type="text"
          placeholder="Filtrer par annee fiscale (ex: 2026)"
          value={fiscalYearFilter}
          onChange={(e) => setFiscalYearFilter(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm w-64 focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />
      </div>

      {/* Form */}
      {showForm && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 mb-5 shadow-sm">
          <h2 className="text-base font-semibold text-gray-800 mb-4">
            {editingId !== null ? "Modifier le recu" : "Nouveau recu fiscal"}
          </h2>
          <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Contact ID</label>
              <input
                type="number"
                required
                value={form.contact_id}
                onChange={(e) => setForm({ ...form, contact_id: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Montant (EUR)</label>
              <input
                type="number"
                step="0.01"
                required
                value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Date</label>
              <input
                type="date"
                required
                value={form.date}
                onChange={(e) => setForm({ ...form, date: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Annee fiscale</label>
              <input
                type="text"
                required
                value={form.fiscal_year}
                onChange={(e) => setForm({ ...form, fiscal_year: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-xs font-medium text-gray-600 mb-1">Objet / Motif</label>
              <input
                type="text"
                value={form.purpose}
                onChange={(e) => setForm({ ...form, purpose: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div className="col-span-2 flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => { setShowForm(false); setEditingId(null); }}
                className="flex items-center gap-1 px-3 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                <X size={14} /> Annuler
              </button>
              <button
                type="submit"
                disabled={saving}
                className="flex items-center gap-1 px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
              >
                <Check size={14} /> {saving ? "Enregistrement..." : "Enregistrer"}
              </button>
            </div>
          </form>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 mb-4 text-sm">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400 text-sm">Chargement...</div>
        ) : receipts.length === 0 ? (
          <div className="p-8 text-center text-gray-400 text-sm">Aucun recu fiscal</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Numero</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Contact</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Montant</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Date</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Annee fiscale</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Objet</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {receipts.map((r) => (
                <tr key={r.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-indigo-700">{r.number}</td>
                  <td className="px-4 py-3 text-gray-700">{r.contact_id}</td>
                  <td className="px-4 py-3 font-medium text-gray-900">{eurFormatter.format(r.amount)}</td>
                  <td className="px-4 py-3 text-gray-600">{r.date}</td>
                  <td className="px-4 py-3 text-gray-600">{r.fiscal_year}</td>
                  <td className="px-4 py-3 text-gray-600 max-w-xs truncate">{r.purpose || "-"}</td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2 justify-end">
                      <button
                        onClick={() => handleEdit(r)}
                        className="p-1 text-gray-400 hover:text-indigo-600 rounded"
                        title="Modifier"
                      >
                        <Pencil size={15} />
                      </button>
                      <button
                        onClick={() => handleDelete(r.id)}
                        className="p-1 text-gray-400 hover:text-red-600 rounded"
                        title="Supprimer"
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
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
