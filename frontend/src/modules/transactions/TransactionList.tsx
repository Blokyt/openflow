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
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
          Transactions
        </h1>
        <button
          onClick={() => { setShowForm(true); setEditingTx(null); }}
          className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] transition-colors"
        >
          <Plus size={15} /> Ajouter
        </button>
      </div>

      {error && (
        <div className="mb-4 bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-2xl p-4 text-sm flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)} className="text-[#FF5252]/70 hover:text-[#FF5252]">
            <X size={16} />
          </button>
        </div>
      )}

      {/* Form panel */}
      {(showForm || editingTx) && (
        <div className="mb-6 bg-[#111] border border-[#222] rounded-2xl p-6">
          <h2 className="text-base font-semibold text-white mb-5">
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
      <div className="mb-5 flex flex-wrap gap-3">
        <div className="flex items-center gap-2 flex-1 min-w-48 bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 focus-within:border-[#F2C48D] transition-colors">
          <Search size={15} className="text-[#666]" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher..."
            className="flex-1 text-sm bg-transparent focus:outline-none text-white placeholder-[#666]"
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-[#666]">Du</label>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors [color-scheme:dark]"
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-[#666]">Au</label>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors [color-scheme:dark]"
          />
        </div>
        {(search || dateFrom || dateTo) && (
          <button
            onClick={() => { setSearch(""); setDateFrom(""); setDateTo(""); }}
            className="text-sm text-[#666] hover:text-white flex items-center gap-1 transition-colors"
          >
            <X size={14} /> Effacer
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#F2C48D]" />
          </div>
        ) : transactions.length === 0 ? (
          <div className="text-center py-12 text-[#666] text-sm">
            Aucune transaction trouvée.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Date</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Libellé</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Catégorie</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Montant</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((tx, idx) => (
                <tr
                  key={tx.id}
                  className={`hover:bg-[#1a1a1a] transition-colors ${idx > 0 ? "border-t border-[#1a1a1a]" : ""}`}
                >
                  <td className="px-5 py-3.5 text-[#B0B0B0] whitespace-nowrap">{tx.date}</td>
                  <td className="px-5 py-3.5 font-medium text-white">
                    {tx.label}
                    {tx.description && (
                      <p className="text-xs text-[#666] font-normal mt-0.5">{tx.description}</p>
                    )}
                  </td>
                  <td className="px-5 py-3.5 text-[#B0B0B0]">
                    {tx.category?.name ?? <span className="text-[#444]">—</span>}
                  </td>
                  <td
                    className={`px-5 py-3.5 text-right font-semibold whitespace-nowrap ${
                      tx.amount >= 0 ? "text-[#00C853]" : "text-[#FF5252]"
                    }`}
                  >
                    {eurFormatter.format(tx.amount)}
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    {confirmDelete === tx.id ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="text-xs text-[#666]">Supprimer ?</span>
                        <button
                          onClick={() => handleDelete(tx.id)}
                          disabled={deletingId === tx.id}
                          className="text-xs font-medium text-[#FF5252] hover:text-red-400"
                        >
                          Oui
                        </button>
                        <button
                          onClick={() => setConfirmDelete(null)}
                          className="text-xs font-medium text-[#666] hover:text-white"
                        >
                          Non
                        </button>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1">
                        <button
                          onClick={() => { setEditingTx(tx); setShowForm(false); }}
                          className="p-1.5 text-[#666] hover:text-white rounded-lg hover:bg-[#222] transition-colors"
                          title="Modifier"
                        >
                          <Pencil size={14} strokeWidth={1.5} />
                        </button>
                        <button
                          onClick={() => setConfirmDelete(tx.id)}
                          className="p-1.5 text-[#666] hover:text-[#FF5252] rounded-lg hover:bg-[#222] transition-colors"
                          title="Supprimer"
                        >
                          <Trash2 size={14} strokeWidth={1.5} />
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
