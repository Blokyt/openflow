import { useEffect, useState, useCallback } from "react";
import { api } from "../../api";
import { Category } from "../../types";
import { useEntity } from "../../core/EntityContext";
import { useFiscalYear } from "../../core/FiscalYearContext";
import { useAuth } from "../../core/AuthContext";
import { formatEuros } from "../../utils/format";
import { Plus, Pencil, Trash2, ChevronRight, ChevronDown, X, Check, AlertTriangle } from "lucide-react";

interface CategoryUsage {
  transactions: number;
  allocations: number;
  children: number;
  accruals: number;
}

/** Construit le message d'avertissement affiché avant confirmation de suppression,
 * en fonction de ce qui utilise la catégorie. Retourne null si rien n'est utilisé
 * (dans ce cas la confirmation générique reste inchangée). */
function describeUsageImpact(usage: CategoryUsage): string | null {
  const uses: string[] = [];
  if (usage.transactions > 0) {
    uses.push(`${usage.transactions} transaction${usage.transactions > 1 ? "s" : ""}`);
  }
  if (usage.allocations > 0) {
    uses.push(`${usage.allocations} allocation${usage.allocations > 1 ? "s" : ""} budgétaire${usage.allocations > 1 ? "s" : ""}`);
  }
  if (usage.children > 0) {
    uses.push(`${usage.children} sous-catégorie${usage.children > 1 ? "s" : ""}`);
  }
  if (usage.accruals > 0) {
    uses.push(`${usage.accruals} écriture${usage.accruals > 1 ? "s" : ""} de clôture`);
  }
  if (uses.length === 0) return null;

  const consequences: string[] = [];
  if (usage.transactions > 0) consequences.push("les transactions seront décatégorisées");
  if (usage.accruals > 0) consequences.push("les écritures de clôture seront décatégorisées");
  if (usage.allocations > 0) consequences.push("les allocations budgétaires seront supprimées");
  if (usage.children > 0) consequences.push("les sous-catégories seront rattachées à la racine");
  const consequenceSentence = consequences.join(", ");

  return `Utilisée par ${uses.join(", ")}. ${consequenceSentence.charAt(0).toUpperCase()}${consequenceSentence.slice(1)}.`;
}

