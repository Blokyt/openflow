import { useEffect, useState, useCallback } from "react";
import { Plus, Pencil, Trash2, X, Search, Mail, Phone, MapPin, Users } from "lucide-react";
import EmptyState from "../../core/EmptyState";

const BASE_URL = "/api";
const eurFormatter = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

async function apiTiers<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}/tiers${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || response.statusText);
  }
  return response.json();
}

interface Contact {
  id: number;
  name: string;
  type: string;
  email: string;
  phone: string;
  address: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

interface Transaction {
  id: number;
  date: string;
  label: string;
  amount: number;
}

type ContactForm = Omit<Contact, "id" | "created_at" | "updated_at">;

const emptyForm: ContactForm = {
  name: "",
  type: "other",
  email: "",
  phone: "",
  address: "",
  notes: "",
};

const TYPE_LABELS: Record<string, string> = {
  client: "Client",
  fournisseur: "Fournisseur",
  membre: "Membre",
  sponsor: "Sponsor",
  other: "Autre",
};

const TYPE_COLORS: Record<string, string> = {
  client: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  fournisseur: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  membre: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  sponsor: "bg-purple-500/15 text-purple-400 border-purple-500/30",
  other: "bg-[#222] text-[#B0B0B0] border-[#333]",
};

export default function TiersList() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Contact | null>(null);
  const [form, setForm] = useState<ContactForm>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [selected, setSelected] = useState<Contact | null>(null);
  const [txns, setTxns] = useState<Transaction[]>([]);
  const [txnsLoading, setTxnsLoading] = useState(false);

