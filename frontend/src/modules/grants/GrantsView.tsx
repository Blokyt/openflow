import { useEffect, useState, useCallback } from "react";
import { Plus, Pencil, Trash2, X, CheckCircle2, Clock, CircleDot } from "lucide-react";

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

interface Grant {
  id: number;
  name: string;
  grantor_contact_id: number | null;
  amount_granted: number;
  amount_received: number;
  date_granted: string;
  date_received: string | null;
  purpose: string;
  status: string;
  notes: string;
}

interface Contact {
  id: number;
  name: string;
  type: string;
}

interface Summary {
  total_granted: number;
  total_received: number;
  total_pending: number;
}

interface GrantForm {
  name: string;
  grantor_contact_id: string;
  amount_granted: string;
  amount_received: string;
  date_granted: string;
  date_received: string;
  purpose: string;
  status: string;
  notes: string;
}

const emptyForm: GrantForm = {
  name: "",
  grantor_contact_id: "",
  amount_granted: "",
  amount_received: "0",
  date_granted: new Date().toISOString().slice(0, 10),
  date_received: "",
  purpose: "",
  status: "pending",
  notes: "",
};

function toPayload(form: GrantForm) {
  return {
    name: form.name,
    grantor_contact_id: form.grantor_contact_id ? parseInt(form.grantor_contact_id) : null,
    amount_granted: parseFloat(form.amount_granted),
    amount_received: parseFloat(form.amount_received) || 0,
    date_granted: form.date_granted,
    date_received: form.date_received || null,
    purpose: form.purpose,
    status: form.status,
    notes: form.notes,
  };
}

