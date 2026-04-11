import { useEffect, useState, useCallback } from "react";
import { api } from "../../api";
import { Category } from "../../types";
import { Plus, Pencil, Trash2, ChevronRight, ChevronDown, X, Check } from "lucide-react";

/* ---------- Category tree node ---------- */
function CategoryNode({
  cat,
  allCategories,
  onEdit,
  onDelete,
}: {
  cat: Category;
  allCategories: Category[];
  onEdit: (cat: Category) => void;
  onDelete: (id: number) => void;
}) {
  const [open, setOpen] = useState(true);
  const hasChildren = cat.children && cat.children.length > 0;

  return (
    <div className="select-none">
      <div className="flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-gray-50 group">
        <button
          onClick={() => setOpen((v) => !v)}
          className="w-5 h-5 flex items-center justify-center text-gray-400"
        >
          {hasChildren ? (
            open ? <ChevronDown size={14} /> : <ChevronRight size={14} />
          ) : (
            <span className="w-3" />
          )}
        </button>
        <span className="flex-1 text-sm text-gray-800 font-medium">{cat.name}</span>
        <span className="hidden group-hover:inline-flex items-center gap-1">
          <button
            onClick={() => onEdit(cat)}
            className="p-1 text-gray-400 hover:text-indigo-600 rounded"
            title="Modifier"
          >
            <Pencil size={13} />
          </button>
          <button
            onClick={() => onDelete(cat.id)}
            className="p-1 text-gray-400 hover:text-red-600 rounded"
            title="Supprimer"
          >
            <Trash2 size={13} />
          </button>
        </span>
      </div>
      {hasChildren && open && (
        <div className="ml-6 border-l border-gray-200 pl-2">
          {cat.children!.map((child) => (
            <CategoryNode
              key={child.id}
              cat={child}
              allCategories={allCategories}
              onEdit={onEdit}
              onDelete={onDelete}
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

  // filter out self + descendants to avoid cycles
  const eligible = allCategories.filter((c) => c.id !== cat.id);

  return (
    <div className="flex items-center gap-2 py-1.5 px-2 bg-indigo-50 rounded-lg">
      <span className="w-5" />
      <input
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="flex-1 border border-indigo-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
      />
      <select
        value={parentId}
        onChange={(e) => setParentId(e.target.value)}
        className="border border-indigo-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
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
        className="p-1 text-green-600 hover:text-green-800"
      >
        <Check size={15} />
      </button>
      <button onClick={onCancel} className="p-1 text-gray-400 hover:text-gray-600">
        <X size={15} />
      </button>
    </div>
  );
}

/* ---------- Main component ---------- */
export default function CategoryManager() {
  const [tree, setTree] = useState<Category[]>([]);
  const [flatList, setFlatList] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingCat, setEditingCat] = useState<Category | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  // New category form
  const [newName, setNewName] = useState("");
  const [newParentId, setNewParentId] = useState("");
  const [creating, setCreating] = useState(false);

  const fetchCategories = useCallback(() => {
    setLoading(true);
    Promise.all([api.getCategoryTree(), api.getCategories()])
      .then(([t, flat]) => {
        setTree(t);
        setFlatList(flat);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

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
    try {
      await api.updateCategory(id, { name, parent_id: parentId });
      setEditingCat(null);
      fetchCategories();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleDelete(id: number) {
    try {
      await api.deleteCategory(id);
      setConfirmDelete(null);
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
        return (
          <div key={cat.id} className="flex items-center gap-2 py-1.5 px-2 bg-red-50 rounded-lg">
            <span className="w-5" />
            <span className="flex-1 text-sm text-red-700 font-medium">{cat.name}</span>
            <span className="text-xs text-red-600">Supprimer ?</span>
            <button
              onClick={() => handleDelete(cat.id)}
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
          </div>
        );
      }
      return (
        <CategoryNode
          key={cat.id}
          cat={cat}
          allCategories={flatList}
          onEdit={setEditingCat}
          onDelete={setConfirmDelete}
        />
      );
    });
  }

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Catégories</h1>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)}><X size={16} /></button>
        </div>
      )}

      {/* Create form */}
      <form onSubmit={handleCreate} className="mb-6 bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">Nouvelle catégorie</h2>
        <div className="flex gap-3 flex-wrap">
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Nom de la catégorie"
            required
            className="flex-1 min-w-40 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <select
            value={newParentId}
            onChange={(e) => setNewParentId(e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
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
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50"
          >
            <Plus size={15} /> Créer
          </button>
        </div>
      </form>

      {/* Tree */}
      <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
          </div>
        ) : tree.length === 0 ? (
          <p className="text-center text-gray-500 text-sm py-8">
            Aucune catégorie. Créez-en une ci-dessus.
          </p>
        ) : (
          <div className="space-y-0.5">{renderTree(tree)}</div>
        )}
      </div>
    </div>
  );
}
