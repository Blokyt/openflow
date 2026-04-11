import { useEffect, useState } from "react";
import { api } from "../../api";
import { Transaction, Category } from "../../types";

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
  const [categories, setCategories] = useState<Category[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.getCategories().then(setCategories).catch(() => {});
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const parsedAmount = parseFloat(amount);
    if (!label.trim()) { setError("Le libellé est obligatoire."); return; }
    if (isNaN(parsedAmount)) { setError("Le montant doit être un nombre."); return; }
    setSubmitting(true);
    try {
      await onSave({
        date,
        label: label.trim(),
        amount: parsedAmount,
        description: description.trim() || undefined,
        category_id: categoryId ? parseInt(categoryId) : undefined,
      });
    } catch (e: any) {
      setError(e.message);
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm">
          {error}
        </div>
      )}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Date</label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            required
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Montant (€)</label>
          <input
            type="number"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
            placeholder="0.00"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Libellé</label>
        <input
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          required
          placeholder="Ex: Loyer, Salaire..."
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Catégorie</label>
        <select
          value={categoryId}
          onChange={(e) => setCategoryId(e.target.value)}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
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
        <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          placeholder="Optionnel..."
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>
      <div className="flex justify-end gap-2 pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
        >
          Annuler
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50"
        >
          {submitting ? "Enregistrement..." : "Enregistrer"}
        </button>
      </div>
    </form>
  );
}