const STATUS_CONFIG: Record<string, { label: string; icon: any; cls: string }> = {
  pending: { label: "En attente", icon: Clock, cls: "bg-amber-500/15 text-amber-400 border-amber-500/30" },
  partial: { label: "Partiellement reçue", icon: CircleDot, cls: "bg-blue-500/15 text-blue-400 border-blue-500/30" },
  received: { label: "Reçue", icon: CheckCircle2, cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" },
};

export default function GrantsView() {
  const [grants, setGrants] = useState<Grant[]>([]);
  const [summary, setSummary] = useState<Summary>({ total_granted: 0, total_received: 0, total_pending: 0 });
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Grant | null>(null);
  const [form, setForm] = useState<GrantForm>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const query = statusFilter ? `?status=${statusFilter}` : "";
      const [grantsData, summaryData] = await Promise.all([
        apiCall<Grant[]>(`/grants/${query}`),
        apiCall<Summary>("/grants/summary"),
      ]);
      setGrants(grantsData);
      setSummary(summaryData);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchAll();
    // contacts pour le picker grantor (best-effort, ignore si tiers inactif)
    apiCall<Contact[]>("/tiers/").then(setContacts).catch(() => setContacts([]));
  }, [fetchAll]);

  function openCreate() {
    setEditing(null);
    setForm(emptyForm);
    setShowForm(true);
  }

  function openEdit(g: Grant) {
    setEditing(g);
    setForm({
      name: g.name,
      grantor_contact_id: g.grantor_contact_id ? String(g.grantor_contact_id) : "",
      amount_granted: String(g.amount_granted),
      amount_received: String(g.amount_received),
      date_granted: g.date_granted,
      date_received: g.date_received || "",
      purpose: g.purpose,
      status: g.status,
      notes: g.notes,
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
        await apiCall(`/grants/${editing.id}`, { method: "PUT", body: JSON.stringify(payload) });
      } else {
        await apiCall("/grants/", { method: "POST", body: JSON.stringify(payload) });
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
      await apiCall(`/grants/${id}`, { method: "DELETE" });
      setConfirmDelete(null);
      fetchAll();
    } catch (e: any) {
      setError(e.message);
    }
  }

  const contactsById = new Map(contacts.map((c) => [c.id, c.name]));

  const inputClass = "w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#444] [color-scheme:dark]";
  const labelClass = "block text-sm font-medium text-[#B0B0B0] mb-1.5";

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
            Subventions
          </h1>
          <p className="text-sm text-[#666] mt-1">
            Suivi des subventions accordées et reçues.
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
          <div className="text-xs font-medium text-[#666] uppercase tracking-wider mb-2">Total accordé</div>
          <div className="text-2xl font-bold text-white">{eurFormatter.format(summary.total_granted)}</div>
        </div>
        <div className="bg-[#111] border border-[#222] rounded-2xl p-5">
          <div className="text-xs font-medium text-[#666] uppercase tracking-wider mb-2">Total reçu</div>
          <div className="text-2xl font-bold text-emerald-400">{eurFormatter.format(summary.total_received)}</div>
        </div>
        <div className="bg-[#111] border border-[#222] rounded-2xl p-5">
          <div className="text-xs font-medium text-[#666] uppercase tracking-wider mb-2">Restant à percevoir</div>
          <div className="text-2xl font-bold text-[#F2C48D]">{eurFormatter.format(summary.total_pending)}</div>
        </div>
      </div>

      <div className="mb-5 flex items-center gap-3">
        <label className="text-sm text-[#666]">Statut</label>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D]"
        >
          <option value="">Tous</option>
          <option value="pending">En attente</option>
          <option value="partial">Partielle</option>
          <option value="received">Reçue</option>
        </select>
      </div>

      {showForm && (
        <div className="mb-6 bg-[#111] border border-[#222] rounded-2xl p-6">
          <h2 className="text-base font-semibold text-white mb-5">
            {editing ? "Modifier la subvention" : "Nouvelle subvention"}
          </h2>
          <form onSubmit={handleSave} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="sm:col-span-2">
              <label className={labelClass}>Nom</label>
              <input
                type="text"
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className={inputClass}
                placeholder="Ex: Subvention Mines Paris 2026"
              />
            </div>
            <div>
              <label className={labelClass}>Organisme (tiers)</label>
              <select
                value={form.grantor_contact_id}
                onChange={(e) => setForm({ ...form, grantor_contact_id: e.target.value })}
                className={inputClass}
              >
                <option value="">(aucun)</option>
                {contacts.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelClass}>Statut</label>
              <select
                value={form.status}
                onChange={(e) => setForm({ ...form, status: e.target.value })}
                className={inputClass}
              >
                <option value="pending">En attente</option>
                <option value="partial">Partielle</option>
                <option value="received">Reçue</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Montant accordé (EUR)</label>
              <input
                type="number"
                step="0.01"
                required
                value={form.amount_granted}
                onChange={(e) => setForm({ ...form, amount_granted: e.target.value })}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Montant reçu (EUR)</label>
              <input
                type="number"
                step="0.01"
                value={form.amount_received}
                onChange={(e) => setForm({ ...form, amount_received: e.target.value })}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Date d'octroi</label>
              <input
                type="date"
                required
                value={form.date_granted}
                onChange={(e) => setForm({ ...form, date_granted: e.target.value })}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Date de réception</label>
              <input
                type="date"
                value={form.date_received}
                onChange={(e) => setForm({ ...form, date_received: e.target.value })}
                className={inputClass}
              />
            </div>
            <div className="sm:col-span-2">
              <label className={labelClass}>Objet</label>
              <input
                type="text"
                value={form.purpose}
                onChange={(e) => setForm({ ...form, purpose: e.target.value })}
                className={inputClass}
                placeholder="Ex: financement gala annuel"
              />
            </div>
            <div className="sm:col-span-2">
              <label className={labelClass}>Notes</label>
              <textarea
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                className={inputClass}
                rows={2}
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
        ) : grants.length === 0 ? (
          <div className="text-center py-12 text-[#666] text-sm">
            Aucune subvention enregistrée.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Nom</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Organisme</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Statut</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Accordé</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Reçu</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Restant</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {grants.map((g, idx) => {
                const pending = g.amount_granted - g.amount_received;
                const cfg = STATUS_CONFIG[g.status] || STATUS_CONFIG.pending;
                const Icon = cfg.icon;
                return (
                  <tr key={g.id} className={`hover:bg-[#1a1a1a] transition-colors ${idx > 0 ? "border-t border-[#1a1a1a]" : ""}`}>
                    <td className="px-5 py-3.5 font-medium text-white">{g.name}</td>
                    <td className="px-5 py-3.5 text-[#B0B0B0]">
                      {g.grantor_contact_id
                        ? contactsById.get(g.grantor_contact_id) || `#${g.grantor_contact_id}`
                        : <span className="text-[#444]">—</span>}
                    </td>
                    <td className="px-5 py-3.5">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border ${cfg.cls}`}>
                        <Icon size={11} /> {cfg.label}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-right text-white whitespace-nowrap">
                      {eurFormatter.format(g.amount_granted)}
                    </td>
                    <td className="px-5 py-3.5 text-right text-emerald-400 whitespace-nowrap">
                      {eurFormatter.format(g.amount_received)}
                    </td>
                    <td className="px-5 py-3.5 text-right text-[#F2C48D] font-semibold whitespace-nowrap">
                      {eurFormatter.format(pending)}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      {confirmDelete === g.id ? (
                        <span className="inline-flex items-center gap-2">
                          <span className="text-xs text-[#666]">Supprimer ?</span>
                          <button onClick={() => handleDelete(g.id)} className="text-xs font-medium text-[#FF5252] hover:text-red-400">Oui</button>
                          <button onClick={() => setConfirmDelete(null)} className="text-xs font-medium text-[#666] hover:text-white">Non</button>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1">
                          <button
                            onClick={() => openEdit(g)}
                            className="p-1.5 text-[#666] hover:text-white rounded-lg hover:bg-[#222] transition-colors"
                            title="Modifier"
                          >
                            <Pencil size={14} strokeWidth={1.5} />
                          </button>
                          <button
                            onClick={() => setConfirmDelete(g.id)}
                            className="p-1.5 text-[#666] hover:text-[#FF5252] rounded-lg hover:bg-[#222] transition-colors"
                            title="Supprimer"
                          >
                            <Trash2 size={14} strokeWidth={1.5} />
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
