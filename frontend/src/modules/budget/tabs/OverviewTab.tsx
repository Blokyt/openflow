import { useEffect, useState, useCallback, type ReactElement } from "react";
import { api } from "../../../api";
import { FiscalYear } from "../../../core/FiscalYearContext";
import { formatEuros, eurosToCents, centsToEuros, COLOR_EXPENSE, COLOR_INCOME } from "../../../utils/format";
import { ChevronDown, ChevronRight } from "lucide-react";

interface Props { year: FiscalYear | null }

const EXPENSE = COLOR_EXPENSE;
const INCOME = COLOR_INCOME;

export default function OverviewTab({ year }: Props) {
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set());
  const [touched, setTouched] = useState(false);
  const [showN1, setShowN1] = useState(true);
  const [seeding, setSeeding] = useState(false);
  const [seedMsg, setSeedMsg] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!year) { setData(null); return; }
    setLoading(true);
    try {
      const d = await api.getBudgetView(year.id);
      setData(d);
      if (!touched) {
        // Déplie les groupes racines au premier affichage (catégories repliées).
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
  const showN1Cols = hasN1 && showN1;
  const totalExpN1: number = data.groups.reduce((s: number, g: any) => s + g.realized_expense_n1, 0);
  const totalIncN1: number = data.groups.reduce((s: number, g: any) => s + g.realized_income_n1, 0);

  function toggle(id: number) {
    setTouched(true);
    setExpanded((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  }

  function toggleCat(key: string) {
    setExpandedCats((prev) => {
      const n = new Set(prev);
      if (n.has(key)) n.delete(key); else n.add(key);
      return n;
    });
  }

  async function seed() {
    if (!year) return;
    setSeeding(true);
    setSeedMsg(null);
    try {
      const res = await api.seedBudgetFromRealized(year.id);
      setSeedMsg(
        res.created > 0
          ? `${res.created} ligne${res.created > 1 ? "s" : ""} pré-remplie${res.created > 1 ? "s" : ""} depuis « ${res.source_name} ».`
          : `Rien à pré-remplir : le budget reprend déjà tout le réel de « ${res.source_name} ».`,
      );
      await reload();
    } catch (e: any) {
      setSeedMsg(e?.message || "Échec de la récupération du réel.");
    } finally {
      setSeeding(false);
    }
  }

  const colCount = 6 + (showN1Cols ? 3 : 0);
  const rows: ReactElement[] = [];

  function pushCategory(node: any, cat: any, depth: number) {
    const key = `${node.entity_id}:${cat.category_id}`;
    const isOpen = expandedCats.has(key);
    const hasKids = Array.isArray(cat.children) && cat.children.length > 0;
    const net1 = cat.realized_income_n1 - cat.realized_expense_n1;
    rows.push(
      <tr key={`c-${key}`} className="border-t border-[#141414] bg-[#0c0c0c] text-[13px]">
        <td className="px-3 py-2 text-[#B0B0B0]" style={{ paddingLeft: 12 + depth * 18 + 18 }}>
          <div className="flex items-center gap-1.5">
            {hasKids ? (
              <button onClick={() => toggleCat(key)} className="text-[#666] hover:text-white">
                {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </button>
            ) : (
              <span className="text-[#555]">↳</span>
            )}
            <span className={hasKids ? "font-medium text-[#cfcfcf]" : ""}>{cat.category_name}</span>
          </div>
        </td>
        {(!hasKids && cat.category_id != null)
          ? <EditableBudget year={year!} node={node} cat={cat} direction="expense" onSaved={reload} />
          : <Num value={cat.allocated_expense} muted />}
        <Num value={cat.realized_expense} color={EXPENSE} />
        {(!hasKids && cat.category_id != null)
          ? <EditableBudget year={year!} node={node} cat={cat} direction="income" onSaved={reload} />
          : <Num value={cat.allocated_income} muted />}
        <Num value={cat.realized_income} color={INCOME} />
        <Num value={cat.realized_income - cat.realized_expense} signed />
        {showN1Cols && (
          <>
            <Num value={cat.realized_expense_n1} muted />
            <Num value={cat.realized_income_n1} muted />
            <Num value={net1} signed muted />
          </>
        )}
      </tr>,
    );
    if (isOpen && hasKids) {
      [...cat.children]
        .sort((a, b) => a.category_name.localeCompare(b.category_name, "fr"))
        .forEach((ch: any) => pushCategory(node, ch, depth + 1));
    }
  }

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
        {showN1Cols && (
          <>
            <Num value={node.realized_expense_n1} muted />
            <Num value={node.realized_income_n1} muted />
            <Num value={net1} signed muted />
          </>
        )}
      </tr>,
    );
    if (isOpen) {
      [...node.categories]
        .sort((a, b) => a.category_name.localeCompare(b.category_name, "fr"))
        .forEach((c: any) => pushCategory(node, c, depth + 1));
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
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-[#666]">
          Hiérarchie pôle / club / catégorie. Déplie une catégorie pour voir ses sous-catégories. Clique sur un montant de budget pour le modifier.
        </p>
        {hasN1 && (
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={seed}
              disabled={seeding}
              title="Pré-remplit les budgets vides à partir des transactions réelles de l'exercice précédent"
              className="text-xs font-semibold text-black bg-[#F2C48D] hover:bg-[#e8b87a] rounded-full px-3 py-1 disabled:opacity-50"
            >
              {seeding ? "Récupération…" : "Récupérer le réel de l'an dernier"}
            </button>
            <button
              onClick={() => setShowN1((v) => !v)}
              className="text-xs text-[#666] hover:text-white border border-[#222] rounded-full px-3 py-1"
            >
              {showN1 ? "Masquer l'exercice précédent" : "Comparer à l'exercice précédent"}
            </button>
          </div>
        )}
      </div>

      {seedMsg && (
        <p className="text-xs text-[#F2C48D] bg-[#1a140a] border border-[#F2C48D]/20 rounded-lg px-3 py-2">
          {seedMsg}
        </p>
      )}

      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-x-auto">
        <table className="w-full text-sm min-w-[1080px]">
          <thead>
            <tr className="border-b border-[#1a1a1a]">
              <Th align="left">Entité / Catégorie</Th>
              <Th color={EXPENSE}>Budget Dépenses</Th>
              <Th color={EXPENSE}>Réalisé Dépenses</Th>
              <Th color={INCOME}>Budget Recettes</Th>
              <Th color={INCOME}>Réalisé Recettes</Th>
              <Th>Solde</Th>
              {showN1Cols && (
                <>
                  <Th>Dépenses N-1</Th>
                  <Th>Recettes N-1</Th>
                  <Th>Solde N-1</Th>
                </>
              )}
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
              {showN1Cols && (
                <>
                  <td className="px-3 py-3 text-right font-semibold text-[#777]">{formatEuros(totalExpN1)}</td>
                  <td className="px-3 py-3 text-right font-semibold text-[#777]">{formatEuros(totalIncN1)}</td>
                  <td className={`px-3 py-3 text-right font-bold ${totalIncN1 - totalExpN1 >= 0 ? "text-[#00C853]" : "text-[#FF5252]"}`}>{formatEuros(totalIncN1 - totalExpN1)}</td>
                </>
              )}
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