  const fetchContacts = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (typeFilter) params.set("type", typeFilter);
    const query = params.toString() ? `?${params.toString()}` : "";
    apiTiers<Contact[]>(`/${query}`)
      .then(setContacts)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [search, typeFilter]);

  useEffect(() => {
    fetchContacts();
  }, [fetchContacts]);

  function openCreate() {
    setEditing(null);
    setForm(emptyForm);
    setShowForm(true);
    setSelected(null);
  }

  function openEdit(c: Contact) {
    setEditing(c);
    setForm({
      name: c.name,
      type: c.type,
      email: c.email,
      phone: c.phone,
      address: c.address,
      notes: c.notes,
    });
    setShowForm(true);
    setSelected(null);
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
      if (editing) {
        await apiTiers(`/${editing.id}`, {
          method: "PUT",
          body: JSON.stringify(form),
        });
      } else {
        await apiTiers("/", {
          method: "POST",
          body: JSON.stringify(form),
        });
      }
      cancelForm();
      fetchContacts();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number) {
    try {
      await apiTiers(`/${id}`, { method: "DELETE" });
      setConfirmDelete(null);
      fetchContacts();
      if (selected?.id === id) setSelected(null);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function openDetail(c: Contact) {
    setSelected(c);
    setShowForm(false);
    setTxnsLoading(true);
    try {
      const data = await apiTiers<Transaction[]>(`/${c.id}/transactions`);
      setTxns(data);
    } catch (e: any) {
      setError(e.message);
      setTxns([]);
    } finally {
      setTxnsLoading(false);
    }
  }

  const inputClass = "w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#444]";
  const labelClass = "block text-sm font-medium text-[#B0B0B0] mb-1.5";

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
            Contacts &amp; Tiers
          </h1>
          <p className="text-sm text-[#666] mt-1">
            Clients, fournisseurs, membres, sponsors.
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

      <div className="mb-5 flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#666]" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher nom, email, téléphone…"
            className="w-full bg-[#111] border border-[#222] rounded-xl pl-9 pr-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#444]"
          />
        </div>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors"
        >
          <option value="">Tous les types</option>
          <option value="client">Client</option>
          <option value="fournisseur">Fournisseur</option>
          <option value="membre">Membre</option>
          <option value="sponsor">Sponsor</option>
          <option value="other">Autre</option>
        </select>
        {(search || typeFilter) && (
          <button
            onClick={() => { setSearch(""); setTypeFilter(""); }}
            className="text-sm text-[#666] hover:text-white flex items-center gap-1 transition-colors"
          >
            <X size={14} /> Effacer
          </button>
        )}
      </div>

      {showForm && (
        <div className="mb-6 bg-[#111] border border-[#222] rounded-2xl p-6">
          <h2 className="text-base font-semibold text-white mb-5">
            {editing ? "Modifier le contact" : "Nouveau contact"}
          </h2>
          <form onSubmit={handleSave} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className={labelClass}>Nom</label>
              <input
                type="text"
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className={inputClass}
                placeholder="Nom du contact"
              />
            </div>
            <div>
              <label className={labelClass}>Type</label>
              <select
                value={form.type}
                onChange={(e) => setForm({ ...form, type: e.target.value })}
                className={inputClass}
              >
                <option value="client">Client</option>
                <option value="fournisseur">Fournisseur</option>
                <option value="membre">Membre</option>
                <option value="sponsor">Sponsor</option>
                <option value="other">Autre</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Email</label>
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className={inputClass}
                placeholder="exemple@mail.fr"
              />
            </div>
            <div>
              <label className={labelClass}>Téléphone</label>
              <input
                type="tel"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                className={inputClass}
                placeholder="06 00 00 00 00"
              />
            </div>
            <div className="sm:col-span-2">
              <label className={labelClass}>Adresse</label>
              <input
                type="text"
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
                className={inputClass}
                placeholder="Rue, ville, code postal…"
              />
            </div>
            <div className="sm:col-span-2">
              <label className={labelClass}>Notes</label>
              <textarea
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                className={inputClass}
                rows={3}
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

      {!loading && contacts.length === 0 ? (
        <EmptyState
          icon={Users}
          title="Aucun contact pour l'instant"
          description="Ton carnet d'adresses : sponsors, fournisseurs, membres, organismes. Lie tes transactions à un contact pour suivre les flux par tiers."
          examples={[
            "Schneider Electric (sponsor) — email pour relances",
            "Marie Dupont (membre) — pour les remboursements",
          ]}
          ctaLabel="Ajouter mon premier contact"
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
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Nom</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Type</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Email</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Téléphone</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {contacts.map((c, idx) => (
                <tr
                  key={c.id}
                  onClick={() => openDetail(c)}
                  className={`cursor-pointer hover:bg-[#1a1a1a] transition-colors ${idx > 0 ? "border-t border-[#1a1a1a]" : ""}`}
                >
                  <td className="px-5 py-3.5 font-medium text-white">{c.name}</td>
                  <td className="px-5 py-3.5">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs border ${TYPE_COLORS[c.type] || TYPE_COLORS.other}`}>
                      {TYPE_LABELS[c.type] || c.type}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 text-[#B0B0B0]">
                    {c.email || <span className="text-[#444]">—</span>}
                  </td>
                  <td className="px-5 py-3.5 text-[#B0B0B0]">
                    {c.phone || <span className="text-[#444]">—</span>}
                  </td>
                  <td className="px-5 py-3.5 text-right" onClick={(e) => e.stopPropagation()}>
                    {confirmDelete === c.id ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="text-xs text-[#666]">Supprimer ?</span>
                        <button
                          onClick={() => handleDelete(c.id)}
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
                          onClick={() => openEdit(c)}
                          className="p-1.5 text-[#666] hover:text-white rounded-lg hover:bg-[#222] transition-colors"
                          title="Modifier"
                        >
                          <Pencil size={14} strokeWidth={1.5} />
                        </button>
                        <button
                          onClick={() => setConfirmDelete(c.id)}
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

      {selected && (
        <div className="fixed inset-0 bg-black/60 flex justify-end z-50" onClick={() => setSelected(null)}>
          <div
            className="w-full max-w-md bg-[#0a0a0a] border-l border-[#222] h-full overflow-y-auto p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between mb-6">
              <div>
                <h2 className="text-xl font-bold text-white">{selected.name}</h2>
                <span className={`inline-block mt-2 px-2 py-0.5 rounded-full text-xs border ${TYPE_COLORS[selected.type] || TYPE_COLORS.other}`}>
                  {TYPE_LABELS[selected.type] || selected.type}
                </span>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="text-[#666] hover:text-white p-1"
              >
                <X size={18} />
              </button>
            </div>

            <div className="space-y-3 mb-6">
              {selected.email && (
                <div className="flex items-center gap-2 text-sm text-[#B0B0B0]">
                  <Mail size={14} className="text-[#666]" />
                  <a href={`mailto:${selected.email}`} className="hover:text-[#F2C48D]">{selected.email}</a>
                </div>
              )}
              {selected.phone && (
                <div className="flex items-center gap-2 text-sm text-[#B0B0B0]">
                  <Phone size={14} className="text-[#666]" />
                  {selected.phone}
                </div>
              )}
              {selected.address && (
                <div className="flex items-start gap-2 text-sm text-[#B0B0B0]">
                  <MapPin size={14} className="text-[#666] mt-0.5" />
                  <span>{selected.address}</span>
                </div>
              )}
              {selected.notes && (
                <div className="mt-3 text-sm text-[#B0B0B0] bg-[#111] border border-[#222] rounded-xl p-3">
                  {selected.notes}
                </div>
              )}
            </div>

            <div className="border-t border-[#1a1a1a] pt-4">
              <h3 className="text-sm font-semibold text-white mb-3">
                Transactions liées ({txns.length})
              </h3>
              {txnsLoading ? (
                <div className="py-4 text-center text-[#666] text-sm">Chargement…</div>
              ) : txns.length === 0 ? (
                <div className="py-4 text-center text-[#666] text-sm">Aucune transaction liée.</div>
              ) : (
                <div className="space-y-2">
                  {txns.map((t) => (
                    <div key={t.id} className="bg-[#111] border border-[#222] rounded-xl p-3 flex items-center justify-between">
                      <div>
                        <div className="text-sm text-white">{t.label || "—"}</div>
                        <div className="text-xs text-[#666]">{t.date}</div>
                      </div>
                      <div className={`text-sm font-semibold ${t.amount >= 0 ? "text-emerald-400" : "text-[#FF5252]"}`}>
                        {eurFormatter.format(t.amount)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="mt-6 flex gap-3">
              <button
                onClick={() => openEdit(selected)}
                className="flex-1 px-4 py-2 text-sm font-semibold text-white border border-[#333] rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors"
              >
                Modifier
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
