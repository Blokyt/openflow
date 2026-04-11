import { useEffect, useState, useCallback } from "react";
import { api } from "../../api";
import { Transaction } from "../../types";
import TransactionForm from "./TransactionForm";
import { Plus, Pencil, Trash2, X, Search } from "lucide-react";

const eurFormatter = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

export default function TransactionList() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editingTx, setEditingTx] = useState<Transaction | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  const fetchTransactions = useCallback(() => {
    setLoading(true);
    const params: Record<string, string> = {};
    if (search) params.search = search;
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    api
      .getTransactions(Object.keys(params).length ? params : undefined)
      .then(setTransactions)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [search, dateFrom, dateTo]);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  async function handleCreate(tx: Omit<Transaction, "id">) {
    await api.createTransaction(tx);
    setShowForm(false);
    fetchTransactions();
  }

  async function handleUpdate(tx: Omit<Transaction, "id">) {
    if (!editingTx) return;
    await api.updateTransaction(editingTx.id, tx);
    setEditingTx(null);
    fetchTransactions();
  }

  async function handleDelete(id: number) {
    setDeletingId(id);
    try {
      await api.deleteTransaction(id);
      setConfirmDelete(null);
      fetchTransactions();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Transactions</h1>
        <button
          onClick={() => { setShowForm(true); setEditingTx(null); }}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700"
        >
          <Plus size={16} /> Ajouter
        </button>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)}><X size={16} /></button>
        </div>
      )}

      {/* Form panel */}
      {(showForm || editingTx) && (
        <div className="mb-6 bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h2 className="text-base font-semibold text-gray-800 mb-4">
            {editingTx ? "Modifier la transaction" : "Nouvelle transaction"}
          </h2>
          <TransactionForm
            initial={editingTx ?? undefined}
            onSave={editingTx ? handleUpdate : handleCreate}
            onCancel={() => { setShowForm(false); setEditingTx(null); }}
          />
        </div>
      )}

      {/* Filters */}
      <div className="mb-4 flex flex-wrap gap-3">
        <div className="flex items-center gap-2 flex-1 min-w-48 bg-white border border-gray-300 rounded-lg px-3 py-2">
          <Search size={16} className="text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher..."
            className="flex-1 text-sm focus:outline-none"
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">Du</label>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">Au</label>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        {(search || dateFrom || dateTo) && (
          <button
            onClick={() => { setSearch(""); setDateFrom(""); setDateTo(""); }}
            className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1"
          >
            <X size={14} /> Effacer
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
          </div>
        ) : transactions.length === 0 ? (
          <div className="text-center py-12 text-gray-500 text-sm">
            Aucune transaction trouvée.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Date</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Libellé</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Catégorie</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600">Montant</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {transactions.map((tx) => (
                <tr key={tx.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{tx.date}</td>
                  <td className="px-4 py-3 font-medium text-gray-900">
                    {tx.label}
                    {tx.description && (
                      <p className="text-xs text-gray-400 font-normal">{tx.description}</p>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {tx.category?.name ?? <span className="text-gray-300">—</span>}
                  </td>
                  <td
                    className={`px-4 py-3 text-right font-semibold whitespace-nowrap ${
                      tx.amount >= 0 ? "text-green-600" : "text-red-600"
                    }`}
                  >
                    {eurFormatter.format(tx.amount)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {confirmDelete === tx.id ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="text-xs text-gray-500">Supprimer ?</span>
                        <button
                          onClick={() => handleDelete(tx.id)}
                          disabled={deletingId === tx.id}
                          className="text-xs font-medium text-red-600 hover:text-red-800"
                        >
                          Oui
                        </button>
                        <button
                          onClick={() => setConfirmDelete(null)}
                          className="text-xs font-medium text-gray-500 hover:text-gray-700"
                        >
                          Non
                        </button>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-2">
                        <button
                          onClick={() => { setEditingTx(tx); setShowForm(false); }}
                          className="p-1 text-gray-400 hover:text-indigo-600 rounded"
                          title="Modifier"
                        >
                          <Pencil size={15} />
                        </button>
                        <button
                          onClick={() => setConfirmDelete(tx.id)}
                          className="p-1 text-gray-400 hover:text-red-600 rounded"
                          title="Supprimer"
                        >
                          <Trash2 size={15} />
                        </button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
