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

  const inputClass = "w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#444] [color-scheme:dark]";
  const labelClass = "block text-xs font-medium text-[#B0B0B0] mb-1.5";

  return (
    <div className="p-8 max-w-5xl">
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <Receipt size={20} strokeWidth={1.5} className="text-[#666]" />
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
            Recus fiscaux
          </h1>
        </div>
        <button
          onClick={() => { setForm(emptyForm); setEditingId(null); setShowForm(true); }}
          className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] transition-colors"
        >
          <Plus size={15} />
          Nouveau recu
        </button>
      </div>

      {/* Filter */}
      <div className="flex gap-3 mb-5">
        <input
          type="text"
          placeholder="Filtrer par année fiscale (ex: 2026)"
          value={fiscalYearFilter}
          onChange={(e) => setFiscalYearFilter(e.target.value)}
          className="bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#444] w-64"
        />
      </div>

      {/* Form */}
      {showForm && (
        <div className="bg-[#111] border border-[#222] rounded-2xl p-6 mb-6">
          <h2 className="text-base font-semibold text-white mb-5">
            {editingId !== null ? "Modifier le recu" : "Nouveau recu fiscal"}
          </h2>
          <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-4">
            <div>
              <label className={labelClass}>Contact ID</label>
              <input
                type="number"
                required
                value={form.contact_id}
                onChange={(e) => setForm({ ...form, contact_id: e.target.value })}
                className={inputClass}
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
              />
            </div>
            <div>
              <label className={labelClass}>Date</label>
              <input
                type="date"
                required
                value={form.date}
                onChange={(e) => setForm({ ...form, date: e.target.value })}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Année fiscale</label>
              <input
                type="text"
                required
                value={form.fiscal_year}
                onChange={(e) => setForm({ ...form, fiscal_year: e.target.value })}
                className={inputClass}
              />
            </div>
            <div className="col-span-2">
              <label className={labelClass}>Objet / Motif</label>
              <input
                type="text"
                value={form.purpose}
                onChange={(e) => setForm({ ...form, purpose: e.target.value })}
                className={inputClass}
              />
            </div>
            <div className="col-span-2 flex gap-3 justify-end pt-2">
              <button
                type="button"
                onClick={() => { setShowForm(false); setEditingId(null); }}
                className="px-5 py-2.5 text-sm font-semibold text-white border border-[#333] rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors"
              >
                Annuler
              </button>
              <button
                type="submit"
                disabled={saving}
                className="flex items-center gap-1.5 px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-50 transition-colors"
              >
                <Check size={14} strokeWidth={1.5} /> {saving ? "Enregistrement..." : "Enregistrer"}
              </button>
            </div>
          </form>
        </div>
      )}

      {error && (
        <div className="bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-2xl px-5 py-4 mb-5 text-sm flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)} className="text-[#FF5252]/70 hover:text-[#FF5252]"><X size={14} /></button>
        </div>
      )}

      {/* Table */}
      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
        {loading ? (
          <div className="p-8 text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#F2C48D] mx-auto" />
          </div>
        ) : receipts.length === 0 ? (
          <div className="p-8 text-center text-[#666] text-sm">Aucun recu fiscal</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                <th className="text-left px-5 py-3.5 text-xs font-medium text-[#666] uppercase tracking-wider">Numéro</th>
                <th className="text-left px-5 py-3.5 text-xs font-medium text-[#666] uppercase tracking-wider">Contact</th>
                <th className="text-left px-5 py-3.5 text-xs font-medium text-[#666] uppercase tracking-wider">Montant</th>
                <th className="text-left px-5 py-3.5 text-xs font-medium text-[#666] uppercase tracking-wider">Date</th>
                <th className="text-left px-5 py-3.5 text-xs font-medium text-[#666] uppercase tracking-wider">Année fiscale</th>
                <th className="text-left px-5 py-3.5 text-xs font-medium text-[#666] uppercase tracking-wider">Objet</th>
                <th className="px-5 py-3.5"></th>
              </tr>
            </thead>
            <tbody>
              {receipts.map((r, idx) => (
                <tr key={r.id} className={`hover:bg-[#1a1a1a] transition-colors ${idx > 0 ? "border-t border-[#1a1a1a]" : ""}`}>
                  <td className="px-5 py-3.5 font-mono text-xs text-[#F2C48D]">{r.number}</td>
                  <td className="px-5 py-3.5 text-[#B0B0B0]">{r.contact_id}</td>
                  <td className="px-5 py-3.5 font-semibold text-white">{eurFormatter.format(r.amount)}</td>
                  <td className="px-5 py-3.5 text-[#B0B0B0]">{r.date}</td>
                  <td className="px-5 py-3.5 text-[#B0B0B0]">{r.fiscal_year}</td>
                  <td className="px-5 py-3.5 text-[#B0B0B0] max-w-xs truncate">{r.purpose || <span className="text-[#444]">—</span>}</td>
                  <td className="px-5 py-3.5">
                    <div className="flex gap-1 justify-end">
                      <button
                        onClick={() => handleEdit(r)}
                        className="p-1.5 text-[#666] hover:text-white rounded-lg hover:bg-[#222] transition-colors"
                        title="Modifier"
                      >
                        <Pencil size={14} strokeWidth={1.5} />
                      </button>
                      <button
                        onClick={() => handleDelete(r.id)}
                        className="p-1.5 text-[#666] hover:text-[#FF5252] rounded-lg hover:bg-[#222] transition-colors"
                        title="Supprimer"
                      >
                        <Trash2 size={14} strokeWidth={1.5} />
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
