import { useEffect, useState } from "react";
import { api } from "../../api";
import { Transaction, Category, Entity, Contact } from "../../types";
import { useEntity } from "../../core/EntityContext";
import ContactCombobox from "../../core/ContactCombobox";
import { eurosToCents, centsToEuros } from "../../utils/format";
import { inputClass, labelClass } from "../../core/formStyles";

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

export default function TransactionForm({ initial, onSave, onCancel }: TransactionFormProps) {
  const { selectedEntity } = useEntity();
  const [date, setDate] = useState(initial?.date ?? localToday());
  const [label, setLabel] = useState(initial?.label ?? "");
  // Le champ montant est en euros (pas en centimes). Si une transaction existante est passée,
  // son amount est en centimes -> on convertit en euros pour le pré-remplissage.
  const [amount, setAmount] = useState(initial?.amount !== undefined ? String(centsToEuros(initial.amount)) : "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [categoryId, setCategoryId] = useState<string>(
    initial?.category_id != null ? String(initial.category_id) : ""
  );
  // `contact_id` peut valoir null sur une transaction existante : ne pré-remplir
  // que si un contact est réellement lié (String(null) donnerait "null", truthy).
  const [contactId, setContactId] = useState<string>(
    (initial as any)?.contact_id != null ? String((initial as any).contact_id) : ""
  );
  // En création avec un focus entité interne actif, la source est pré-remplie
  // avec l'entité focalisée (cas le plus fréquent : saisir une dépense du club).
  const [fromEntityId, setFromEntityId] = useState<string>(
    initial?.from_entity_id != null
      ? String(initial.from_entity_id)
      : selectedEntity && selectedEntity.type === "internal" && !initial
        ? String(selectedEntity.id)
        : ""
  );
  const [toEntityId, setToEntityId] = useState<string>(
    initial?.to_entity_id != null ? String(initial.to_entity_id) : ""
  );
  const [payerContactId, setPayerContactId] = useState<string>(
    initial?.reimb_contact_id != null ? String(initial.reimb_contact_id) : ""
  );
  const [categories, setCategories] = useState<Category[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  // Cache id -> nom des contacts déjà vus (sélection, création, pré-remplissage).
  // On ne charge jamais tout le carnet : la recherche se fait côté serveur.
  const [contactNames, setContactNames] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.getCategories().then(setCategories).catch(() => {});
    api.getEntities().then(setEntities).catch(() => {});
  }, []);

  // Pré-remplissage en édition : résout les noms des contacts déjà liés.
  useEffect(() => {
    const ids = [contactId, payerContactId].filter((id) => id && !contactNames[id]);
    ids.forEach((id) => {
      api.getContact(parseInt(id))
        .then((c) => setContactNames((prev) => ({ ...prev, [id]: c.name })))
        .catch(() => {});
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contactId, payerContactId]);

  function rememberContact(c: Contact) {
    setContactNames((prev) => ({ ...prev, [String(c.id)]: c.name }));
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
          <label htmlFor="tx-date" className={labelClass}>Date</label>
          <input
            id="tx-date"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            required
            className={inputClass}
          />
        </div>
        <div>
          <label htmlFor="tx-amount" className={labelClass}>Montant (€)</label>
          <input
            id="tx-amount"
            type="number"
            step="0.01"
            min="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
            placeholder="0,00"
            className={inputClass}
          />
        </div>
      </div>

      <div>
        <label htmlFor="tx-label" className={labelClass}>Libellé</label>
        <input
          id="tx-label"
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
          <label htmlFor="tx-from" className={labelClass}>Source (d'où part l'argent)</label>
          <select id="tx-from" value={fromEntityId} onChange={(e) => setFromEntityId(e.target.value)} required className={inputClass}>
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
          <label htmlFor="tx-to" className={labelClass}>Destination (où va l'argent)</label>
          <select id="tx-to" value={toEntityId} onChange={(e) => setToEntityId(e.target.value)} required className={inputClass}>
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
        <p className="-mt-1 text-xs text-[#8a8a8a]">
          Sens détecté : <span className="font-semibold" style={{ color: flowSense.color }}>{flowSense.label}</span>
        </p>
      ) : (
        <p className="-mt-1 text-xs text-[#555]">
          Une dépense va d'un compte interne vers un tiers externe ; une recette fait l'inverse.
        </p>
      )}

      <div>
        <label htmlFor="tx-category" className={labelClass}>Catégorie</label>
        <select id="tx-category" value={categoryId} onChange={(e) => setCategoryId(e.target.value)} className={inputClass}>
          <option value="">— Sans catégorie —</option>
          {categories.map((cat) => (
            <option key={cat.id} value={cat.id}>{cat.name}</option>
          ))}
        </select>
      </div>

      <div>
        <label className={labelClass}>Contact associé</label>
        <ContactCombobox
          value={contactId}
          selectedName={contactNames[contactId] ?? null}
          onChange={setContactId}
          onPick={rememberContact}
          placeholder="Rechercher un contact..."
        />
      </div>

      <div>
        <label className={labelClass}>Avance de frais (payée par)</label>
        <ContactCombobox
          value={payerContactId}
          selectedName={contactNames[payerContactId] ?? null}
          onChange={setPayerContactId}
          onPick={rememberContact}
          placeholder="Aucun remboursement, rechercher un membre..."
        />
        <p className="text-xs text-[#555] mt-1">
          Si un membre a avancé l'argent, sélectionne-le pour créer un remboursement automatique.
        </p>
      </div>

      <div>
        <label htmlFor="tx-description" className={labelClass}>Description</label>
        <textarea
          id="tx-description"
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