/* ---------- Category tree node ---------- */
function CategoryNode({
  cat,
  allCategories,
  onEdit,
  onDelete,
  canEdit,
}: {
  cat: Category;
  allCategories: Category[];
  onEdit: (cat: Category) => void;
  onDelete: (id: number) => void;
  canEdit: boolean;
}) {
  const [open, setOpen] = useState(true);
  const hasChildren = cat.children && cat.children.length > 0;

  return (
    <div className="select-none">
      <div className="flex items-center gap-2 py-2 px-2 rounded-lg hover:bg-[#1a1a1a] group transition-colors">
        <button
          onClick={() => setOpen((v) => !v)}
          className="w-5 h-5 flex items-center justify-center text-[#444]"
        >
          {hasChildren ? (
            open ? <ChevronDown size={13} strokeWidth={1.5} /> : <ChevronRight size={13} strokeWidth={1.5} />
          ) : (
            <span className="w-3" />
          )}
        </button>
        <span
          className="w-2.5 h-2.5 rounded-full flex-shrink-0"
          style={{ backgroundColor: cat.color || "#6B7280" }}
          title={cat.color || "#6B7280"}
        />
        <span className="flex-1 text-sm text-white font-medium">{cat.name}</span>
        {hasChildren ? (
          (cat.descendant_tx_count ?? 0) > 0 && (
            <span className="text-xs text-[#555] mr-1">
              {cat.descendant_tx_count} · {formatEuros(cat.descendant_tx_total ?? 0)}
            </span>
          )
        ) : (
          (cat.tx_count ?? 0) > 0 && (
            <span className="text-xs text-[#8a8a8a] mr-1">
              {cat.tx_count} · {formatEuros(cat.tx_total ?? 0)}
            </span>
          )
        )}
        {canEdit && (
          <span className="hidden group-hover:inline-flex items-center gap-1">
            <button
              onClick={() => onEdit(cat)}
              className="p-1.5 text-[#8a8a8a] hover:text-white rounded-lg hover:bg-[#222] transition-colors"
              title="Modifier"
            >
              <Pencil size={12} strokeWidth={1.5} />
            </button>
            <button
              onClick={() => onDelete(cat.id)}
              className="p-1.5 text-[#8a8a8a] hover:text-[#FF5252] rounded-lg hover:bg-[#222] transition-colors"
              title="Supprimer"
            >
              <Trash2 size={12} strokeWidth={1.5} />
            </button>
          </span>
        )}
      </div>
      {hasChildren && open && (
        <div className="ml-6 border-l border-[#222] pl-2">
          {cat.children!.map((child) => (
            <CategoryNode
              key={child.id}
              cat={child}
              allCategories={allCategories}
              onEdit={onEdit}
              onDelete={onDelete}
              canEdit={canEdit}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------- Inline edit row ---------- */
function EditRow({
  cat,
  allCategories,
  onSave,
  onCancel,
}: {
  cat: Category;
  allCategories: Category[];
  onSave: (id: number, name: string, parentId?: number) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(cat.name);
  const [parentId, setParentId] = useState<string>(
    cat.parent_id !== undefined ? String(cat.parent_id) : ""
  );

  const eligible = allCategories.filter((c) => c.id !== cat.id);

  return (
    <div className="flex items-center gap-2 py-2 px-2 bg-[#1a1a1a] rounded-lg border border-[#F2C48D]/30">
      <span className="w-5" />
      <input
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="flex-1 bg-[#0a0a0a] border border-[#222] rounded-lg px-2 py-1.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors"
      />
      <select
        value={parentId}
        onChange={(e) => setParentId(e.target.value)}
        className="bg-[#0a0a0a] border border-[#222] rounded-lg px-2 py-1.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors"
      >
        <option value="">— Racine —</option>
        {eligible.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
      <button
        onClick={() => onSave(cat.id, name, parentId ? parseInt(parentId) : undefined)}
        className="p-1.5 text-[#00C853] hover:text-green-400 rounded-lg hover:bg-[#222] transition-colors"
      >
        <Check size={14} strokeWidth={1.5} />
      </button>
      <button onClick={onCancel} className="p-1.5 text-[#8a8a8a] hover:text-white rounded-lg hover:bg-[#222] transition-colors">
        <X size={14} strokeWidth={1.5} />
      </button>
    </div>
  );
}

/* ---------- Main component ---------- */
export default function CategoryManager() {
  const { isAdmin } = useAuth();
  const [tree, setTree] = useState<Category[]>([]);
  const [flatList, setFlatList] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingCat, setEditingCat] = useState<Category | null>(null);
  const [savingCat, setSavingCat] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [deleteUsage, setDeleteUsage] = useState<CategoryUsage | null>(null);

  const [newName, setNewName] = useState("");
  const [newParentId, setNewParentId] = useState("");
  const [creating, setCreating] = useState(false);

  const { selectedEntityId, selectedEntity } = useEntity();
  const { selectedYear } = useFiscalYear();

  const fetchCategories = useCallback(() => {
    setLoading(true);
    // Les compteurs/montants par catégorie suivent le focus global : même
    // périmètre (entité + sous-entités) et même fenêtre d'exercice que le reste.
    const today = new Date().toISOString().slice(0, 10);
    const dateFrom = selectedYear?.start_date;
    const dateTo = selectedYear ? (selectedYear.end_date ?? today) : undefined;
    Promise.all([
      api.getCategoryTree(selectedEntityId ?? undefined, dateFrom, dateTo),
      api.getCategories(),
    ])
      .then(([t, flat]) => {
        setTree(t);
        setFlatList(flat);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [selectedEntityId, selectedYear?.id]);

  useEffect(() => {
    fetchCategories();
  }, [fetchCategories]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await api.createCategory({
        name: newName.trim(),
        parent_id: newParentId ? parseInt(newParentId) : undefined,
      });
      setNewName("");
      setNewParentId("");
      fetchCategories();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  }

  async function handleUpdate(id: number, name: string, parentId?: number) {
    if (savingCat) return; // anti double-soumission
    setSavingCat(true);
    try {
      await api.updateCategory(id, { name, parent_id: parentId });
      setEditingCat(null);
      fetchCategories();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSavingCat(false);
    }
  }

  function requestDelete(id: number) {
    setConfirmDelete(id);
    setDeleteUsage(null);
    // Best-effort : si la route n'est pas encore déployée ou que l'appel échoue
    // (réseau), on retombe silencieusement sur la confirmation générique.
    api.getCategoryUsage(id).then(setDeleteUsage).catch(() => {});
  }

  function cancelDelete() {
    setConfirmDelete(null);
    setDeleteUsage(null);
  }

  async function handleDelete(id: number) {
    try {
      await api.deleteCategory(id);
      setConfirmDelete(null);
      setDeleteUsage(null);
      fetchCategories();
    } catch (e: any) {
      setError(e.message);
    }
  }

  function renderTree(nodes: Category[]) {
    return nodes.map((cat) => {
      if (editingCat?.id === cat.id) {
        return (
          <EditRow
            key={cat.id}
            cat={cat}
            allCategories={flatList}
            onSave={handleUpdate}
            onCancel={() => setEditingCat(null)}
          />
        );
      }
      if (confirmDelete === cat.id) {
        const impact = deleteUsage ? describeUsageImpact(deleteUsage) : null;
        return (
          <div key={cat.id} className="flex flex-col gap-1.5 py-2 px-2 bg-[#1a0a0a] border border-[#FF5252]/20 rounded-lg">
            <div className="flex items-center gap-2">
              <span className="w-5" />
              <span className="flex-1 text-sm text-[#FF5252] font-medium">{cat.name}</span>
              <span className="text-xs text-[#FF5252]/70">Supprimer ?</span>
              <button
                onClick={() => handleDelete(cat.id)}
                className="text-xs font-medium text-[#FF5252] hover:text-red-400"
              >
                Oui
              </button>
              <button
                onClick={cancelDelete}
                className="text-xs font-medium text-[#8a8a8a] hover:text-white"
              >
                Non
              </button>
            </div>
            {impact && (
              <div className="flex items-start gap-1.5 pl-7">
                <AlertTriangle size={12} strokeWidth={1.5} className="text-amber-400 mt-0.5 flex-shrink-0" />
                <p className="text-xs text-amber-300 leading-relaxed">{impact}</p>
              </div>
            )}
          </div>
        );
      }
      return (
        <CategoryNode
          key={cat.id}
          cat={cat}
          allCategories={flatList}
          onEdit={setEditingCat}
          onDelete={requestDelete}
          canEdit={isAdmin}
        />
      );
    });
  }

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-3xl font-bold text-white mb-2" style={{ letterSpacing: "-0.02em" }}>
        Catégories
      </h1>
      <p className="text-sm text-[#B0B0B0] mb-2 leading-relaxed">
        Les catégories décrivent <span className="text-white font-medium">la nature</span> d'une
        transaction (ex&nbsp;: <em>matériel, transport, cotisations, sponsoring</em>).
      </p>
      <p className="text-xs text-[#8a8a8a] mb-2 leading-relaxed">
        Pour modéliser <span className="text-[#B0B0B0]">qui gère le budget</span> (sous-clubs,
        pôles, sections), utilise plutôt{" "}
        <a href="/entities" className="text-[#F2C48D] hover:underline">Entités</a>.
      </p>
      {(selectedEntity || selectedYear) && (
        <p className="text-xs text-[#8a8a8a] mb-8">
          Statistiques comptées pour{" "}
          {selectedEntity ? (
            <span className="text-[#F2C48D] font-medium">{selectedEntity.name} et sous-entités</span>
          ) : (
            "toutes les entités"
          )}
          {selectedYear && (
            <> sur l'exercice <span className="text-[#F2C48D] font-medium">{selectedYear.name}</span></>
          )}.
        </p>
      )}
      {!selectedEntity && !selectedYear && <div className="mb-6" />}

      {error && (
        <div className="mb-4 bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-2xl p-4 text-sm flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)} className="text-[#FF5252]/70 hover:text-[#FF5252]">
            <X size={16} />
          </button>
        </div>
      )}

      {/* Create form */}
      {isAdmin && (
        <form onSubmit={handleCreate} className="mb-6 bg-[#111] border border-[#222] rounded-2xl p-5">
          <h2 className="text-sm font-semibold text-white mb-4">Nouvelle catégorie</h2>
          <div className="flex gap-3 flex-wrap">
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Nom de la catégorie"
              required
              className="flex-1 min-w-40 bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#444]"
            />
            <select
              value={newParentId}
              onChange={(e) => setNewParentId(e.target.value)}
              className="bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors"
            >
              <option value="">— Racine —</option>
              {flatList.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.name}
                </option>
              ))}
            </select>
            <button
              type="submit"
              disabled={creating}
              className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-50 transition-colors"
            >
              <Plus size={14} /> Créer
            </button>
          </div>
        </form>
      )}

      {/* Tree */}
      <div className="bg-[#111] border border-[#222] rounded-2xl p-4">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#F2C48D]" />
          </div>
        ) : tree.length === 0 ? (
          <p className="text-center text-[#8a8a8a] text-sm py-8">
            Aucune catégorie. Créez-en une ci-dessus.
          </p>
        ) : (
          <div className="space-y-0.5">{renderTree(tree)}</div>
        )}
      </div>
    </div>
  );
}
