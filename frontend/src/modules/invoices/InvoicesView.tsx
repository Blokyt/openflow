import { useEffect, useState, useCallback } from "react";
import { Plus, Trash2, X, Download, FileText } from "lucide-react";

const BASE_URL = "/api";
const eurFormatter = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

async function apiCall<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || response.statusText);
  }
  return response.json();
}

interface Invoice {
  id: number;
  type: "quote" | "invoice";
  number: string;
  date: string;
  contact_id: number | null;
  subtotal: number;
  tax_rate: number;
  total: number;
  status: string;
  lines?: InvoiceLine[];
}

interface InvoiceLine {
  description: string;
  quantity: number;
  unit_price: number;
}

interface Contact { id: number; name: string; }

export default function InvoicesView() {
  const [tab, setTab] = useState<"quote" | "invoice">("invoice");
  const [items, setItems] = useState<Invoice[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [vatEnabled, setVatEnabled] = useState(false);
  const [showForm, setShowForm] = useState(false);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const list = await apiCall<Invoice[]>(`/invoices/?type=${tab}`);
      setItems(list);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    fetchItems();
    apiCall<Contact[]>("/tiers/").then(setContacts).catch(() => setContacts([]));
    apiCall<any>("/config").then((cfg) => setVatEnabled(!!cfg.entity?.vat_enabled)).catch(() => {});
  }, [fetchItems]);

  const contactName = (id: number | null) =>
    id ? contacts.find((c) => c.id === id)?.name || `#${id}` : "—";

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
            Factures &amp; devis
          </h1>
          <p className="text-sm text-[#666] mt-1">
            {vatEnabled
              ? "TVA activée — facturation avec TVA."
              : "TVA non applicable — mention art. 293 B du CGI sur chaque facture."}
          </p>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] transition-colors"
        >
          <Plus size={15} /> Nouveau {tab === "invoice" ? "facture" : "devis"}
        </button>
      </div>

      <div className="flex gap-1 mb-6 bg-[#111] border border-[#222] rounded-full p-1 w-fit">
        <button
          onClick={() => setTab("invoice")}
          className={`px-5 py-2 rounded-full text-sm font-medium transition-colors ${
            tab === "invoice" ? "bg-[#F2C48D] text-black" : "text-[#B0B0B0] hover:text-white"
          }`}
        >
          Factures
        </button>
        <button
          onClick={() => setTab("quote")}
          className={`px-5 py-2 rounded-full text-sm font-medium transition-colors ${
            tab === "quote" ? "bg-[#F2C48D] text-black" : "text-[#B0B0B0] hover:text-white"
          }`}
        >
          Devis
        </button>
      </div>

      {error && (
        <div className="mb-4 bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-2xl p-4 text-sm flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)}>
            <X size={16} />
          </button>
        </div>
      )}

      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#F2C48D]" />
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-12 text-[#666] text-sm">
            <FileText size={32} className="mx-auto mb-3 opacity-30" />
            Aucun {tab === "invoice" ? "facture" : "devis"} pour l'instant.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase">Numéro</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase">Date</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase">Client</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase">Total TTC</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase">Statut</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((inv, idx) => (
                <tr key={inv.id} className={`hover:bg-[#1a1a1a] ${idx > 0 ? "border-t border-[#1a1a1a]" : ""}`}>
                  <td className="px-5 py-3.5 font-medium text-white">{inv.number}</td>
                  <td className="px-5 py-3.5 text-[#B0B0B0] whitespace-nowrap">{inv.date}</td>
                  <td className="px-5 py-3.5 text-[#B0B0B0]">{contactName(inv.contact_id)}</td>
                  <td className="px-5 py-3.5 text-right text-[#F2C48D] font-semibold whitespace-nowrap">
                    {eurFormatter.format(inv.total)}
                  </td>
                  <td className="px-5 py-3.5 text-[#B0B0B0] text-xs">{inv.status}</td>
                  <td className="px-5 py-3.5 text-right">
                    <a
                      href={`/api/invoices/${inv.id}/pdf`}
                      className="p-1.5 text-[#666] hover:text-white rounded-lg hover:bg-[#222] inline-block"
                      title="Télécharger PDF"
                    >
                      <Download size={14} strokeWidth={1.5} />
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showForm && (
        <InvoiceFormModal
          type={tab}
          vatEnabled={vatEnabled}
          contacts={contacts}
          onClose={() => setShowForm(false)}
          onSaved={() => { setShowForm(false); fetchItems(); }}
        />
      )}
    </div>
  );
}

