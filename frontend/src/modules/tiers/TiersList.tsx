import { useEffect, useState, useCallback } from "react";
import { Plus, Pencil, Trash2, X, Search, Mail, Phone, MapPin, Users, GitMerge, AlertTriangle } from "lucide-react";
import EmptyState from "../../core/EmptyState";
import { useAuth } from "../../core/AuthContext";
import { rawFetch } from "../../api";
import { formatEuros, formatDate, txTone } from "../../utils/format";
import { CONTACT_TYPES } from "../../core/ContactCombobox";
import useDebounce from "../../utils/useDebounce";
import { inputClass, labelClass } from "../../core/formStyles";
import PageLoader from "../../core/PageLoader";

const PAGE_SIZE = 80;

async function apiTiers<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await rawFetch(`/tiers${path}`, {
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
  from_entity_type?: string;
  to_entity_type?: string;
}

type ContactForm = Omit<Contact, "id" | "created_at" | "updated_at">;

const emptyForm: ContactForm = { name: "", type: "other", email: "", phone: "", address: "", notes: "" };

const TYPE_LABELS: Record<string, string> = Object.fromEntries(CONTACT_TYPES.map((t) => [t.value, t.label]));
const TYPE_COLORS: Record<string, string> = {
  client: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  fournisseur: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  membre: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  sponsor: "bg-purple-500/15 text-purple-400 border-purple-500/30",
  other: "bg-[#222] text-text-secondary border-border-hover",
};

export default function TiersList() {
  const { isAdmin } = useAuth();
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const debouncedSearch = useDebounce(search, 320);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Contact | null>(null);
  const [form, setForm] = useState<ContactForm>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [selected, setSelected] = useState<Contact | null>(null);
  const [txns, setTxns] = useState<Transaction[]>([]);
  const [txnsLoading, setTxnsLoading] = useState(false);
  const [mergeMode, setMergeMode] = useState(false);
  const [mergeSearch, setMergeSearch] = useState("");
  const debouncedMergeSearch = useDebounce(mergeSearch, 250);
  const [mergeResults, setMergeResults] = useState<Contact[]>([]);
  const [mergeTarget, setMergeTarget] = useState<Contact | null>(null);
  const [merging, setMerging] = useState(false);

  function buildQuery(offset = 0) {
    const p = new URLSearchParams();
    if (debouncedSearch) p.set("search", debouncedSearch);
    if (typeFilter) p.set("type", typeFilter);
    p.set("limit", String(PAGE_SIZE));
    p.set("offset", String(offset));
    return `/?${p.toString()}`;
  }

  const fetchContacts = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiTiers<{ total: number; items: Contact[] }>(buildQuery(0));
      setContacts(data.items);
      setTotal(data.total);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, typeFilter]);

  useEffect(() => { fetchContacts(); }, [fetchContacts]);

  async function loadMore() {
    setLoadingMore(true);
    try {
      const data = await apiTiers<{ total: number; items: Contact[] }>(buildQuery(contacts.length));
      setContacts((prev) => [...prev, ...data.items]);
      setTotal(data.total);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoadingMore(false);
    }
  }

  // Recherche côté serveur, temporisée : évite de charger tout le carnet
  // (mesuré 60-110 ms et croissant avec l'historique) pour filtrer côté client.
  useEffect(() => {
    if (!mergeMode || debouncedMergeSearch.length < 2) { setMergeResults([]); return; }
    let cancelled = false;
    apiTiers<{ total: number; items: Contact[] }>(`/?search=${encodeURIComponent(debouncedMergeSearch)}&limit=20`)
      .then((data) => {
        if (cancelled) return;
        setMergeResults(data.items.filter((c) => c.id !== selected?.id));
      })
      .catch(() => { if (!cancelled) setMergeResults([]); });
    return () => { cancelled = true; };
  }, [debouncedMergeSearch, mergeMode, selected?.id]);

  function openCreate() { setEditing(null); setForm(emptyForm); setShowForm(true); setSelected(null); }
  function openEdit(c: Contact) {
    setEditing(c);
    setForm({ name: c.name, type: c.type, email: c.email, phone: c.phone, address: c.address, notes: c.notes });
    setShowForm(true);
    setSelected(null);
  }
  function cancelForm() { setShowForm(false); setEditing(null); setForm(emptyForm); }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      if (editing) {
        await apiTiers(`/${editing.id}`, { method: "PUT", body: JSON.stringify(form) });
      } else {
        await apiTiers("/", { method: "POST", body: JSON.stringify(form) });
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
      if (selected?.id === id) setSelected(null);
      fetchContacts();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function openDetail(c: Contact) {
    setSelected(c);
    setShowForm(false);
    setMergeMode(false);
    setMergeTarget(null);
    setMergeSearch("");
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

  async function handleMerge() {
    if (!selected || !mergeTarget) return;
    setMerging(true);
    try {
      await apiTiers(`/${selected.id}/merge-into/${mergeTarget.id}`, { method: "POST" });
      setSelected(null);
      setMergeMode(false);
      setMergeTarget(null);
      fetchContacts();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setMerging(false);
    }
  }

  function openMergeMode() {
    setMergeMode(true);
  }

  const hasMore = contacts.length < total;


  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>Contacts</h1>
          <p className="text-sm text-[#8a8a8a] mt-1">Clients, fournisseurs, membres, sponsors.</p>
        </div>
        {isAdmin && (
          <button onClick={openCreate} className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-full hover:bg-accent-sand transition-colors">
            <Plus size={15} /> Nouveau contact
          </button>
        )}
      </div>

      {error && (
        <div className="mb-4 bg-[#1a0a0a] border border-alert/30 text-alert rounded-2xl p-4 text-sm flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)} className="text-alert/70 hover:text-alert"><X size={16} /></button>
        </div>
      )}

      <div className="mb-5 flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8a8a8a]" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher nom, email, téléphone…"
            className="w-full bg-bg-card border border-border rounded-xl pl-9 pr-3 py-2.5 text-sm text-white focus:outline-none focus:border-accent-sand transition-colors placeholder-text-muted"
          />
        </div>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="bg-bg-card border border-border rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-accent-sand transition-colors"
        >
          <option value="">Tous les types</option>
          <option value="client">Client</option>
          <option value="fournisseur">Fournisseur</option>
          <option value="membre">Membre</option>
          <option value="sponsor">Sponsor</option>
          <option value="other">Autre</option>
        </select>
        {(search || typeFilter) && (
          <button onClick={() => { setSearch(""); setTypeFilter(""); }} className="text-sm text-[#8a8a8a] hover:text-white flex items-center gap-1 transition-colors">
            <X size={14} /> Effacer
          </button>
        )}
        {!loading && (
          <span className="text-xs text-[#555]">
            {contacts.length < total ? `${contacts.length} / ${total}` : `${total}`} contact{total > 1 ? "s" : ""}
          </span>
        )}
      </div>

      {isAdmin && showForm && (
        <div className="mb-6 bg-bg-card border border-border rounded-2xl p-6">
          <h2 className="text-base font-semibold text-white mb-5">{editing ? "Modifier le contact" : "Nouveau contact"}</h2>
          <form onSubmit={handleSave} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className={labelClass}>Nom</label>
              <input type="text" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={inputClass} placeholder="Nom du contact" />
            </div>
            <div>
              <label className={labelClass}>Type</label>
              <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} className={inputClass}>
                <option value="client">Client</option>
                <option value="fournisseur">Fournisseur</option>
                <option value="membre">Membre</option>
                <option value="sponsor">Sponsor</option>
                <option value="other">Autre</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Email</label>
              <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className={inputClass} placeholder="exemple@mail.fr" />
            </div>
            <div>
              <label className={labelClass}>Téléphone</label>
              <input type="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} className={inputClass} placeholder="06 00 00 00 00" />
            </div>
            <div className="sm:col-span-2">
              <label className={labelClass}>Adresse</label>
              <input type="text" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} className={inputClass} placeholder="Rue, ville, code postal…" />
            </div>
            <div className="sm:col-span-2">
              <label className={labelClass}>Notes</label>
              <textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} className={inputClass} rows={3} placeholder="Optionnel" />
            </div>
            <div className="sm:col-span-2 flex justify-end gap-3 pt-2">
              <button type="button" onClick={cancelForm} className="px-5 py-2.5 text-sm font-semibold text-white border border-border-hover rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors">Annuler</button>
              <button type="submit" disabled={saving} className="px-5 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-full hover:bg-accent-sand disabled:opacity-50 transition-colors">{saving ? "Enregistrement..." : "Enregistrer"}</button>
            </div>
          </form>
        </div>
      )}

      {!loading && contacts.length === 0 ? (
        <EmptyState
          icon={Users}
          title="Aucun contact pour l'instant"
          description="Ton carnet d'adresses : sponsors, fournisseurs, membres, organismes."
          examples={["Schneider Electric (sponsor)", "Marie Dupont (membre)"]}
          ctaLabel={isAdmin ? "Ajouter mon premier contact" : undefined}
          onCta={isAdmin ? openCreate : undefined}
        />
      ) : (
        <div className="bg-bg-card border border-border rounded-2xl overflow-hidden">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <PageLoader fullScreen={false} />
            </div>
          ) : (
            <>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#1a1a1a]">
                    <th className="px-5 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Nom</th>
                    <th className="px-5 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Type</th>
                    <th className="px-5 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Email</th>
                    <th className="px-5 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Téléphone</th>
                    <th className="px-5 py-3.5 text-right text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Actions</th>
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
                      <td className="px-5 py-3.5 text-text-secondary">{c.email || <span className="text-[#444]">—</span>}</td>
                      <td className="px-5 py-3.5 text-text-secondary">{c.phone || <span className="text-[#444]">—</span>}</td>
                      <td className="px-5 py-3.5 text-right" onClick={(e) => e.stopPropagation()}>
                        {!isAdmin ? null : confirmDelete === c.id ? (
                          <span className="inline-flex items-center gap-2">
                            <span className="text-xs text-[#8a8a8a]">Supprimer ?</span>
                            <button onClick={() => handleDelete(c.id)} className="text-xs font-medium text-alert hover:text-red-400">Oui</button>
                            <button onClick={() => setConfirmDelete(null)} className="text-xs font-medium text-[#8a8a8a] hover:text-white">Non</button>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1">
                            <button onClick={() => openEdit(c)} className="p-1.5 text-[#8a8a8a] hover:text-white rounded-lg hover:bg-[#222] transition-colors" title="Modifier">
                              <Pencil size={14} strokeWidth={1.5} />
                            </button>
                            <button onClick={() => setConfirmDelete(c.id)} className="p-1.5 text-[#8a8a8a] hover:text-alert rounded-lg hover:bg-[#222] transition-colors" title="Supprimer">
                              <Trash2 size={14} strokeWidth={1.5} />
                            </button>
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {hasMore && (
                <div className="border-t border-[#1a1a1a] px-5 py-4 flex items-center justify-between">
                  <span className="text-xs text-[#555]">{contacts.length} affichés sur {total}</span>
                  <button
                    onClick={loadMore}
                    disabled={loadingMore}
                    className="px-4 py-2 text-sm font-medium text-accent-sand border border-accent-sand/30 rounded-full hover:bg-accent-sand/10 disabled:opacity-50 transition-colors"
                  >
                    {loadingMore ? "Chargement…" : `Charger ${Math.min(PAGE_SIZE, total - contacts.length)} de plus`}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Panneau de détail */}
      {selected && (
        <div className="fixed inset-0 bg-black/60 flex justify-end z-50" onClick={() => setSelected(null)}>
          <div className="w-full max-w-md bg-[#0a0a0a] border-l border-border h-full overflow-y-auto p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between mb-6">
              <div>
                <h2 className="text-xl font-bold text-white">{selected.name}</h2>
                <span className={`inline-block mt-2 px-2 py-0.5 rounded-full text-xs border ${TYPE_COLORS[selected.type] || TYPE_COLORS.other}`}>
                  {TYPE_LABELS[selected.type] || selected.type}
                </span>
              </div>
              <button onClick={() => setSelected(null)} className="text-[#8a8a8a] hover:text-white p-1"><X size={18} /></button>
            </div>

            <div className="space-y-3 mb-6">
              {selected.email && (
                <div className="flex items-center gap-2 text-sm text-text-secondary">
                  <Mail size={14} className="text-[#8a8a8a]" />
                  <a href={`mailto:${selected.email}`} className="hover:text-accent-sand">{selected.email}</a>
                </div>
              )}
              {selected.phone && (
                <div className="flex items-center gap-2 text-sm text-text-secondary">
                  <Phone size={14} className="text-[#8a8a8a]" />
                  {selected.phone}
                </div>
              )}
              {selected.address && (
                <div className="flex items-start gap-2 text-sm text-text-secondary">
                  <MapPin size={14} className="text-[#8a8a8a] mt-0.5" />
                  <span>{selected.address}</span>
                </div>
              )}
              {selected.notes && (
                <div className="mt-3 text-sm text-text-secondary bg-bg-card border border-border rounded-xl p-3">{selected.notes}</div>
              )}
            </div>

            <div className="border-t border-[#1a1a1a] pt-4 mb-6">
              <h3 className="text-sm font-semibold text-white mb-3">Transactions liées ({txns.length})</h3>
              {txnsLoading ? (
                <div className="py-4 text-center text-[#8a8a8a] text-sm">Chargement…</div>
              ) : txns.length === 0 ? (
                <div className="py-4 text-center text-[#8a8a8a] text-sm">Aucune transaction liée.</div>
              ) : (
                <div className="space-y-2">
                  {txns.map((t) => (
                    <div key={t.id} className="bg-bg-card border border-border rounded-xl p-3 flex items-center justify-between">
                      <div>
                        <div className="text-sm text-white">{t.label || "—"}</div>
                        <div className="text-xs text-[#8a8a8a]">{formatDate(t.date)}</div>
                      </div>
                      {(() => {
                        const { color, sign } = txTone(t);
                        return (
                          <div className="text-sm font-semibold" style={{ color }}>
                            {sign}{formatEuros(t.amount)}
                          </div>
                        );
                      })()}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {isAdmin && (
            <div className="border-t border-[#1a1a1a] pt-4">
              {!mergeMode ? (
                <button onClick={openMergeMode} className="flex items-center gap-2 text-sm text-[#8a8a8a] hover:text-accent-sand transition-colors">
                  <GitMerge size={14} /> Fusionner avec un autre contact…
                </button>
              ) : mergeTarget ? (
                <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 space-y-3">
                  <div className="flex items-start gap-2">
                    <AlertTriangle size={15} className="text-amber-400 mt-0.5 flex-shrink-0" />
                    <p className="text-xs text-amber-300 leading-relaxed">
                      <span className="font-semibold">{selected.name}</span> sera supprimé. Toutes ses transactions, remboursements et factures seront réattribués à <span className="font-semibold">{mergeTarget.name}</span>. Irréversible.
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={handleMerge} disabled={merging} className="flex-1 px-4 py-2 text-sm font-semibold text-black bg-amber-400 rounded-full hover:bg-amber-300 disabled:opacity-50 transition-colors">
                      {merging ? "Fusion..." : "Confirmer la fusion"}
                    </button>
                    <button onClick={() => setMergeTarget(null)} className="px-4 py-2 text-sm text-[#8a8a8a] border border-border-hover rounded-full hover:text-white transition-colors">
                      Changer
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  <p className="text-xs text-[#8a8a8a] mb-2">Fusionner <span className="text-white">{selected.name}</span> dans :</p>
                  <div className="relative">
                    <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8a8a8a]" />
                    <input
                      type="text"
                      value={mergeSearch}
                      onChange={(e) => setMergeSearch(e.target.value)}
                      placeholder="Rechercher le contact cible…"
                      autoFocus
                      className="w-full bg-bg-card border border-border-hover rounded-xl pl-8 pr-3 py-2 text-sm text-white focus:outline-none focus:border-accent-sand placeholder-text-muted"
                    />
                  </div>
                  <div className="max-h-48 overflow-y-auto space-y-1">
                    {mergeSearch.length < 2 ? (
                      <p className="text-xs text-[#555] px-3 py-2">Tape au moins 2 caractères…</p>
                    ) : mergeResults.length === 0 ? (
                      <p className="text-xs text-[#555] px-3 py-2">Aucun résultat</p>
                    ) : mergeResults.slice(0, 20).map((c) => (
                      <button
                        key={c.id}
                        onClick={() => setMergeTarget(c)}
                        className="w-full text-left px-3 py-2 text-sm text-white hover:bg-[#1a1a1a] rounded-lg transition-colors flex items-center justify-between"
                      >
                        <span>{c.name}</span>
                        <span className={`text-xs px-1.5 py-0.5 rounded-full border ${TYPE_COLORS[c.type] || TYPE_COLORS.other}`}>
                          {TYPE_LABELS[c.type] || c.type}
                        </span>
                      </button>
                    ))}
                  </div>
                  <button onClick={() => setMergeMode(false)} className="text-xs text-[#555] hover:text-white transition-colors">Annuler</button>
                </div>
              )}
            </div>
            )}

            {isAdmin && (
            <div className="mt-6 flex gap-3">
              <button onClick={() => openEdit(selected)} className="flex-1 px-4 py-2 text-sm font-semibold text-white border border-border-hover rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors">
                Modifier
              </button>
            </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
