import { useEffect, useState } from "react";

const eurFormatter = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

interface Invoice {
  id: number;
  number: string;
  type: string;
  date: string;
  due_date: string | null;
  status: string;
  total: number;
}

export default function UnpaidInvoices() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetch("/api/invoices/?status=sent").then((r) => {
        if (!r.ok) throw new Error(r.statusText);
        return r.json();
      }),
      fetch("/api/invoices/?status=overdue").then((r) => {
        if (!r.ok) throw new Error(r.statusText);
        return r.json();
      }),
    ])
      .then(([sent, overdue]) => {
        const combined: Invoice[] = [...sent, ...overdue];
        combined.sort((a, b) => (a.due_date ?? a.date) < (b.due_date ?? b.date) ? -1 : 1);
        setInvoices(combined);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-sm text-red-600 bg-red-50 rounded-lg">{error}</div>
    );
  }

  if (invoices.length === 0) {
    return (
      <div className="p-4 text-sm text-gray-500 text-center">
        Aucune facture impayee.
      </div>
    );
  }

  return (
    <div className="p-4 space-y-2">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">Factures impayees</h3>
      {invoices.map((inv) => (
        <div key={inv.id} className="flex items-center justify-between text-sm">
          <div className="flex flex-col">
            <span className="font-medium text-gray-800">{inv.number}</span>
            {inv.due_date && (
              <span className="text-xs text-gray-400">Echeance : {inv.due_date}</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`px-2 py-0.5 text-xs rounded-full font-medium ${
                inv.status === "overdue"
                  ? "bg-red-100 text-red-700"
                  : "bg-yellow-100 text-yellow-700"
              }`}
            >
              {inv.status === "overdue" ? "En retard" : "Envoyee"}
            </span>
            <span className="font-semibold text-gray-900">
              {eurFormatter.format(inv.total)}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
