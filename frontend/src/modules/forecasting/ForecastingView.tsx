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
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Prévisions de trésorerie</h1>
          <p className="text-sm text-gray-500 mt-1">Projection du cash-flow futur</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600 font-medium">Horizon :</label>
          <select
            value={months}
            onChange={(e) => setMonths(Number(e.target.value))}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {[3, 6, 9, 12].map((m) => (
              <option key={m} value={m}>{m} mois</option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
        </div>
      ) : data ? (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
            <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm flex items-center gap-4">
              <div className="bg-indigo-50 p-3 rounded-lg">
                <Wallet size={20} className="text-indigo-600" />
              </div>
              <div>
                <p className="text-xs text-gray-500 font-medium">Solde actuel</p>
                <p className={`text-lg font-bold ${data.current_balance >= 0 ? "text-gray-900" : "text-red-600"}`}>
                  {eurFormatter.format(data.current_balance)}
                </p>
              </div>
            </div>
            <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm flex items-center gap-4">
              <div className="bg-green-50 p-3 rounded-lg">
                <TrendingUp size={20} className="text-green-600" />
              </div>
              <div>
                <p className="text-xs text-gray-500 font-medium">Recettes moy. / mois</p>
                <p className="text-lg font-bold text-green-600">
                  {eurFormatter.format(data.avg_monthly_income)}
                </p>
              </div>
            </div>
            <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm flex items-center gap-4">
              <div className="bg-red-50 p-3 rounded-lg">
                <TrendingDown size={20} className="text-red-600" />
              </div>
              <div>
                <p className="text-xs text-gray-500 font-medium">Dépenses moy. / mois</p>
                <p className="text-lg font-bold text-red-600">
                  {eurFormatter.format(data.avg_monthly_expenses)}
                </p>
              </div>
            </div>
          </div>

          {/* Projection table */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-100">
              <h2 className="text-sm font-semibold text-gray-700">
                Projection sur {months} mois
              </h2>
            </div>
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-5 py-3 text-left font-medium text-gray-600">Mois</th>
                  <th className="px-5 py-3 text-right font-medium text-gray-600">Solde projeté</th>
                  <th className="px-5 py-3 text-right font-medium text-gray-600">Variation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.projection.map((row, idx) => {
                  const prev = idx === 0 ? data.current_balance : data.projection[idx - 1].projected_balance;
                  const delta = row.projected_balance - prev;
                  return (
                    <tr key={row.month} className="hover:bg-gray-50 transition-colors">
                      <td className="px-5 py-3 font-medium text-gray-800 capitalize">
                        {formatMonth(row.month)}
                      </td>
                      <td className={`px-5 py-3 text-right font-semibold ${row.projected_balance >= 0 ? "text-gray-900" : "text-red-600"}`}>
                        {eurFormatter.format(row.projected_balance)}
                      </td>
                      <td className={`px-5 py-3 text-right text-xs font-medium ${delta >= 0 ? "text-green-600" : "text-red-500"}`}>
                        {delta >= 0 ? "+" : ""}{eurFormatter.format(delta)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <p className="mt-3 text-xs text-gray-400">
            Calcul basé sur les moyennes des 6 derniers mois de transactions.
          </p>
        </>
      ) : null}
    </div>
  );
}
