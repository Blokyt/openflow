import { useEffect, useState, useCallback, type ReactElement } from "react";
import { api } from "../../../api";
import { FiscalYear } from "../../../core/FiscalYearContext";
import { formatEuros, eurosToCents, centsToEuros, budgetColor } from "../../../utils/format";
import { ChevronDown, ChevronRight } from "lucide-react";

interface Props { year: FiscalYear | null }

const EXPENSE = "#FF8A5B";
const INCOME = "#00C853";

export default function OverviewTab({ year }: Props) {
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [touched, setTouched] = useState(false);
  const [showN1, setShowN1] = useState(false);

  const reload = useCallback(async () => {
    if (!year) { setData(null); return; }
    setLoading(true);
    try {
      const d = await api.getBudgetView(year.id);
      setData(d);
      if (!touched) {
        // Déplie les groupes racines au premier affichage.
        setExpanded(new Set(d.groups.map((g: any) => g.entity_id)));
      }
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year?.id]);

  useEffect(() => { reload(); }, [reload]);

  if (!year) return <p className="text-sm text-[#666]">Crée un exercice pour voir le suivi.</p>;
  if (loading && !data) return <p className="text-sm text-[#666]">Chargement…</p>;
  if (!data) return null;

  const hasN1: boolean = data.previous_fiscal_year_id !== null;
  const t = data.totals;

  function toggle(id: number) {
    setTouched(true);
    setExpanded((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  }

  const colCount = 7 + (hasN1 && showN1 ? 1 : 0);
  const rows: ReactElement[] = [];

  function pushEntity(node: any, depth: number) {
    const isOpen = expanded.has(node.entity_id);
    const hasKids = node.children.length > 0 || node.categories.length > 0;
    const net1 = node.realized_income_n1 - node.realized_expense_n1;
    rows.push(
      <tr key={`e-${node.entity_id}`} className="border-t border-[#1a1a1a] hover:bg-[#151515]">
        <td className="px-3 py-2.5" style={{ paddingLeft: 12 + depth * 18 }}>
          <div className="flex items-center gap-1.5">
            {hasKids ? (
              <button onClick={() => toggle(node.entity_id)} className="text-[#666] hover:text-white">
                {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </button>
            ) : <span className="inline-block w-3.5" />}
            <span className={depth === 0 ? "font-semibold text-white" : "font-medium text-[#e5e5e5]"}>{node.entity_name}</span>
          </div>
        </td>
        <Num value={node.allocated_expense} muted />
        <Num value={node.realized_expense} color={EXPENSE} />
        <Num value={node.allocated_income} muted />
        <Num value={node.realized_income} color={INCOME} />
        <Num value={node.realized_net} signed />
        <td className="px-3 py-2.5 text-right text-xs" style={{ color: budgetColor(node.coverage_pct) }}>
          {node.realized_expense > 0 ? `${node.coverage_pct.toFixed(0)} %` : "—"}
        </td>
        {hasN1 && showN1 && <Num value={net1} signed muted />}
      </tr>,
    );
    if (isOpen) {
      node.categories.forEach((c: any) =>
        rows.push(
          <CategoryRow
            key={`c-${node.entity_id}-${c.category_id}`}
            year={year!}
            node={node}
            cat={c}
            depth={depth + 1}
            hasN1={hasN1 && showN1}
            onSaved={reload}
          />,
        ),
      );
      [...node.children]
        .sort((a, b) => a.entity_name.localeCompare(b.entity_name, "fr"))
        .forEach((ch: any) => pushEntity(ch, depth + 1));
    }
  }

  [...data.groups]
    .sort((a, b) => a.entity_name.localeCompare(b.entity_name, "fr"))
    .forEach((g: any) => pushEntity(g, 0));

  const Th = ({ children, color, align = "right" }: { children?: React.ReactNode; color?: string; align?: string }) => (
    <th className={`px-3 py-2.5 text-${align} text-xs font-medium uppercase tracking-wide`} style={{ color: color ?? "#666" }}>
      {children}
    </th>
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-[#666]">
          Hiérarchie pôle / club / catégorie. Clique sur un montant de budget pour le modifier.
        </p>
        {hasN1 && (
          <button
            onClick={() => setShowN1((v) => !v)}
            className="text-xs text-[#666] hover:text-white border border-[#222] rounded-full px-3 py-1"
          >
            {showN1 ? "Masquer N-1" : "Comparer à N-1"}
          </button>
        )}
      </div>

      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-x-auto">
        <table className="w-full text-sm min-w-[760px]">
          <thead>
            <tr className="border-b border-[#1a1a1a]">
              <Th align="left">Entité / Catégorie</Th>
              <Th color={EXPENSE}>Budget dép.</Th>
              <Th color={EXPENSE}>Réalisé dép.</Th>
              <Th color={INCOME}>Budget rec.</Th>
              <Th color={INCOME}>Réalisé rec.</Th>
              <Th>Solde</Th>
              <Th>Couv.</Th>
              {hasN1 && showN1 && <Th>Solde N-1</Th>}
            </tr>
          </thead>
          <tbody>
            {rows.length > 0 ? rows : (
              <tr><td colSpan={colCount} className="px-4 py-8 text-center text-[#666]">
                Aucune entité interne. Crée des clubs dans le module Entités.
              </td></tr>
            )}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-[#222] bg-[#0a0a0a]">
              <td className="px-3 py-3 font-semibold text-white">Total</td>
              <td className="px-3 py-3 text-right font-semibold" style={{ color: EXPENSE }}>{formatEuros(t.allocated_expense)}</td>
              <td className="px-3 py-3 text-right font-semibold" style={{ color: EXPENSE }}>{formatEuros(t.realized_expense)}</td>
              <td className="px-3 py-3 text-right font-semibold" style={{ color: INCOME }}>{formatEuros(t.allocated_income)}</td>
              <td className="px-3 py-3 text-right font-semibold" style={{ color: INCOME }}>{formatEuros(t.realized_income)}</td>
              <td className={`px-3 py-3 text-right font-bold ${t.realized_net >= 0 ? "text-[#00C853]" : "text-[#FF5252]"}`}>{formatEuros(t.realized_net)}</td>
              <td className="px-3 py-3" />
              {hasN1 && showN1 && <td className="px-3 py-3" />}
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}

function Num({ value, color, muted, signed }: { value: number; color?: string; muted?: boolean; signed?: boolean }) {
  let cls = "text-white";
  let style: React.CSSProperties = {};
  if (signed) cls = value >= 0 ? "text-[#00C853]" : "text-[#FF5252]";
  else if (muted) cls = "text-[#777]";
  else if (color) { style = { color }; cls = ""; }
  return (
    <td className={`px-3 py-2.5 text-right whitespace-nowrap ${cls}`} style={style}>
      {value ? formatEuros(value) : <span className="text-[#444]">—</span>}
    </td>
  );
}

function CategoryRow({
  year, node, cat, depth, hasN1, onSaved,
}: { year: FiscalYear; node: any; cat: any; depth: number; hasN1: boolean; onSaved: () => void }) {
  const net1 = cat.realized_income_n1 - cat.realized_expense_n1;
  return (
    <tr className="border-t border-[#141414] bg-[#0c0c0c] text-[13px]">
      <td className="px-3 py-2 text-[#B0B0B0]" style={{ paddingLeft: 12 + depth * 18 + 18 }}>
        <span className="text-[#555] mr-1">↳</span>{cat.category_name}
      </td>
      <EditableBudget year={year} node={node} cat={cat} direction="expense" onSaved={onSaved} />
      <Num value={cat.realized_expense} color={EXPENSE} />
      <EditableBudget year={year} node={node} cat={cat} direction="income" onSaved={onSaved} />
      <Num value={cat.realized_income} color={INCOME} />
      <Num value={cat.realized_income - cat.realized_expense} signed />
      <td className="px-3 py-2 text-right text-xs" style={{ color: budgetColor(cat.coverage_pct) }}>
        {cat.realized_expense > 0 ? `${cat.coverage_pct.toFixed(0)} %` : "—"}
      </td>
      {hasN1 && <Num value={net1} signed muted />}
    </tr>
  );
}

function EditableBudget({
  year, node, cat, direction, onSaved,
}: { year: FiscalYear; node: any; cat: any; direction: "expense" | "income"; onSaved: () => void }) {
  const allocId: number | null = direction === "expense" ? cat.allocation_id_expense : cat.allocation_id_income;
  const value: number = direction === "expense" ? cat.allocated_expense : cat.allocated_income;
  const color = direction === "expense" ? EXPENSE : INCOME;
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState("");
  const [busy, setBusy] = useState(false);

  function start() {
    setVal(value ? String(centsToEuros(value)) : "");
    setEditing(true);
  }

  async function save() {
    setBusy(true);
    try {
      const cents = eurosToCents(val);
      if (allocId) {
        await api.updateAllocation(allocId, { amount: cents });
      } else if (cents > 0) {
        await api.createAllocation(year.id, {
          entity_id: node.entity_id, category_id: cat.category_id, direction, amount: cents,
        });
      }
      setEditing(false);
      onSaved();
    } finally {
      setBusy(false);
    }
  }

  if (editing) {
    return (
      <td className="px-3 py-2 text-right">
        <input
          type="number"
          step="0.01"
          autoFocus
          value={val}
          disabled={busy}
          onChange={(e) => setVal(e.target.value)}
          onBlur={save}
          onKeyDown={(e) => {
            if (e.key === "Enter") save();
            if (e.key === "Escape") setEditing(false);
          }}
          className="w-24 bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1 text-sm text-white text-right focus:outline-none focus:border-[#F2C48D]"
        />
      </td>
    );
  }

  return (
    <td className="px-3 py-2 text-right whitespace-nowrap">
      <button onClick={start} className="hover:underline" style={{ color: value ? color : "#444" }} title="Modifier le budget">
        {value ? formatEuros(value) : "—"}
      </button>
    </td>
  );
}
