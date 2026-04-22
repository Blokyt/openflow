import { useEffect, useState } from "react";
import { Check, Save } from "lucide-react";
import { api } from "../api";
import { eur } from "../utils/format";

interface EntityRow {
  id: number;
  name: string;
  parent_id: number | null;
  color?: string;
  balance_mode: "own" | "aggregate";
  depth: number;
}

interface RowState {
  // loaded state
  loadedMode: "own" | "aggregate";
  loadedDate: string;
  loadedAmount: string;
  // draft state
  mode: "own" | "aggregate";
  date: string;
  amount: string;
  // computed balance (read-only)
  currentBalance: number | null;
  // UI state
  saving: boolean;
  savedOk: boolean;
  error: string | null;
}

/** Flatten an entity tree (from /entities/tree) into a depth-annotated list */
function flattenTree(
  nodes: any[],
  depth = 0,
  result: EntityRow[] = []
): EntityRow[] {
  for (const node of nodes) {
    result.push({
      id: node.id,
      name: node.name,
      parent_id: node.parent_id ?? null,
      color: node.color,
      balance_mode: node.balance_mode ?? "own",
      depth,
    });
    if (node.children && node.children.length > 0) {
      flattenTree(node.children, depth + 1, result);
    }
  }
  return result;
}

export default function BalanceRefsSection() {
  const [entities, setEntities] = useState<EntityRow[]>([]);
  const [rows, setRows] = useState<Record<number, RowState>>({});
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      // Use the tree endpoint to get hierarchy + depth; filter to internal type
      const tree = await api.getEntityTree();
      const flat = flattenTree(tree);

      // Load balance-refs and current balances for all entities in parallel
      const results = await Promise.all(
        flat.map((e) =>
          Promise.all([
            api.getBalanceRef(e.id).catch(() => ({ reference_date: null, reference_amount: 0 })),
            api.getEntityBalance(e.id).catch(() => null),
          ])
        )
      );

      const newRows: Record<number, RowState> = {};
      flat.forEach((e, i) => {
        const [ref, bal] = results[i];
        const date = ref.reference_date ?? "";
        const amount = ref.reference_amount != null ? String(ref.reference_amount) : "";
        const currentBalance = bal?.balance ?? null;
        newRows[e.id] = {
          loadedMode: e.balance_mode,
          loadedDate: date,
          loadedAmount: amount,
          mode: e.balance_mode,
          date,
          amount,
          currentBalance,
          saving: false,
          savedOk: false,
          error: null,
        };
      });

      setEntities(flat);
      setRows(newRows);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function updateRow(id: number, patch: Partial<RowState>) {
    setRows((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  }

  function isDirty(id: number): boolean {
    const r = rows[id];
    if (!r) return false;
    return r.mode !== r.loadedMode || r.date !== r.loadedDate || r.amount !== r.loadedAmount;
  }

  function hasDateHint(id: number): boolean {
    const r = rows[id];
    if (!r) return false;
    const amt = parseFloat(r.amount);
    return !r.date && !isNaN(amt) && amt !== 0;
  }

  async function handleSave(entity: EntityRow) {
    const r = rows[entity.id];
    if (!r) return;
    updateRow(entity.id, { saving: true, error: null, savedOk: false });
    try {
      const modeChanged = r.mode !== r.loadedMode;
      const refChanged = r.date !== r.loadedDate || r.amount !== r.loadedAmount;

      if (modeChanged) {
        await api.updateEntityNode(entity.id, { balance_mode: r.mode });
      }
      if (refChanged) {
        await api.updateBalanceRef(entity.id, {
          reference_date: r.date || null,
          reference_amount: r.amount !== "" ? parseFloat(r.amount) : 0,
        });
      }

      // Refresh balance after save
      const [newRef, newBal] = await Promise.all([
        api.getBalanceRef(entity.id).catch(() => ({ reference_date: null, reference_amount: 0 })),
        api.getEntityBalance(entity.id).catch(() => null),
      ]);
      const newDate = newRef.reference_date ?? "";
      const newAmount = newRef.reference_amount != null ? String(newRef.reference_amount) : "";

      updateRow(entity.id, {
        saving: false,
        savedOk: true,
        error: null,
        loadedMode: r.mode,
        loadedDate: newDate,
        loadedAmount: newAmount,
        date: newDate,
        amount: newAmount,
        currentBalance: newBal?.balance ?? null,
      });

      // Clear the success check after 2s
      setTimeout(() => updateRow(entity.id, { savedOk: false }), 2000);
    } catch (err: any) {
      updateRow(entity.id, {
        saving: false,
        error: err.message || "Erreur lors de la sauvegarde",
      });
    }
  }

  if (loading) {
    return (
      <section id="balances" className="mb-8">
        <h2 className="text-base font-semibold text-white mb-3">Soldes de référence</h2>
        <div className="bg-[#111] border border-[#222] rounded-2xl p-5 flex items-center justify-center h-20">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[#F2C48D]" />
        </div>
      </section>
    );
  }

  if (entities.length === 0) return null;

  return (
    <section id="balances" className="mb-8">
      <h2 className="text-base font-semibold text-white mb-3">Soldes de référence</h2>
      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
        {/* Intro */}
        <div className="px-5 pt-5 pb-4 border-b border-[#1a1a1a]">
          <p className="text-xs text-[#999] leading-relaxed">
            Saisis le solde réel de chaque entité à une date donnée. Les dates peuvent être différentes.
          </p>
          <p className="text-xs text-[#999] leading-relaxed mt-1.5">
            Mode <span className="text-white font-medium">Agrégé</span> : pour une entité racine sans compte propre (ex : BDA), le solde saisi représente le solde bancaire total (entité + enfants). Le solde propre est alors dérivé automatiquement.
          </p>
        </div>

        {/* Table header */}
        <div className="hidden md:grid grid-cols-[1fr_110px_130px_160px_130px_44px] gap-x-3 px-5 py-2.5 border-b border-[#1a1a1a]">
          <span className="text-xs font-semibold uppercase tracking-wider text-[#555]">Entité</span>
          <span className="text-xs font-semibold uppercase tracking-wider text-[#555]">Mode</span>
          <span className="text-xs font-semibold uppercase tracking-wider text-[#555]">Date réf.</span>
          <span className="text-xs font-semibold uppercase tracking-wider text-[#555]">Solde de référence</span>
          <span className="text-xs font-semibold uppercase tracking-wider text-[#555]">Solde calculé</span>
          <span />
        </div>

        {/* Rows */}
        {entities.map((entity, idx) => {
          const r = rows[entity.id];
          if (!r) return null;
          const dirty = isDirty(entity.id);
          const hint = hasDateHint(entity.id);
          const isRoot = entity.parent_id === null;

          return (
            <div
              key={entity.id}
              className={`${idx > 0 ? "border-t border-[#1a1a1a]" : ""} px-5 py-3 hover:bg-[#1a1a1a] transition-colors`}
            >
              {/* Mobile label */}
              <div className="md:hidden text-xs text-[#666] mb-2 font-medium">{entity.name}</div>

              <div className="grid grid-cols-1 md:grid-cols-[1fr_110px_130px_160px_130px_44px] gap-x-3 gap-y-2 items-center">

                {/* Entity name */}
                <div
                  className="flex items-center gap-2 min-w-0"
                  style={{ paddingLeft: `${entity.depth * 16}px` }}
                >
                  {entity.color && (
                    <span
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ backgroundColor: entity.color }}
                    />
                  )}
                  <span className="text-sm text-white truncate">{entity.name}</span>
                </div>

                {/* Mode toggle */}
                <div>
                  {isRoot ? (
                    <select
                      value={r.mode}
                      onChange={(e) => updateRow(entity.id, { mode: e.target.value as "own" | "aggregate" })}
                      className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none focus:border-[#F2C48D] cursor-pointer"
                    >
                      <option value="own">Autonome</option>
                      <option value="aggregate">Agrégé</option>
                    </select>
                  ) : (
                    <span className="text-xs text-[#555]">Autonome</span>
                  )}
                </div>

                {/* Reference date */}
                <div className="flex flex-col gap-1">
                  <input
                    type="date"
                    value={r.date}
                    onChange={(e) => updateRow(entity.id, { date: e.target.value })}
                    className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none focus:border-[#F2C48D] [color-scheme:dark]"
                  />
                </div>

                {/* Reference amount */}
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      step="0.01"
                      value={r.amount}
                      onChange={(e) => updateRow(entity.id, { amount: e.target.value })}
                      placeholder="0"
                      className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none focus:border-[#F2C48D]"
                    />
                    <span className="text-xs text-[#555] flex-shrink-0">€</span>
                  </div>
                  {r.mode === "aggregate" && (
                    <span className="text-[10px] text-[#F2C48D]/70 leading-tight">solde agrégé bancaire</span>
                  )}
                  {hint && (
                    <span className="text-[10px] text-[#FF5252]/80 leading-tight">
                      Indique une date pour que le solde soit pris en compte
                    </span>
                  )}
                </div>

                {/* Current balance (read-only) */}
                <div className="text-sm text-right">
                  {r.currentBalance !== null ? (
                    <span className={r.currentBalance >= 0 ? "text-[#00C853]" : "text-[#FF5252]"}>
                      {eur.format(r.currentBalance)}
                    </span>
                  ) : (
                    <span className="text-[#444]">—</span>
                  )}
                </div>

                {/* Save button / feedback */}
                <div className="flex items-center justify-end h-8">
                  {r.savedOk ? (
                    <Check size={16} className="text-[#00C853]" />
                  ) : r.error ? (
                    <span className="text-[10px] text-[#FF5252] leading-tight text-right max-w-[80px]">{r.error}</span>
                  ) : dirty ? (
                    <button
                      onClick={() => handleSave(entity)}
                      disabled={r.saving}
                      className="p-1.5 rounded-lg bg-[#F2C48D]/10 border border-[#F2C48D]/30 text-[#F2C48D] hover:bg-[#F2C48D]/20 transition-colors disabled:opacity-50"
                      title="Enregistrer"
                    >
                      {r.saving ? (
                        <div className="animate-spin rounded-full h-3.5 w-3.5 border-b border-[#F2C48D]" />
                      ) : (
                        <Save size={14} />
                      )}
                    </button>
                  ) : null}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
