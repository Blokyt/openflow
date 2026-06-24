import { useEffect, useState, useCallback } from "react";
import { api } from "../../../api";
import { FiscalYear } from "../../../core/FiscalYearContext";
import { Entity, Category } from "../../../types";
import { formatEuros, eurosToCents, centsToEuros } from "../../../utils/format";
import { Plus, Trash2, Pencil } from "lucide-react";

interface Props {
  year: FiscalYear | null;
  onChange: () => void;
}

export default function AllocationTab({ year, onChange }: Props) {
  const [allocations, setAllocations] = useState<any[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [adding, setAdding] = useState(false);
  const [newEntity, setNewEntity] = useState("");
  const [newCategory, setNewCategory] = useState("");
  const [newAmount, setNewAmount] = useState("");
  const [newDirection, setNewDirection] = useState<"expense" | "income">("expense");
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editAmount, setEditAmount] = useState("");

  useEffect(() => {
    Promise.all([api.getEntities(), api.getCategories()])
      .then(([e, c]) => { setEntities(e as any); setCategories(c as any); })
      .catch(() => {});
  }, []);

  const reloadAllocations = useCallback(async () => {
    if (!year) return;
    try {
      const a = await api.listAllocations(year.id);
      setAllocations(a);
    } catch (err: any) {
      setError(err.message);
    }
  }, [year?.id]);

  useEffect(() => { reloadAllocations(); }, [reloadAllocations]);

  if (!year) return <p className="text-sm text-[#666]">Crée un exercice d'abord.</p>;

  async function addRow() {
    setError(null);
    if (!newEntity || !newAmount) { setError("Entité et montant obligatoires."); return; }
    try {
      // La saisie est en euros -> envoyer en centimes à l'API
      await api.createAllocation(year!.id, {
        entity_id: parseInt(newEntity, 10),
        category_id: newCategory ? parseInt(newCategory, 10) : null,
        direction: newDirection,
        amount: eurosToCents(newAmount),
      });
      setNewEntity(""); setNewCategory(""); setNewAmount(""); setNewDirection("expense");
      setAdding(false);
      await reloadAllocations();
      onChange();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function remove(id: number) {
    try {
      await api.deleteAllocation(id);
      await reloadAllocations();
      onChange();
    } catch (err: any) {
      setError(err.message);
    }
  }

  function startEdit(a: any) {
    setError(null);
    setEditingId(a.id);
    // a.amount est en centimes -> euros pour la saisie
    setEditAmount(String(centsToEuros(a.amount)));
  }

  async function saveEdit() {
    if (editingId == null) return;
    try {
      await api.updateAllocation(editingId, { amount: eurosToCents(editAmount) });
      setEditingId(null);
      await reloadAllocations();
      onChange();
    } catch (err: any) {
      setError(err.message);
    }
  }

  const internalEntities = entities.filter((e: any) => e.type === "internal");

  return (
    <div className="space-y-4">
      {error && (
        <div className="bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-xl p-3 text-sm">
          {error}
        </div>
      )}

      <div className="flex items-center justify-between">
        <p className="text-sm text-[#B0B0B0]">
          {allocations.length} allocation(s). Laisse la catégorie vide pour une enveloppe globale de l'entité.
        </p>
        <button
          onClick={() => setAdding(true)}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-[#F2C48D] border border-[#F2C48D]/40 rounded-full hover:bg-[#F2C48D]/10"
        >
          <Plus size={14} /> Ajouter
        </button>
      </div>

      {adding && (
        <div className="bg-[#111] border border-[#222] rounded-xl p-4 flex items-end gap-3">
          <div className="flex-1">
            <label className="block text-xs text-[#666] mb-1">Entité</label>
            <select
              value={newEntity}
              onChange={(e) => setNewEntity(e.target.value)}
              className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-sm text-white"
            >
              <option value="">— Choisir —</option>
              {internalEntities.map((e: any) => (
                <option key={e.id} value={e.id}>{e.name}</option>
              ))}
            </select>
          </div>
          <div className="flex-1">
            <label className="block text-xs text-[#666] mb-1">Catégorie (facultatif)</label>
            <select
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
              className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-sm text-white"
            >
              <option value="">— Globale —</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-[#666] mb-1">Sens</label>
            <select
              value={newDirection}
              onChange={(e) => setNewDirection(e.target.value as "expense" | "income")}
              className="bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-sm text-white"
            >
              <option value="expense">Dépense</option>
              <option value="income">Recette</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-[#666] mb-1">Montant</label>
            <input
              type="number"
              step="0.01"
              value={newAmount}
              onChange={(e) => setNewAmount(e.target.value)}
              className="w-28 bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-sm text-white text-right"
            />
          </div>
          <button onClick={addRow} className="px-4 py-2 text-sm font-semibold text-black bg-[#F2C48D] rounded-full">
            OK
          </button>
          <button onClick={() => setAdding(false)} className="px-4 py-2 text-sm text-[#666]">
            Annuler
          </button>
        </div>
      )}

      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
        {allocations.length === 0 ? (
          <div className="py-8 text-center text-sm text-[#666]">Aucune allocation.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                <th className="px-4 py-3 text-left text-xs font-medium text-[#666] uppercase">Entité</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-[#666] uppercase">Catégorie</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-[#666] uppercase">Sens</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-[#666] uppercase">Montant</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-[#666] uppercase">Actions</th>
              </tr>
            </thead>
            <tbody>
              {allocations.map((a, idx) => {
                const ent = entities.find((e: any) => e.id === a.entity_id);
                const cat = a.category_id ? categories.find((c) => c.id === a.category_id) : null;
                return (
                  <tr key={a.id} className={idx > 0 ? "border-t border-[#1a1a1a]" : ""}>
                    <td className="px-4 py-3 text-white">{(ent as any)?.name ?? `#${a.entity_id}`}</td>
                    <td className="px-4 py-3 text-[#B0B0B0]">
                      {cat ? cat.name : <span className="text-[#666] italic">Globale</span>}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${a.direction === "income" ? "text-[#00C853] border-[#00C853]/30 bg-[#00C853]/10" : "text-[#FF8A5B] border-[#FF8A5B]/30 bg-[#FF8A5B]/10"}`}>
                        {a.direction === "income" ? "Recette" : "Dépense"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-medium text-white">
                      {editingId === a.id ? (
                        <input
                          type="number"
                          step="0.01"
                          value={editAmount}
                          onChange={(e) => setEditAmount(e.target.value)}
                          autoFocus
                          onKeyDown={(e) => {
                            if (e.key === "Enter") saveEdit();
                            if (e.key === "Escape") setEditingId(null);
                          }}
                          className="w-28 bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1 text-sm text-white text-right focus:outline-none focus:border-[#F2C48D]"
                        />
                      ) : (
                        formatEuros(a.amount)
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {editingId === a.id ? (
                        <span className="inline-flex items-center gap-2">
                          <button onClick={saveEdit} className="text-xs font-semibold text-[#F2C48D] hover:underline">
                            OK
                          </button>
                          <button onClick={() => setEditingId(null)} className="text-xs text-[#666] hover:text-white">
                            Annuler
                          </button>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1">
                          <button
                            onClick={() => startEdit(a)}
                            className="p-1.5 text-[#666] hover:text-white"
                            title="Modifier le montant"
                          >
                            <Pencil size={14} strokeWidth={1.5} />
                          </button>
                          <button
                            onClick={() => remove(a.id)}
                            className="p-1.5 text-[#666] hover:text-[#FF5252]"
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
