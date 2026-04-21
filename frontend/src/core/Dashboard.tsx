import { useEffect, useState } from "react";
import { api } from "../api";
import { DashboardSummary } from "../types";
import { TrendingUp, TrendingDown, Hash, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { useEntity } from "./EntityContext";
import ModuleDiscoveryHint from "./ModuleDiscoveryHint";

const eurFormatter = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

interface TimePoint { month: string; balance: number; }
interface TopCat { name: string; color: string; total: number; }
interface RecentTx {
  id: number; date: string; label: string; amount: number;
  from_entity_name?: string; to_entity_name?: string;
  category_name?: string; category_color?: string;
}

function SummaryCard({
  label, value, icon: Icon, valueColor,
}: {
  label: string; value: string; icon: React.ElementType; valueColor: string;
}) {
  return (
    <div className="bg-[#111] border border-[#222] rounded-2xl p-6 flex items-center gap-4">
      <div className="p-3 rounded-xl bg-[#1a1a1a] border border-[#222]">
        <Icon size={20} strokeWidth={1.5} className="text-[#B0B0B0]" />
      </div>
      <div>
        <p className="text-xs font-medium text-[#666] uppercase tracking-wider mb-1">{label}</p>
        <p className={`text-xl font-bold ${valueColor}`}>{value}</p>
      </div>
    </div>
  );
}

function BalanceChart({ series }: { series: TimePoint[] }) {
  if (series.length < 2) {
    return (
      <div className="bg-[#111] border border-[#222] rounded-2xl p-6">
        <p className="text-xs font-medium text-[#666] uppercase tracking-wider mb-3">Évolution du solde</p>
        <p className="text-sm text-[#666]">Pas assez de données pour afficher un graphique.</p>
      </div>
    );
  }
  const w = 640, h = 180, padL = 50, padR = 12, padT = 12, padB = 24;
  const xs = (i: number) => padL + (i * (w - padL - padR)) / (series.length - 1);
  const values = series.map((s) => s.balance);
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const range = maxV - minV || 1;
  const ys = (v: number) => padT + (1 - (v - minV) / range) * (h - padT - padB);
  const pts = series.map((s, i) => `${xs(i)},${ys(s.balance)}`).join(" ");
  const area = `M${xs(0)},${h - padB} L${pts.split(" ").join(" L")} L${xs(series.length - 1)},${h - padB} Z`;
  const labelFor = (m: string) => {
    const [y, mo] = m.split("-");
    const names = ["jan", "fév", "mar", "avr", "mai", "jun", "jul", "aoû", "sep", "oct", "nov", "déc"];
    return `${names[parseInt(mo, 10) - 1]} ${y.slice(2)}`;
  };
  const stepX = Math.ceil(series.length / 6);
  return (
    <div className="bg-[#111] border border-[#222] rounded-2xl p-6">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-medium text-[#666] uppercase tracking-wider">Évolution du solde</p>
        <p className="text-xs text-[#666]">{series.length} mois</p>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-auto">
        <defs>
          <linearGradient id="balanceGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#F2C48D" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#F2C48D" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.5, 1].map((t) => {
          const y = padT + t * (h - padT - padB);
          const v = maxV - t * range;
          return (
            <g key={t}>
              <line x1={padL} y1={y} x2={w - padR} y2={y} stroke="#1a1a1a" strokeWidth="1" />
              <text x={padL - 6} y={y + 3} fill="#555" fontSize="10" textAnchor="end">
                {Math.round(v).toLocaleString("fr-FR")}
              </text>
            </g>
          );
        })}
        <path d={area} fill="url(#balanceGrad)" />
        <polyline points={pts} fill="none" stroke="#F2C48D" strokeWidth="2" />
        {series.map((s, i) =>
          i % stepX === 0 || i === series.length - 1 ? (
            <text key={i} x={xs(i)} y={h - 6} fill="#666" fontSize="10" textAnchor="middle">
              {labelFor(s.month)}
            </text>
          ) : null
        )}
      </svg>
    </div>
  );
}

