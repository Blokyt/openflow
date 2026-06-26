import { useEffect, useRef, useState } from "react";
import { UserPlus, X } from "lucide-react";
import { api } from "../../api";
import { Transaction, Category, Entity, Contact } from "../../types";
import { eurosToCents, centsToEuros } from "../../utils/format";

/** Retourne la date locale du jour au format YYYY-MM-DD (sans décalage UTC). */
function localToday(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

interface TransactionFormProps {
  initial?: Partial<Transaction>;
  onSave: (tx: Omit<Transaction, "id">) => void;
  onCancel: () => void;
}

const inputClass = "w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#444] [color-scheme:dark]";
const labelClass = "block text-sm font-medium text-[#B0B0B0] mb-1.5";

const CONTACT_TYPES: { value: string; label: string }[] = [
  { value: "membre", label: "Membre" },
  { value: "fournisseur", label: "Fournisseur" },
  { value: "client", label: "Client" },
  { value: "sponsor", label: "Sponsor" },
  { value: "other", label: "Autre" },
];

function ContactCombobox({
  contacts,
  value,
  onChange,
  onContactCreated,
  placeholder,
}: {
  contacts: Contact[];
  value: string;
  onChange: (id: string) => void;
  onContactCreated: (c: Contact) => void;
  placeholder: string;
}) {
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState("membre");
  const [saving, setSaving] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  const selected = contacts.find((c) => String(c.id) === value);

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
        setCreating(false);
      }
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  const filtered = contacts.filter((c) =>
    c.name.toLowerCase().includes(search.toLowerCase())
  );

  function selectContact(c: Contact) {
    onChange(String(c.id));
    setSearch("");
    setOpen(false);
    setCreating(false);
  }

  function clearContact() {
    onChange("");
    setSearch("");
  }

  async function handleCreate() {
    if (!newName.trim()) return;
    setSaving(true);
    try {
      const created = await api.createContact({ name: newName.trim(), type: newType });
      onContactCreated(created);
      onChange(String(created.id));
      setCreating(false);
      setNewName("");
      setOpen(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div ref={wrapRef} className="relative">
      {selected ? (
        <div className="flex items-center justify-between bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5">
          <span className="text-sm text-white">{selected.name}</span>
          <button
            type="button"
            onClick={clearContact}
            className="text-[#555] hover:text-[#FF5252] transition-colors ml-2"
          >
            <X size={14} />
          </button>
        </div>
      ) : (
        <input
          type="text"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setOpen(true); setCreating(false); }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder}
          className={inputClass}
          autoComplete="off"
        />
      )}

      {open && !selected && (
        <div className="absolute z-50 mt-1 w-full bg-[#111] border border-[#222] rounded-xl shadow-xl overflow-hidden max-h-52 overflow-y-auto">
          {filtered.length > 0 ? (
            filtered.slice(0, 30).map((c) => (
              <button
                key={c.id}
                type="button"
                onMouseDown={() => selectContact(c)}
                className="w-full text-left px-3 py-2 text-sm text-white hover:bg-[#1a1a1a] transition-colors flex items-center justify-between"
              >
                <span>{c.name}</span>
                <span className="text-xs text-[#555] ml-2">{c.type}</span>
              </button>
            ))
          ) : (
            <p className="px-3 py-2 text-sm text-[#555]">Aucun résultat</p>
          )}

          {!creating ? (
            <button
              type="button"
              onMouseDown={() => { setCreating(true); setOpen(true); }}
              className="w-full text-left px-3 py-2 text-sm text-[#F2C48D] hover:bg-[#1a1a1a] transition-colors flex items-center gap-2 border-t border-[#1a1a1a]"
            >
              <UserPlus size={13} /> Créer un nouveau contact
            </button>
          ) : (
            <div className="border-t border-[#1a1a1a] p-3 space-y-2">
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Nom du contact"
                className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] placeholder-[#444]"
                autoFocus
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleCreate(); } }}
              />
              <select
                value={newType}
                onChange={(e) => setNewType(e.target.value)}
                className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-sm text-white focus:outline-none focus:border-[#F2C48D]"
              >
                {CONTACT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
              <div className="flex gap-2">
                <button
                  type="button"
                  onMouseDown={handleCreate}
                  disabled={saving || !newName.trim()}
                  className="flex-1 px-3 py-1.5 text-xs font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-50 transition-colors"
                >
                  {saving ? "Création..." : "Créer"}
                </button>
                <button
                  type="button"
                  onMouseDown={() => setCreating(false)}
                  className="px-3 py-1.5 text-xs text-[#666] border border-[#333] rounded-full hover:text-white transition-colors"
                >
                  Annuler
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function TransactionForm({ initial, onSave, onCancel }: TransactionFormProps) {
  const [date, setDate] = useState(initial?.date ?? localToday());
  const [label, setLabel] = useState(initial?.label ?? "");
  // Le champ montant est en euros (pas en centimes). Si une transaction existante est passée,
  // son amount est en centimes -> on convertit en euros pour le pré-remplissage.
  const [amount, setAmount] = useState(initial?.amount !== undefined ? String(centsToEuros(initial.amount)) : "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [categoryId, setCategoryId] = useState<string>(
    initial?.category_id !== undefined ? String(initial.category_id) : ""
  );
  const [contactId, setContactId] = useState<string>(
    (initial as any)?.contact_id !== undefined ? String((initial as any).contact_id) : ""
  );
  const [fromEntityId, setFromEntityId] = useState<string>(
    initial?.from_entity_id !== undefined ? String(initial.from_entity_id) : ""
  );
  const [toEntityId, setToEntityId] = useState<string>(
    initial?.to_entity_id !== undefined ? String(initial.to_entity_id) : ""
  );
  const [payerContactId, setPayerContactId] = useState<string>(
    initial?.reimb_contact_id !== undefined ? String(initial.reimb_contact_id) : ""
  );
  const [categories, setCategories] = useState<Category[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.getCategories().then(setCategories).catch(() => {});
    api.getEntities().then(setEntities).catch(() => {});
    api.getContacts().then(setContacts).catch(() => {});
  }, []);

  function handleContactCreated(c: Contact) {
    setContacts((prev) => [...prev, c].sort((a, b) => a.name.localeCompare(b.name)));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const parsedAmount = parseFloat(String(amount).replace(",", "."));
    if (!label.trim()) { setError("Le libellé est obligatoire."); return; }
    if (isNaN(parsedAmount)) { setError("Le montant doit être un nombre."); return; }
    if (parsedAmount <= 0) { setError("Le montant doit être strictement positif."); return; }
    if (!fromEntityId) { setError("L'entité source est obligatoire."); return; }
    if (!toEntityId) { setError("L'entité destination est obligatoire."); return; }
    if (fromEntityId === toEntityId) { setError("La source et la destination doivent être différentes."); return; }
    setSubmitting(true);
    try {
      await onSave({
        date,
        label: label.trim(),
        // Conversion euros (saisie) -> centimes entiers (API)
        amount: eurosToCents(amount),
        description: description.trim() || undefined,
        category_id: categoryId ? parseInt(categoryId) : undefined,
        contact_id: contactId ? parseInt(contactId) : null,
        from_entity_id: parseInt(fromEntityId),
        to_entity_id: parseInt(toEntityId),
        payer_contact_id: payerContactId ? parseInt(payerContactId) : null,
      } as any);
    } catch (e: any) {
      setError(e.message);
      setSubmitting(false);
    }
  }

  const internalEntities = entities.filter((e) => e.type === "internal");
  const externalEntities = entities.filter((e) => e.type === "external");
  const fromEnt = entities.find((e) => String(e.id) === fromEntityId);
  const toEnt = entities.find((e) => String(e.id) === toEntityId);
  let flowSense: { label: string; color: string } | null = null;
  if (fromEnt && toEnt) {
    if (fromEnt.type === "external" && toEnt.type === "internal")
      flowSense = { label: "Recette (argent entrant)", color: "#00C853" };
    else if (fromEnt.type === "internal" && toEnt.type === "external")
      flowSense = { label: "Dépense (argent sortant)", color: "#FF5252" };
    else flowSense = { label: "Virement interne", color: "#B0B0B0" };
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && (
        <div className="bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-xl p-3 text-sm">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>Date</label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            required
            className={inputClass}
          />
        </div>
        <div>
          <label className={labelClass}>Montant (€)</label>
          <input
            type="number"
            step="0.01"
            min="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
            placeholder="0.00"
            className={inputClass}
          />
        </div>
      </div>

      <div>
        <label className={labelClass}>Libellé</label>
        <input
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          required
          placeholder="Ex: Loyer, Salaire..."
          className={inputClass}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>Source (d'où part l'argent)</label>
          <select value={fromEntityId} onChange={(e) => setFromEntityId(e.target.value)} required className={inputClass}>
            <option value="">— Choisir —</option>
            <optgroup label="Mes comptes (internes)">
              {internalEntities.map((ent) => (
                <option key={ent.id} value={ent.id}>{ent.name}</option>
              ))}
            </optgroup>
            <optgroup label="Tiers / Externes">
              {externalEntities.map((ent) => (
                <option key={ent.id} value={ent.id}>{ent.name}</option>
              ))}
            </optgroup>
          </select>
        </div>
        <div>
          <label className={labelClass}>Destination (où va l'argent)</label>
          <select value={toEntityId} onChange={(e) => setToEntityId(e.target.value)} required className={inputClass}>
            <option value="">— Choisir —</option>
            <optgroup label="Mes comptes (internes)">
              {internalEntities.map((ent) => (
                <option key={ent.id} value={ent.id}>{ent.name}</option>
              ))}
            </optgroup>
            <optgroup label="Tiers / Externes">
              {externalEntities.map((ent) => (
                <option key={ent.id} value={ent.id}>{ent.name}</option>
              ))}
            </optgroup>
          </select>
        </div>
      </div>

      {flowSense ? (
        <p className="-mt-1 text-xs text-[#666]">
          Sens détecté : <span className="font-semibold" style={{ color: flowSense.color }}>{flowSense.label}</span>
        </p>
      ) : (
        <p className="-mt-1 text-xs text-[#555]">
          Une dépense va d'un compte interne vers un tiers externe ; une recette fait l'inverse.
        </p>
      )}

      <div>
        <label className={labelClass}>Catégorie</label>
        <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)} className={inputClass}>
          <option value="">— Sans catégorie —</option>
          {categories.map((cat) => (
            <option key={cat.id} value={cat.id}>{cat.name}</option>
          ))}
        </select>
      </div>

      <div>
        <label className={labelClass}>Contact associé</label>
        <ContactCombobox
          contacts={contacts}
          value={contactId}
          onChange={setContactId}
          onContactCreated={handleContactCreated}
          placeholder="Rechercher un contact..."
        />
      </div>

      {contacts.length > 0 && (
        <div>
          <label className={labelClass}>Avance de frais (payée par)</label>
          <select value={payerContactId} onChange={(e) => setPayerContactId(e.target.value)} className={inputClass}>
            <option value="">— Aucun remboursement —</option>
            {contacts.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <p className="text-xs text-[#555] mt-1">
            Si un membre a avancé l'argent, sélectionne-le pour créer un remboursement automatique.
          </p>
        </div>
      )}

      <div>
        <label className={labelClass}>Description</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          placeholder="Optionnel"
          className={inputClass}
        />
      </div>

      <div className="flex justify-end gap-3 pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-5 py-2.5 text-sm font-semibold text-white border border-[#333] rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors"
        >
          Annuler
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-50 transition-colors"
        >
          {submitting ? "Enregistrement..." : "Enregistrer"}
        </button>
      </div>
    </form>
  );
}
