import { useEffect, useState, useCallback, useRef } from "react";
import { api } from "../../api";
import { Transaction, Category } from "../../types";
import { useEntity } from "../../core/EntityContext";
import { useFiscalYear } from "../../core/FiscalYearContext";
import { useAuth } from "../../core/AuthContext";
import TransactionForm from "./TransactionForm";
import AttachmentsSection from "./AttachmentsSection";
import { formatEuros, formatDate, eurosToCents, txTone } from "../../utils/format";
import { transactionsToCsv, downloadCsv } from "../../utils/csv";
import { Plus, Pencil, Trash2, X, Search, ArrowRight, Eye, Hourglass, Check, RotateCcw, Download, AlertTriangle } from "lucide-react";

const PAGE_SIZE = 100;

export default function TransactionList() {
  const { isAdmin } = useAuth();
  const { selectedEntityId, selectedEntity } = useEntity();
  const { selectedYear } = useFiscalYear();
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  // Track the last context that initialized the date filters (for the reset link)
  const contextDatesRef = useRef<{ from: string; to: string } | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [reimbFilter, setReimbFilter] = useState<string>("");
  const [amountMin, setAmountMin] = useState<string>("");
  const [amountMax, setAmountMax] = useState<string>("");
  const [categories, setCategories] = useState<Category[]>([]);
  const [sortBy, setSortBy] = useState<"date" | "amount" | "label">("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [undoTx, setUndoTx] = useState<Transaction | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingTx, setEditingTx] = useState<Transaction | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [detailTx, setDetailTx] = useState<Transaction | null>(null);
  const [activeModuleIds, setActiveModuleIds] = useState<Set<string>>(new Set());
  // Action en attente de confirmation « exercice clôturé » (relancée avec force=true).
  const [pendingForceAction, setPendingForceAction] = useState<(() => Promise<void>) | null>(null);

  useEffect(() => {
    api.getModules()
      .then((mods: any[]) => setActiveModuleIds(new Set(mods.map((m) => m.id))))
      .catch(() => {});
    api.getCategories().then(setCategories).catch(() => {});
  }, []);

  // Recherche temporisée : évite une requête à chaque frappe.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  // Synchronise les filtres de date avec l'exercice sélectionné.
  const today = new Date().toISOString().slice(0, 10);
  useEffect(() => {
    if (selectedYear) {
      const from = selectedYear.start_date;
      const to = selectedYear.end_date ?? today;
      contextDatesRef.current = { from, to };
      setDateFrom(from);
      setDateTo(to);
    } else {
      // Filtre exercice effacé : on retire les dates qu'il avait posées, mais on
      // préserve des dates saisies manuellement par l'utilisateur.
      const ctx = contextDatesRef.current;
      contextDatesRef.current = null;
      if (ctx) {
        setDateFrom((cur) => (cur === ctx.from ? "" : cur));
        setDateTo((cur) => (cur === ctx.to ? "" : cur));
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedYear?.id]);

  // Vérifie si les dates ont été modifiées manuellement par rapport au contexte
  const datesModified =
    contextDatesRef.current !== null &&
    (dateFrom !== contextDatesRef.current.from || dateTo !== contextDatesRef.current.to);

  function resetDatesToContext() {
    if (contextDatesRef.current) {
      setDateFrom(contextDatesRef.current.from);
      setDateTo(contextDatesRef.current.to);
    }
  }

  const hasAttachments = activeModuleIds.has("attachments");
  const hasActiveFilters = Boolean(
    search || dateFrom || dateTo || categoryFilter || reimbFilter || amountMin || amountMax
  );

  // Paramètres de requête communs (filtres + tri), hors pagination.
  const buildParams = useCallback((): Record<string, string> => {
    const params: Record<string, string> = {};
    if (debouncedSearch) params.search = debouncedSearch;
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    if (categoryFilter) params.category_id = categoryFilter;
    if (reimbFilter) params.reimb_status = reimbFilter;
    // Saisie en euros, l'API attend des centimes entiers.
    if (amountMin) params.amount_min = String(eurosToCents(amountMin));
    if (amountMax) params.amount_max = String(eurosToCents(amountMax));
    if (selectedEntityId) {
      params.entity_id = String(selectedEntityId);
      params.include_children = "true";
    }
    params.sort_by = sortBy;
    params.sort_dir = sortDir;
    return params;
  }, [debouncedSearch, dateFrom, dateTo, categoryFilter, reimbFilter, amountMin, amountMax, selectedEntityId, sortBy, sortDir]);

  const loadFirstPage = useCallback(() => {
    setLoading(true);
    api
      .getTransactions({ ...buildParams(), limit: String(PAGE_SIZE), offset: "0" })
      .then((r) => { setTransactions(r.items); setTotal(r.total); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [buildParams]);

  useEffect(() => {
    loadFirstPage();
  }, [loadFirstPage]);

  function loadMore() {
    setLoadingMore(true);
    api
      .getTransactions({ ...buildParams(), limit: String(PAGE_SIZE), offset: String(transactions.length) })
      .then((r) => { setTransactions((prev) => [...prev, ...r.items]); setTotal(r.total); })
      .catch((e) => setError(e.message))
      .finally(() => setLoadingMore(false));
  }

  async function handleExportCsv() {
    setExporting(true);
    try {
      // Sans limit : on exporte toutes les transactions filtrées, pas seulement la page chargée.
      const r = await api.getTransactions(buildParams());
      downloadCsv(transactionsToCsv(r.items), `transactions-${today}.csv`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setExporting(false);
    }
  }

  // Exécute `action(false)` ; si le backend refuse à cause d'un exercice clôturé
  // (409 « clôturé »), garde l'action de côté pour la relancer avec force=true
  // après confirmation, au lieu d'afficher une erreur bloquante.
  async function withForceConfirm(action: (force: boolean) => Promise<void>) {
    try {
      await action(false);
    } catch (e: any) {
      if (typeof e?.message === "string" && e.message.includes("clôturé")) {
        setPendingForceAction(() => () => action(true));
      } else {
        setError(e.message);
      }
    }
  }

  async function handleCreate(tx: Omit<Transaction, "id">) {
    await withForceConfirm(async (force) => {
      await api.createTransaction(tx, force);
      setShowForm(false);
      loadFirstPage();
    });
  }

  async function handleUpdate(tx: Omit<Transaction, "id">) {
    if (!editingTx) return;
    await withForceConfirm(async (force) => {
      await api.updateTransaction(editingTx.id, tx, force);
      setEditingTx(null);
      loadFirstPage();
    });
  }

  async function handleDelete(id: number) {
    const target = transactions.find((t) => t.id === id) ?? null;
    setDeletingId(id);
    await withForceConfirm(async (force) => {
      await api.deleteTransaction(id, force);
      setConfirmDelete(null);
      if (target) {
        setUndoTx(target);
        setTimeout(() => {
          setUndoTx((current) => (current && current.id === target.id ? null : current));
        }, 6000);
      }
      loadFirstPage();
    });
    setDeletingId(null);
  }

  async function handleUndoDelete() {
    if (!undoTx) return;
    const restore = {
      date: undoTx.date,
      label: undoTx.label,
      amount: undoTx.amount,
      description: undoTx.description,
      category_id: undoTx.category_id,
      from_entity_id: undoTx.from_entity_id,
      to_entity_id: undoTx.to_entity_id,
    };
    await withForceConfirm(async (force) => {
      await api.createTransaction(restore, force);
      setUndoTx(null);
      loadFirstPage();
    });
  }

  function toggleSort(col: "date" | "amount" | "label") {
    if (sortBy === col) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else {
      setSortBy(col);
      setSortDir(col === "date" ? "desc" : "asc");
    }
  }

  function clearFilters() {
    setSearch(""); setDateFrom(""); setDateTo("");
    setCategoryFilter(""); setReimbFilter(""); setAmountMin(""); setAmountMax("");
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
            Transactions
          </h1>
          {selectedEntity && (
            <p className="text-sm text-[#8a8a8a] mt-1">
              Filtrées pour <span className="text-[#F2C48D] font-medium">{selectedEntity.name}</span> et sous-entités
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleExportCsv}
            disabled={exporting || total === 0}
            className="flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-white border border-[#333] rounded-full hover:border-[#444] hover:bg-[#1a1a1a] disabled:opacity-40 transition-colors"
            title="Exporter les transactions filtrées au format CSV"
          >
            <Download size={15} /> {exporting ? "Export..." : "Exporter CSV"}
          </button>
          {isAdmin && (
            <button
              onClick={() => { setShowForm(true); setEditingTx(null); }}
              className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] transition-colors"
            >
              <Plus size={15} /> Nouvelle transaction
            </button>
          )}
        </div>
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
      <div className="mb-5 flex flex-wrap gap-2">
        <div className="flex items-center gap-2 flex-1 min-w-48 bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 focus-within:border-[#F2C48D] transition-colors">
          <Search size={15} className="text-[#8a8a8a]" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher..."
            className="flex-1 text-sm bg-transparent focus:outline-none text-white placeholder-[#666]"
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-[#8a8a8a]">Du</label>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors [color-scheme:dark]"
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-[#8a8a8a]">Au</label>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors [color-scheme:dark]"
          />
        </div>
        {datesModified && (
          <button
            onClick={resetDatesToContext}
            className="flex items-center gap-1.5 px-3 py-2.5 text-xs text-[#F2C48D] border border-[#F2C48D]/30 rounded-xl hover:bg-[#F2C48D]/10 transition-colors"
            title="Réinitialiser aux dates de l'exercice"
          >
            <RotateCcw size={12} />
            Réinitialiser
          </button>
        )}
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors"
          title="Filtrer par catégorie"
        >
          <option value="">Toutes catégories</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        <select
          value={reimbFilter}
          onChange={(e) => setReimbFilter(e.target.value)}
          className="bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors"
        >
          <option value="">Toutes les avances</option>
          <option value="pending">En attente</option>
          <option value="reimbursed">Remboursées</option>
          <option value="none">Sans avance</option>
        </select>
        <input
          type="number"
          step="0.01"
          min="0"
          value={amountMin}
          onChange={(e) => setAmountMin(e.target.value)}
          placeholder="Min €"
          className="min-w-0 w-24 bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#666]"
        />
        <input
          type="number"
          step="0.01"
          min="0"
          value={amountMax}
          onChange={(e) => setAmountMax(e.target.value)}
          placeholder="Max €"
          className="min-w-0 w-24 bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#666]"
        />
        {hasActiveFilters && (
          <button
            onClick={clearFilters}
            className="text-sm text-[#8a8a8a] hover:text-white flex items-center gap-1 transition-colors"
          >
            <X size={14} /> Effacer
          </button>
        )}
      </div>

      {/* Count */}
      {!loading && total > 0 && (
        <p className="mb-3 text-xs text-[#8a8a8a]">
          {transactions.length === total
            ? `${total} transaction${total > 1 ? "s" : ""}`
            : `${transactions.length} sur ${total} transactions`}
        </p>
      )}

      {/* Table */}
      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-x-auto">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#F2C48D]" />
          </div>
        ) : transactions.length === 0 ? (
          <div className="text-center py-12 text-[#8a8a8a] text-sm">
            Aucune transaction trouvée.
            {hasActiveFilters && (
              <button onClick={clearFilters} className="ml-2 text-[#F2C48D] hover:underline">
                Effacer les filtres
              </button>
            )}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                <th className="px-3 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider w-12">#</th>
                <th
                  onClick={() => toggleSort("date")}
                  className="px-4 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider cursor-pointer select-none hover:text-white"
                >
                  Date {sortBy === "date" ? (sortDir === "asc" ? "↑" : "↓") : ""}
                </th>
                <th
                  onClick={() => toggleSort("label")}
                  className="px-4 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider cursor-pointer select-none hover:text-white"
                >
                  Libellé {sortBy === "label" ? (sortDir === "asc" ? "↑" : "↓") : ""}
                </th>
                <th className="px-4 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Flux</th>
                <th className="px-4 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Catégorie</th>
                <th className="px-4 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Avance de frais</th>
                <th
                  onClick={() => toggleSort("amount")}
                  className="px-4 py-3.5 text-right text-xs font-medium text-[#8a8a8a] uppercase tracking-wider cursor-pointer select-none hover:text-white"
                >
                  Montant {sortBy === "amount" ? (sortDir === "asc" ? "↑" : "↓") : ""}
                </th>
                <th className="px-4 py-3.5 text-right text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((tx: any, idx) => (
                <tr
                  key={tx.id}
                  className={`hover:bg-[#1a1a1a] transition-colors ${idx > 0 ? "border-t border-[#1a1a1a]" : ""}`}
                >
                  <td className="px-3 py-3.5 text-[#555] text-xs font-mono">#{tx.id}</td>
                  <td className="px-4 py-3.5 text-[#B0B0B0] whitespace-nowrap">{formatDate(tx.date)}</td>
                  <td className="px-4 py-3.5 font-medium text-white max-w-xs">
                    <span title={tx.description || undefined}>{tx.label}</span>
                    {tx.description && (
                      <p className="text-xs text-[#888] font-normal mt-0.5 truncate" title={tx.description}>{tx.description}</p>
                    )}
                  </td>
                  <td className="px-4 py-3.5">
                    <div className="flex items-center gap-1.5 text-xs">
                      <span
                        className="px-2 py-0.5 rounded-full truncate max-w-[100px]"
                        style={{
                          backgroundColor: (tx.from_entity_color || "#6B7280") + "20",
                          color: tx.from_entity_color || "#999",
                        }}
                        title={tx.from_entity_name}
                      >
                        {tx.from_entity_name || "—"}
                      </span>
                      <ArrowRight size={12} className="text-[#555] shrink-0" />
                      <span
                        className="px-2 py-0.5 rounded-full truncate max-w-[100px]"
                        style={{
                          backgroundColor: (tx.to_entity_color || "#6B7280") + "20",
                          color: tx.to_entity_color || "#999",
                        }}
                        title={tx.to_entity_name}
                      >
                        {tx.to_entity_name || "—"}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3.5">
                    {tx.category_name ? (
                      <span
                        className="text-xs px-2 py-0.5 rounded-full"
                        style={{
                          backgroundColor: (tx.category_color || "#6B7280") + "20",
                          color: tx.category_color || "#999",
                        }}
                      >
                        {tx.category_name}
                      </span>
                    ) : (
                      <span className="text-[#444]">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3.5">
                    {tx.reimb_person_name ? (
                      <span
                        className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border ${
                          tx.reimb_status === "reimbursed"
                            ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                            : "bg-amber-500/10 text-amber-400 border-amber-500/30"
                        }`}
                        title={`Avance de ${tx.reimb_person_name}${tx.reimb_status === "reimbursed" ? " (remboursé)" : " (en attente)"}`}
                      >
                        {tx.reimb_status === "reimbursed" ? <Check size={12} /> : <Hourglass size={12} />}
                        {tx.reimb_person_name}
                      </span>
                    ) : (
                      <span className="text-xs text-[#444]">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3.5 text-right font-semibold whitespace-nowrap">
                    {(() => {
                      const { color, sign } = txTone(tx);
                      return <span style={{ color }}>{sign}{formatEuros(tx.amount)}</span>;
                    })()}
                  </td>
                  <td className="px-4 py-3.5 text-right">
                    {confirmDelete === tx.id ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="text-xs text-[#8a8a8a]">Supprimer ?</span>
                        <button
                          onClick={() => handleDelete(tx.id)}
                          disabled={deletingId === tx.id}
                          className="text-xs font-medium text-[#FF5252] hover:text-red-400"
                        >
                          Oui
                        </button>
                        <button
                          onClick={() => setConfirmDelete(null)}
                          className="text-xs font-medium text-[#8a8a8a] hover:text-white"
                        >
                          Non
                        </button>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1">
                        {hasAttachments && (
                          <button
                            onClick={() => setDetailTx(tx)}
                            className="p-1.5 text-[#8a8a8a] hover:text-[#F2C48D] rounded-lg hover:bg-[#222] transition-colors"
                            title="Voir les détails"
                          >
                            <Eye size={14} strokeWidth={1.5} />
                          </button>
                        )}
                        {isAdmin && (
                          <>
                            <button
                              onClick={() => { setEditingTx(tx); setShowForm(false); }}
                              className="p-1.5 text-[#8a8a8a] hover:text-white rounded-lg hover:bg-[#222] transition-colors"
                              title="Modifier"
                            >
                              <Pencil size={14} strokeWidth={1.5} />
                            </button>
                            <button
                              onClick={() => setConfirmDelete(tx.id)}
                              className="p-1.5 text-[#8a8a8a] hover:text-[#FF5252] rounded-lg hover:bg-[#222] transition-colors"
                              title="Supprimer"
                            >
                              <Trash2 size={14} strokeWidth={1.5} />
                            </button>
                          </>
                        )}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination "charger plus" */}
      {!loading && transactions.length < total && (
        <div className="mt-4 flex justify-center">
          <button
            onClick={loadMore}
            disabled={loadingMore}
            className="px-5 py-2.5 text-sm font-medium text-[#B0B0B0] border border-[#333] rounded-full hover:border-[#444] hover:bg-[#1a1a1a] disabled:opacity-50 transition-colors"
          >
            {loadingMore ? "Chargement..." : `Charger plus (${total - transactions.length} restantes)`}
          </button>
        </div>
      )}

      {undoTx && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-4 bg-[#111] border border-[#333] rounded-full px-5 py-3 shadow-xl">
          <span className="text-sm text-white">Transaction supprimée</span>
          <button
            onClick={handleUndoDelete}
            className="text-sm font-semibold text-[#F2C48D] hover:underline"
          >
            Annuler
          </button>
          <button
            onClick={() => setUndoTx(null)}
            className="text-[#8a8a8a] hover:text-white"
            aria-label="Fermer"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {pendingForceAction && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[#111] border border-[#333] rounded-2xl p-6 max-w-sm w-full mx-4 space-y-4">
            <div className="flex items-center gap-3">
              <AlertTriangle size={20} className="text-[#F2C48D] flex-shrink-0" />
              <h3 className="text-base font-semibold text-white">Exercice clôturé</h3>
            </div>
            <p className="text-sm text-[#999]">
              Cette écriture appartient à un exercice clôturé. La modifier peut
              affecter un bilan déjà rendu. Forcer la modification ?
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setPendingForceAction(null)}
                className="px-4 py-2 text-sm text-[#8a8a8a] border border-[#333] rounded-xl hover:text-white transition-colors"
              >
                Annuler
              </button>
              <button
                onClick={async () => {
                  const action = pendingForceAction;
                  setPendingForceAction(null);
                  if (!action) return;
                  try {
                    await action();
                  } catch (e: any) {
                    setError(e.message);
                  }
                }}
                className="px-4 py-2 text-sm font-medium text-black bg-[#F2C48D] rounded-xl hover:bg-[#e8b87a] transition-colors"
              >
                Forcer la modification
              </button>
            </div>
          </div>
        </div>
      )}

      {detailTx && (
        <div className="fixed inset-0 bg-black/60 flex justify-end z-50" onClick={() => setDetailTx(null)}>
          <div
            className="w-full max-w-md bg-[#0a0a0a] border-l border-[#222] h-full overflow-y-auto p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between mb-6">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-[#555] bg-[#1a1a1a] px-1.5 py-0.5 rounded">#{detailTx.id}</span>
                  <h2 className="text-xl font-bold text-white break-words">{detailTx.label}</h2>
                </div>
                <div className="text-sm text-[#8a8a8a] mt-1">{formatDate(detailTx.date)}</div>
                {(() => {
                  const { color, sign } = txTone(detailTx);
                  return (
                    <div className="mt-3 text-2xl font-bold" style={{ color }}>
                      {sign}{formatEuros(detailTx.amount)}
                    </div>
                  );
                })()}
                {(detailTx as any).reimb_person_name && (
                  <div className={`mt-2 inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-lg border ${
                    (detailTx as any).reimb_status === "reimbursed"
                      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                      : "bg-amber-500/10 text-amber-400 border-amber-500/30"
                  }`}>
                    ↩ Avance de {(detailTx as any).reimb_person_name}
                    {(detailTx as any).reimb_status === "reimbursed" ? " — remboursé" : " — en attente"}
                  </div>
                )}
              </div>
              <button
                onClick={() => setDetailTx(null)}
                className="text-[#8a8a8a] hover:text-white p-1 flex-shrink-0"
              >
                <X size={18} />
              </button>
            </div>

            {(detailTx as any).description && (
              <div className="mb-4 bg-[#111] border border-[#222] rounded-xl p-3 text-sm text-[#B0B0B0]">
                {(detailTx as any).description}
              </div>
            )}

            <div className="space-y-4">
              {hasAttachments && <AttachmentsSection txId={detailTx.id} />}
              {!hasAttachments && (
                <div className="text-sm text-[#8a8a8a]">
                  Active le module « Pièces jointes » dans Paramètres
                  pour enrichir le détail des transactions.
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