function TopCategories({ cats }: { cats: TopCat[] }) {
  if (cats.length === 0) return null;
  const max = Math.max(...cats.map((c) => c.total));
  return (
    <div className="bg-[#111] border border-[#222] rounded-2xl p-6">
      <p className="text-xs font-medium text-[#666] uppercase tracking-wider mb-4">Top dépenses par catégorie</p>
      <div className="space-y-3">
        {cats.map((c) => (
          <div key={c.name}>
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-[#B0B0B0]">{c.name}</span>
              <span className="text-white font-medium">{eurFormatter.format(c.total)}</span>
            </div>
            <div className="h-1.5 bg-[#1a1a1a] rounded-full overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{ width: `${(c.total / max) * 100}%`, backgroundColor: c.color }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function RecentTransactions({ txs }: { txs: RecentTx[] }) {
  return (
    <div className="bg-[#111] border border-[#222] rounded-2xl p-6">
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs font-medium text-[#666] uppercase tracking-wider">Dernières transactions</p>
        <Link to="/transactions" className="text-xs text-[#F2C48D] hover:underline inline-flex items-center gap-0.5">
          Voir tout <ArrowRight size={11} />
        </Link>
      </div>
      {txs.length === 0 ? (
        <p className="text-sm text-[#666]">Aucune transaction.</p>
      ) : (
        <div className="space-y-2">
          {txs.map((t) => (
            <div key={t.id} className="flex items-center justify-between gap-3 py-1.5">
              <div className="min-w-0 flex-1">
                <p className="text-sm text-white font-medium truncate">{t.label}</p>
                <p className="text-xs text-[#666]">
                  {t.date} · {t.from_entity_name || "—"} → {t.to_entity_name || "—"}
                </p>
              </div>
              <p className={`text-sm font-semibold whitespace-nowrap ${t.amount >= 0 ? "text-[#00C853]" : "text-[#FF5252]"}`}>
                {eurFormatter.format(t.amount)}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [series, setSeries] = useState<TimePoint[]>([]);
  const [cats, setCats] = useState<TopCat[]>([]);
  const [recent, setRecent] = useState<RecentTx[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const { selectedEntityId } = useEntity();

  useEffect(() => {
    setLoading(true);
    const eid = selectedEntityId ?? undefined;
    Promise.all([
      api.getSummary(eid),
      api.getTimeseries(eid),
      api.getTopCategories(eid),
      api.getRecentTransactions(eid),
    ])
      .then(([s, ts, tc, rt]) => {
        setSummary(s);
        setSeries(ts);
        setCats(tc);
        setRecent(rt);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [selectedEntityId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#F2C48D]" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-2xl p-4">{error}</div>
      </div>
    );
  }

  if (!summary) return null;
  const balancePositive = summary.balance >= 0;

  return (
    <div className="p-8 space-y-6">
      <ModuleDiscoveryHint />
      <div>
        <p className="text-sm font-medium text-[#666] uppercase tracking-wider mb-2">Solde actuel</p>
        <div className="relative inline-block">
          <div className="absolute -inset-4 bg-[rgba(26,115,232,0.08)] rounded-3xl blur-xl pointer-events-none" />
          <h1
            className={`relative text-5xl font-bold tracking-tight ${balancePositive ? "text-white" : "text-[#FF5252]"}`}
            style={{ letterSpacing: "-0.02em" }}
          >
            {eurFormatter.format(summary.balance)}
          </h1>
        </div>
        {summary.reference_date && summary.reference_amount !== undefined && (
          <p className="mt-3 text-sm text-[#666]">
            Référence au{" "}
            <span className="text-[#B0B0B0] font-medium">{summary.reference_date}</span>{" "}:{" "}
            <span className="text-[#B0B0B0] font-medium">{eurFormatter.format(summary.reference_amount)}</span>
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <SummaryCard label="Recettes" value={eurFormatter.format(summary.total_income)} icon={TrendingUp} valueColor="text-[#00C853]" />
        <SummaryCard label="Dépenses" value={eurFormatter.format(summary.total_expenses)} icon={TrendingDown} valueColor="text-[#FF5252]" />
        <SummaryCard label="Transactions" value={String(summary.transaction_count)} icon={Hash} valueColor="text-white" />
      </div>

      <BalanceChart series={series} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <TopCategories cats={cats} />
        <RecentTransactions txs={recent} />
      </div>
    </div>
  );
}
