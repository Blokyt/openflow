import { useEffect, useState } from "react";
import { api } from "../../api";
import { Transaction, Category, Entity } from "../../types";

interface TransactionFormProps {
  initial?: Partial<Transaction>;
  onSave: (tx: Omit<Transaction, "id">) => void;
  onCancel: () => void;
}

export default function TransactionForm({ initial, onSave, onCancel }: TransactionFormProps) {
  const [date, setDate] = useState(initial?.date ?? new Date().toISOString().slice(0, 10));
  const [label, setLabel] = useState(initial?.label ?? "");
  const [amount, setAmount] = useState(initial?.amount !== undefined ? String(initial.amount) : "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [categoryId, setCategoryId] = useState<string>(
    initial?.category_id !== undefined ? String(initial.category_id) : ""
  );
  const [fromEntityId, setFromEntityId] = useState<string>(
    initial?.from_entity_id !== undefined ? String(initial.from_entity_id) : ""
  );
  const [toEntityId, setToEntityId] = useState<string>(
    initial?.to_entity_id !== undefined ? String(initial.to_entity_id) : ""
  );
  const [categories, setCategories] = useState<Category[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.getCategories().then(setCategories).catch(() => {});
    api.getEntities().then(setEntities).catch(() => {});
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const parsedAmount = parseFloat(amount);
    if (!label.trim()) { setError("Le libellé est obligatoire."); return; }
    if (isNaN(parsedAmount)) { setError("Le montant doit être un nombre."); return; }
    if (!fromEntityId) { setError("L'entité source est obligatoire."); return; }
    if (!toEntityId) { setError("L'entité destination est obligatoire."); return; }
    if (fromEntityId === toEntityId) { setError("La source et la destination doivent être différentes."); return; }
    setSubmitting(true);
    try {
      await onSave({
        date,
        label: label.trim(),
        amount: parsedAmount,
        description: description.trim() || undefined,
        category_id: categoryId ? parseInt(categoryId) : undefined,
        from_entity_id: parseInt(fromEntityId),
        to_entity_id: parseInt(toEntityId),
      });
    } catch (e: any) {
      setError(e.message);
      setSubmitting(false);
    }
  }

  const inputClass = "w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#444] [color-scheme:dark]";
  const labelClass = "block text-sm font-medium text-[#B0B0B0] mb-1.5";

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
          <label className={labelClass}>Source</label>
          <select
            value={fromEntityId}
            onChange={(e) => setFromEntityId(e.target.value)}
            required
            className={inputClass}
          >
            <option value="">— Choisir —</option>
            {entities.map((ent) => (
              <option key={ent.id} value={ent.id}>
                {ent.name} {ent.type === "external" ? "(externe)" : ""}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={labelClass}>Destination</label>
          <select
            value={toEntityId}
            onChange={(e) => setToEntityId(e.target.value)}
            required
            className={inputClass}
          >
            <option value="">— Choisir —</option>
            {entities.map((ent) => (
              <option key={ent.id} value={ent.id}>
                {ent.name} {ent.type === "external" ? "(externe)" : ""}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div>
        <label className={labelClass}>Catégorie</label>
        <select
          value={categoryId}
          onChange={(e) => setCategoryId(e.target.value)}
          className={inputClass}
        >
          <option value="">— Sans catégorie —</option>
          {categories.map((cat) => (
            <option key={cat.id} value={cat.id}>
              {cat.name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className={labelClass}>Description</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          placeholder="Optionnel..."
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
