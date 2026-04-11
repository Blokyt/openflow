import { useEffect, useState } from "react";
import { TrendingUp, TrendingDown, Wallet } from "lucide-react";

const BASE_URL = "/api";
const eurFormatter = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

interface ProjectionMonth {
  month: string;
  projected_balance: number;
}

interface ProjectionData {
  current_balance: number;
  avg_monthly_income: number;
  avg_monthly_expenses: number;
  projection: ProjectionMonth[];
}

async function fetchProjection(months: number): Promise<ProjectionData> {
  const response = await fetch(`${BASE_URL}/forecasting/projection?months=${months}`, {
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || response.statusText);
  }
  return response.json();
}

function formatMonth(ym: string): string {
  const [year, month] = ym.split("-");
  const d = new Date(Number(year), Number(month) - 1, 1);
  return d.toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
}

export default function ForecastingView() {
  const [months, setMonths] = useState(6);
  const [data, setData] = useState<ProjectionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchProjection(months)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [months]);

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
            Prévisions de trésorerie
          </h1>
          <p className="text-sm text-[#666] mt-1">Projection du cash-flow futur</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-sm text-[#666] font-medium">Horizon :</label>
          <select
            value={months}
            onChange={(e) => setMonths(Number(e.target.value))}
            className="bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors"
          >
            {[3, 6, 9, 12].map((m) => (
              <option key={m} value={m}>{m} mois</option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="mb-4 bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-2xl p-4 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#F2C48D]" />
        </div>
      ) : data ? (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
            <div className="bg-[#111] border border-[#222] rounded-2xl p-6 flex items-center gap-4">
              <div className="bg-[#1a1a1a] border border-[#222] p-3 rounded-xl">
                <Wallet size={18} strokeWidth={1.5} className="text-[#B0B0B0]" />
              </div>
              <div>
                <p className="text-xs text-[#666] font-medium uppercase tracking-wider mb-1">Solde actuel</p>
                <p className={`text-lg font-bold ${data.current_balance >= 0 ? "text-white" : "text-[#FF5252]"}`}>
                  {eurFormatter.format(data.current_balance)}
                </p>
              </div>
            </div>
            <div className="bg-[#111] border border-[#222] rounded-2xl p-6 flex items-center gap-4">
              <div className="bg-[#00C853]/10 border border-[#00C853]/20 p-3 rounded-xl">
                <TrendingUp size={18} strokeWidth={1.5} className="text-[#00C853]" />
              </div>
              <div>
                <p className="text-xs text-[#666] font-medium uppercase tracking-wider mb-1">Recettes moy. / mois</p>
                <p className="text-lg font-bold text-[#00C853]">
                  {eurFormatter.format(data.avg_monthly_income)}
                </p>
              </div>
            </div>
            <div className="bg-[#111] border border-[#222] rounded-2xl p-6 flex items-center gap-4">
              <div className="bg-[#FF5252]/10 border border-[#FF5252]/20 p-3 rounded-xl">
                <TrendingDown size={18} strokeWidth={1.5} className="text-[#FF5252]" />
              </div>
              <div>
                <p className="text-xs text-[#666] font-medium uppercase tracking-wider mb-1">Dépenses moy. / mois</p>
                <p className="text-lg font-bold text-[#FF5252]">
                  {eurFormatter.format(data.avg_monthly_expenses)}
                </p>
              </div>
            </div>
          </div>

          {/* Projection table */}
          <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
            <div className="px-6 py-4 border-b border-[#1a1a1a]">
              <h2 className="text-sm font-semibold text-white">
                Projection sur {months} mois
              </h2>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#1a1a1a]">
                  <th className="px-6 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Mois</th>
                  <th className="px-6 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Solde projeté</th>
                  <th className="px-6 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Variation</th>
                </tr>
              </thead>
              <tbody>
                {data.projection.map((row, idx) => {
                  const prev = idx === 0 ? data.current_balance : data.projection[idx - 1].projected_balance;
                  const delta = row.projected_balance - prev;
                  return (
                    <tr key={row.month} className={`hover:bg-[#1a1a1a] transition-colors ${idx > 0 ? "border-t border-[#1a1a1a]" : ""}`}>
                      <td className="px-6 py-3.5 font-medium text-white capitalize">
                        {formatMonth(row.month)}
                      </td>
                      <td className={`px-6 py-3.5 text-right font-semibold ${row.projected_balance >= 0 ? "text-white" : "text-[#FF5252]"}`}>
                        {eurFormatter.format(row.projected_balance)}
                      </td>
                      <td className={`px-6 py-3.5 text-right text-xs font-medium ${delta >= 0 ? "text-[#00C853]" : "text-[#FF5252]"}`}>
                        {delta >= 0 ? "+" : ""}{eurFormatter.format(delta)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <p className="mt-4 text-xs text-[#444]">
            Calcul basé sur les moyennes des 6 derniers mois de transactions.
          </p>
        </>
      ) : null}
    </div>
  );
}
