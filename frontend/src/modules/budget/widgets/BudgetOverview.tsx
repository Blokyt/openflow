import { useFiscalYear } from "../../../core/FiscalYearContext";
import { useEntity } from "../../../core/EntityContext";
import { formatEuros, budgetColor, COLOR_INCOME } from "../../../utils/format";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { findGroupNode } from "../utils";

/** Une ligne du widget : un sens (dépense ou recette) d'une catégorie racine. */
interface Line {
  key: string;
  name: string;
  direction: "expense" | "income";
  realized: number;
  allocated: number;
}

interface Section {
  entityId: number;
  entityName: string;
  lines: Line[];
}

/** Lignes d'une entité : catégories racines, un sens par ligne, split dépenses/recettes.
 *  Une catégorie sans budget mais avec du réalisé reste visible (« Hors budget »). */
function buildLines(node: any): Line[] {
  const lines: Line[] = [];
  for (const cat of node.categories ?? []) {
    const name = cat.category_name;
    const key = `${node.entity_id}:${cat.category_id ?? "none"}`;
    if (cat.allocated_expense > 0 || cat.realized_expense > 0) {
      lines.push({
        key: `${key}:e`,
        name,
        direction: "expense",
        realized: cat.realized_expense,
        allocated: cat.allocated_expense,
      });
    }
    if (cat.allocated_income > 0 || cat.realized_income > 0) {
      lines.push({
        key: `${key}:i`,
        name,
        direction: "income",
        realized: cat.realized_income,
        allocated: cat.allocated_income,
      });
    }
  }
  // Anomalies d'abord (réalisé sans budget), puis taux de consommation décroissant.
  lines.sort((a, b) => {
    const pctA = a.allocated > 0 ? a.realized / a.allocated : Infinity;
    const pctB = b.allocated > 0 ? b.realized / b.allocated : Infinity;
    return pctB - pctA;
  });
  return lines;
}

/** Parcours entité puis sous-entités (ordre alphabétique), une section par entité active. */
function collectSections(node: any, out: Section[]) {
  const lines = buildLines(node);
  if (lines.length > 0) {
    out.push({ entityId: node.entity_id, entityName: node.entity_name, lines });
  }
  [...(node.children ?? [])]
    .sort((a: any, b: any) => a.entity_name.localeCompare(b.entity_name, "fr"))
    .forEach((ch: any) => collectSections(ch, out));
}

function BudgetLine({ line }: { line: Line }) {
  const hasBudget = line.allocated > 0;
  const pct = hasBudget ? (line.realized / line.allocated) * 100 : line.realized > 0 ? 100 : 0;
  const isOver = hasBudget && line.direction === "expense" && line.realized > line.allocated;
  const isIncome = line.direction === "income";
  // Dépense : vert -> doré -> rouge selon la consommation. Recette : toujours vert
  // (un budget de recettes atteint est une bonne nouvelle). Hors budget : rouge.
  const barColor = !hasBudget ? "#FF5252" : isIncome ? COLOR_INCOME : budgetColor(pct);

  return (
    <div>
      <div className="flex items-center justify-between text-xs mb-1.5">
        <span className="text-text-secondary truncate pr-2">
          {line.name}
          {isIncome && (
            <span className="ml-1.5 text-[10px] uppercase tracking-wide" style={{ color: COLOR_INCOME }}>
              Recettes
            </span>
          )}
        </span>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span className={`font-medium ${isOver ? "text-alert" : "text-white"}`}>
            {formatEuros(line.realized)}
          </span>
          {hasBudget ? (
            <span className="text-[#8a8a8a]">/ {formatEuros(line.allocated)}</span>
          ) : (
            <span className="text-alert font-medium">(Hors budget)</span>
          )}
        </div>
      </div>
      <div className="h-1.5 bg-[#1a1a1a] rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${Math.min(pct, 100)}%`, backgroundColor: barColor }}
        />
      </div>
    </div>
  );
}

interface Props {
  view: any | null;
  loading: boolean;
  error: string | null;
}

export default function BudgetOverview({ view, loading, error }: Props) {
  const { selectedYear } = useFiscalYear();
  const { selectedEntityId, selectedEntity } = useEntity();

  const shell = (body: React.ReactNode) => (
    <div className="bg-bg-card border border-border rounded-2xl p-6 flex flex-col h-full max-h-[400px]">
      <div className="flex items-center justify-between mb-4 gap-2">
        <p className="text-xs font-medium text-[#8a8a8a] uppercase tracking-wider truncate min-w-0">
          {selectedEntity ? `État des Budgets · ${selectedEntity.name}` : "État des Budgets"}
        </p>
        <Link to="/budget" className="text-xs text-accent-sand hover:underline inline-flex items-center gap-0.5 flex-shrink-0">
          Détail <ArrowRight size={11} />
        </Link>
      </div>
      {body}
    </div>
  );

  if (!selectedYear) {
    return shell(
      <p className="text-sm text-[#8a8a8a]">
        <Link to="/budget" className="text-accent-sand hover:underline">Crée un exercice</Link> pour activer le suivi.
      </p>,
    );
  }
  if (error) return shell(<p className="text-sm text-alert">{error}</p>);
  if (loading || !view) {
    return shell(
      <>
        <div className="h-2 bg-[#1a1a1a] rounded-full overflow-hidden mb-3 animate-pulse" />
        <p className="text-sm text-[#8a8a8a]">Chargement…</p>
      </>,
    );
  }

  // Même périmètre que la page Budget : l'entité sélectionnée et ses sous-entités.
  const scopedNode = selectedEntityId ? findGroupNode(view.groups ?? [], selectedEntityId) : null;
  const rootNodes: any[] = scopedNode ? [scopedNode] : (view.groups ?? []);

  const sections: Section[] = [];
  [...rootNodes]
    .sort((a: any, b: any) => a.entity_name.localeCompare(b.entity_name, "fr"))
    .forEach((n: any) => collectSections(n, sections));

  if (sections.length === 0) {
    return shell(
      <p className="text-sm text-[#8a8a8a]">
        Aucun budget alloué ni de flux sur ce périmètre.{" "}
        <Link to="/budget" className="text-accent-sand hover:underline">Budgéter</Link>
      </p>,
    );
  }

  const showHeaders = sections.length > 1;

  return shell(
    <div className="space-y-5 overflow-y-auto pr-2 custom-scrollbar">
      {sections.map((s) => (
        <div key={s.entityId}>
          {showHeaders && (
            <p className="text-[11px] font-semibold text-accent-sand uppercase tracking-wider mb-2.5 border-b border-[#1a1a1a] pb-1">
              {s.entityName}
            </p>
          )}
          <div className="space-y-3.5">
            {s.lines.map((l) => <BudgetLine key={l.key} line={l} />)}
          </div>
        </div>
      ))}
    </div>,
  );
}