function InvoiceFormModal({
  type, vatEnabled, contacts, onClose, onSaved,
}: {
  type: "quote" | "invoice";
  vatEnabled: boolean;
  contacts: Contact[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [clientId, setClientId] = useState<string>("");
  const [lines, setLines] = useState<InvoiceLine[]>([
    { description: "", quantity: 1, unit_price: 0 },
  ]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const totalHT = lines.reduce((s, l) => s + l.quantity * l.unit_price, 0);
  const totalTTC = totalHT;

  function updateLine(idx: number, field: keyof InvoiceLine, value: any) {
    setLines((prev) => prev.map((l, i) => (i === idx ? { ...l, [field]: value } : l)));
  }

  function addLine() {
    setLines((prev) => [...prev, { description: "", quantity: 1, unit_price: 0 }]);
  }

  function removeLine(idx: number) {
    setLines((prev) => prev.filter((_, i) => i !== idx));
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await apiCall("/invoices/", {
        method: "POST",
        body: JSON.stringify({
          type,
          date,
          contact_id: clientId ? parseInt(clientId) : null,
          lines,
        }),
      });
      onSaved();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex justify-center items-start z-50 overflow-y-auto p-8" onClick={onClose}>
      <div className="bg-[#0a0a0a] border border-[#222] rounded-2xl w-full max-w-3xl p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-xl font-bold text-white">
            Nouveau {type === "invoice" ? "facture" : "devis"}
          </h2>
          <button onClick={onClose} className="text-[#666] hover:text-white p-1"><X size={18} /></button>
        </div>

        {error && <div className="mb-3 text-xs text-[#FF5252]">{error}</div>}

        <form onSubmit={handleSave} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[#B0B0B0] mb-1">Date</label>
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
                className="w-full bg-[#111] border border-[#222] rounded-xl px-3 py-2 text-sm text-white [color-scheme:dark]" />
            </div>
            <div>
              <label className="block text-xs text-[#B0B0B0] mb-1">Client</label>
              <select value={clientId} onChange={(e) => setClientId(e.target.value)}
                className="w-full bg-[#111] border border-[#222] rounded-xl px-3 py-2 text-sm text-white">
                <option value="">(aucun)</option>
                {contacts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-white">Lignes</h3>
              <button type="button" onClick={addLine} className="text-xs text-[#F2C48D] hover:underline">+ Ajouter une ligne</button>
            </div>
            <div className="space-y-2">
              {lines.map((l, idx) => (
                <div key={idx} className="grid grid-cols-12 gap-2 items-center">
                  <input type="text" value={l.description} onChange={(e) => updateLine(idx, "description", e.target.value)}
                    placeholder="Description" className="col-span-6 bg-[#111] border border-[#222] rounded-lg px-2 py-1.5 text-xs text-white" />
                  <input type="number" step="0.01" value={l.quantity} onChange={(e) => updateLine(idx, "quantity", parseFloat(e.target.value) || 0)}
                    placeholder="Qté" className="col-span-2 bg-[#111] border border-[#222] rounded-lg px-2 py-1.5 text-xs text-white" />
                  <input type="number" step="0.01" value={l.unit_price} onChange={(e) => updateLine(idx, "unit_price", parseFloat(e.target.value) || 0)}
                    placeholder="PU €" className="col-span-3 bg-[#111] border border-[#222] rounded-lg px-2 py-1.5 text-xs text-white" />
                  <button type="button" onClick={() => removeLine(idx)}
                    className="col-span-1 text-[#FF5252] hover:text-red-400 flex justify-center">
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="border-t border-[#1a1a1a] pt-4 space-y-1 text-sm">
            <div className="flex justify-between text-[#B0B0B0]">
              <span>Total HT</span>
              <span>{eurFormatter.format(totalHT)}</span>
            </div>
            {vatEnabled && (
              <div className="flex justify-between text-[#B0B0B0]">
                <span>TVA</span>
                <span>{eurFormatter.format(0)}</span>
              </div>
            )}
            <div className="flex justify-between text-[#F2C48D] font-semibold">
              <span>Total TTC</span>
              <span>{eurFormatter.format(totalTTC)}</span>
            </div>
            {!vatEnabled && (
              <p className="text-xs text-[#666] italic mt-2">
                TVA non applicable, art. 293 B du CGI.
              </p>
            )}
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-white border border-[#333] rounded-full">
              Annuler
            </button>
            <button type="submit" disabled={saving}
              className="px-5 py-2 text-sm font-semibold text-black bg-[#F2C48D] rounded-full disabled:opacity-50">
              {saving ? "Enregistrement…" : "Enregistrer"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
