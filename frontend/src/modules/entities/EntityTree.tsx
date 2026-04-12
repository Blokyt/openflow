import { useEffect, useState } from "react";
import { api } from "../../api";
import { Entity, EntityBalance, ConsolidatedBalance } from "../../types";
import { GitBranch, Plus, Building2, Users, Trash2, ChevronRight, ChevronDown, X } from "lucide-react";
import { useEntity } from "../../core/EntityContext";

const eurFormatter = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

// ─── Entity tree node ────────────────────────────────────────────────────────

function EntityNode({
  entity,
  depth,
  onDelete,
  onSelect,
}: {
  entity: Entity;
  depth: number;
  onDelete: (id: number) => void;
  onSelect: (id: number) => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const hasChildren = entity.children && entity.children.length > 0;

  return (
    <div>
      <div
        className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-[#1a1a1a] group cursor-pointer"
        style={{ paddingLeft: `${12 + depth * 20}px` }}
        onClick={() => onSelect(entity.id)}
      >
        {/* Expand/collapse toggle */}
        <button
          className="text-[#444] hover:text-white w-4 flex-shrink-0"
          onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
        >
          {hasChildren ? (
            expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
          ) : (
            <span className="w-4 inline-block" />
          )}
        </button>

        {/* Color dot */}
        <span
          className="w-2.5 h-2.5 rounded-full flex-shrink-0"
          style={{ backgroundColor: entity.color || "#F2C48D" }}
        />

        <span className="text-sm text-white flex-1 truncate">{entity.name}</span>

        {entity.is_default === 1 && (
          <span className="text-[10px] text-[#F2C48D] border border-[#F2C48D]/30 rounded px-1.5 py-0.5">
            défaut
          </span>
        )}

        <button
          className="opacity-0 group-hover:opacity-100 text-[#666] hover:text-[#FF5252] transition-opacity ml-1"
          onClick={(e) => { e.stopPropagation(); onDelete(entity.id); }}
          title="Supprimer"
        >
          <Trash2 size={13} />
        </button>
      </div>

      {hasChildren && expanded && (
        <div>
          {entity.children!.map((child) => (
            <EntityNode
              key={child.id}
              entity={child}
              depth={depth + 1}
              onDelete={onDelete}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Create entity modal ──────────────────────────────────────────────────────

function CreateEntityModal({
  type,
  internalEntities,
  onClose,
  onCreate,
}: {
  type: "internal" | "external";
  internalEntities: Entity[];
  onClose: () => void;
  onCreate: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [parentId, setParentId] = useState<number | "">("");
  const [color, setColor] = useState("#F2C48D");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await api.createEntity({
        name: name.trim(),
        description: description.trim(),
        type,
        parent_id: parentId !== "" ? parentId : null,
        color,
        is_default: 0,
        is_divers: 0,
        position: 0,
      });
      onCreate();
      onClose();
    } catch (err: any) {
      setError(err.message || "Erreur lors de la création");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-[#111] border border-[#222] rounded-2xl p-6 w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-base font-semibold text-white">
            Nouvelle entité {type === "internal" ? "interne" : "externe"}
          </h2>
          <button onClick={onClose} className="text-[#666] hover:text-white">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-[#666] mb-1.5 uppercase tracking-wider">Nom *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-[#1a1a1a] border border-[#333] rounded-lg px-3 py-2 text-sm text-white placeholder-[#555] focus:outline-none focus:border-[#F2C48D]/50"
              placeholder="Nom de l'entité"
              required
              autoFocus
            />
          </div>

          <div>
            <label className="block text-xs text-[#666] mb-1.5 uppercase tracking-wider">Description</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full bg-[#1a1a1a] border border-[#333] rounded-lg px-3 py-2 text-sm text-white placeholder-[#555] focus:outline-none focus:border-[#F2C48D]/50"
              placeholder="Description optionnelle"
            />
          </div>

          {type === "internal" && internalEntities.length > 0 && (
            <div>
              <label className="block text-xs text-[#666] mb-1.5 uppercase tracking-wider">Entité parente</label>
              <select
                value={parentId}
                onChange={(e) => setParentId(e.target.value !== "" ? parseInt(e.target.value, 10) : "")}
                className="w-full bg-[#1a1a1a] border border-[#333] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#F2C48D]/50"
              >
                <option value="">Aucune (racine)</option>
                {internalEntities.map((e) => (
                  <option key={e.id} value={e.id}>{e.name}</option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label className="block text-xs text-[#666] mb-1.5 uppercase tracking-wider">Couleur</label>
            <div className="flex items-center gap-3">
              <input
                type="color"
                value={color}
                onChange={(e) => setColor(e.target.value)}
                className="w-10 h-10 rounded-lg border border-[#333] bg-[#1a1a1a] cursor-pointer"
              />
              <span className="text-sm text-[#666]">{color}</span>
            </div>
          </div>

          {error && (
            <div className="text-sm text-[#FF5252] bg-[#1a0a0a] border border-[#FF5252]/20 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 rounded-lg border border-[#333] text-sm text-[#666] hover:text-white hover:border-[#444] transition-colors"
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={saving || !name.trim()}
              className="flex-1 px-4 py-2 rounded-lg bg-[#F2C48D] text-black text-sm font-medium hover:bg-[#e5b57e] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {saving ? "Création..." : "Créer"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Balance detail panel ─────────────────────────────────────────────────────

function EntityBalancePanel({
  entityId,
  entityName,
  onClose,
}: {
  entityId: number;
  entityName: string;
  onClose: () => void;
}) {
  const [balance, setBalance] = useState<EntityBalance | null>(null);
  const [consolidated, setConsolidated] = useState<ConsolidatedBalance | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.getEntityBalance(entityId).catch(() => null),
      api.getConsolidatedBalance(entityId).catch(() => null),
    ]).then(([b, c]) => {
      setBalance(b);
      setConsolidated(c);
    }).finally(() => setLoading(false));
  }, [entityId]);

  return (
    <div className="bg-[#0d0d0d] border border-[#222] rounded-2xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white">{entityName}</h3>
        <button onClick={onClose} className="text-[#666] hover:text-white">
          <X size={16} />
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-4">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[#F2C48D]" />
        </div>
      ) : (
        <div className="space-y-3">
          {balance && (
            <div className="bg-[#111] border border-[#222] rounded-xl p-4">
              <p className="text-xs text-[#666] uppercase tracking-wider mb-2">Solde propre</p>
              <p className={`text-2xl font-bold ${balance.balance >= 0 ? "text-white" : "text-[#FF5252]"}`}>
                {eurFormatter.format(balance.balance)}
              </p>
              {balance.reference_date && (
                <p className="text-xs text-[#555] mt-1">
                  Réf. {balance.reference_date} : {eurFormatter.format(balance.reference_amount)}
                </p>
              )}
            </div>
          )}

          {consolidated && consolidated.children && consolidated.children.length > 0 && (
            <div className="bg-[#111] border border-[#222] rounded-xl p-4">
              <p className="text-xs text-[#666] uppercase tracking-wider mb-2">Solde consolidé</p>
              <p className={`text-2xl font-bold ${consolidated.consolidated_balance >= 0 ? "text-[#F2C48D]" : "text-[#FF5252]"}`}>
                {eurFormatter.format(consolidated.consolidated_balance)}
              </p>
              <div className="mt-3 space-y-1">
                {consolidated.children.map((child) => (
                  <div key={child.entity_id} className="flex justify-between text-xs">
                    <span className="text-[#666]">Entité #{child.entity_id}</span>
                    <span className={child.balance >= 0 ? "text-[#B0B0B0]" : "text-[#FF5252]"}>
                      {eurFormatter.format(child.balance)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!balance && !consolidated && (
            <p className="text-sm text-[#666] text-center py-2">Aucune donnée disponible</p>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function EntityTree() {
  const { entities, reload } = useEntity();
  const [externalEntities, setExternalEntities] = useState<Entity[]>([]);
  const [showCreateModal, setShowCreateModal] = useState<"internal" | "external" | null>(null);
  const [selectedEntityId, setSelectedEntityId] = useState<number | null>(null);
  const [selectedEntityName, setSelectedEntityName] = useState<string>("");

  useEffect(() => {
    api.getEntities("external")
      .then(setExternalEntities)
      .catch(() => setExternalEntities([]));
  }, []);

  async function handleDelete(id: number) {
    if (!confirm("Supprimer cette entité ?")) return;
    try {
      await api.deleteEntity(id);
      await reload();
      api.getEntities("external").then(setExternalEntities).catch(() => {});
      if (selectedEntityId === id) setSelectedEntityId(null);
    } catch (err: any) {
      alert(err.message || "Erreur lors de la suppression");
    }
  }

  function handleSelectEntity(id: number) {
    const found = findEntityFlat([...entities, ...externalEntities], id);
    if (found) {
      setSelectedEntityId(id);
      setSelectedEntityName(found.name);
    }
  }

  async function handleCreated() {
    await reload();
    await api.getEntities("external").then(setExternalEntities).catch(() => {});
  }

  // Flatten internal entities for parent selector
  const flatInternal = flattenTree(entities);

  return (
    <div className="p-8 max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <GitBranch size={22} className="text-[#F2C48D]" strokeWidth={1.5} />
          <h1 className="text-2xl font-bold text-white">Entités</h1>
        </div>
        <p className="text-sm text-[#666]">
          Gérez la structure des entités internes et externes de votre organisation.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column: trees */}
        <div className="lg:col-span-2 space-y-6">
          {/* Internal entities */}
          <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-[#222]">
              <div className="flex items-center gap-2">
                <Building2 size={16} className="text-[#F2C48D]" strokeWidth={1.5} />
                <span className="text-sm font-semibold text-white">Entités internes</span>
                <span className="text-xs text-[#555] bg-[#1a1a1a] border border-[#2a2a2a] rounded-full px-2 py-0.5">
                  {flatInternal.length}
                </span>
              </div>
              <button
                onClick={() => setShowCreateModal("internal")}
                className="flex items-center gap-1.5 text-xs text-[#F2C48D] border border-[#F2C48D]/30 hover:border-[#F2C48D]/60 hover:bg-[#F2C48D]/5 rounded-lg px-3 py-1.5 transition-colors"
              >
                <Plus size={13} />
                Nouvelle
              </button>
            </div>

            <div className="p-2">
              {entities.length === 0 ? (
                <div className="text-center py-8 text-sm text-[#555]">
                  Aucune entité interne. Créez-en une pour commencer.
                </div>
              ) : (
                entities.map((e) => (
                  <EntityNode
                    key={e.id}
                    entity={e}
                    depth={0}
                    onDelete={handleDelete}
                    onSelect={handleSelectEntity}
                  />
                ))
              )}
            </div>
          </div>

          {/* External entities */}
          <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-[#222]">
              <div className="flex items-center gap-2">
                <Users size={16} className="text-[#B0B0B0]" strokeWidth={1.5} />
                <span className="text-sm font-semibold text-white">Entités externes</span>
                <span className="text-xs text-[#555] bg-[#1a1a1a] border border-[#2a2a2a] rounded-full px-2 py-0.5">
                  {externalEntities.length}
                </span>
              </div>
              <button
                onClick={() => setShowCreateModal("external")}
                className="flex items-center gap-1.5 text-xs text-[#B0B0B0] border border-[#333] hover:border-[#555] hover:bg-[#1a1a1a] rounded-lg px-3 py-1.5 transition-colors"
              >
                <Plus size={13} />
                Nouvelle
              </button>
            </div>

            <div className="p-2">
              {externalEntities.length === 0 ? (
                <div className="text-center py-8 text-sm text-[#555]">
                  Aucune entité externe.
                </div>
              ) : (
                externalEntities.map((e) => (
                  <div
                    key={e.id}
                    className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-[#1a1a1a] group cursor-pointer"
                    onClick={() => handleSelectEntity(e.id)}
                  >
                    <span
                      className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                      style={{ backgroundColor: e.color || "#888" }}
                    />
                    <span className="text-sm text-white flex-1 truncate">{e.name}</span>
                    {e.description && (
                      <span className="text-xs text-[#555] truncate max-w-[120px]">{e.description}</span>
                    )}
                    <button
                      className="opacity-0 group-hover:opacity-100 text-[#666] hover:text-[#FF5252] transition-opacity"
                      onClick={(e2) => { e2.stopPropagation(); handleDelete(e.id); }}
                      title="Supprimer"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Right column: balance panel */}
        <div>
          {selectedEntityId !== null ? (
            <EntityBalancePanel
              entityId={selectedEntityId}
              entityName={selectedEntityName}
              onClose={() => setSelectedEntityId(null)}
            />
          ) : (
            <div className="bg-[#0d0d0d] border border-[#1a1a1a] rounded-2xl p-5 text-center">
              <GitBranch size={24} className="text-[#333] mx-auto mb-3" strokeWidth={1.5} />
              <p className="text-sm text-[#555]">
                Cliquez sur une entité pour voir son solde
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Create modal */}
      {showCreateModal && (
        <CreateEntityModal
          type={showCreateModal}
          internalEntities={flatInternal}
          onClose={() => setShowCreateModal(null)}
          onCreate={handleCreated}
        />
      )}
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function flattenTree(nodes: Entity[]): Entity[] {
  const result: Entity[] = [];
  function walk(list: Entity[]) {
    for (const e of list) {
      result.push(e);
      if (e.children) walk(e.children);
    }
  }
  walk(nodes);
  return result;
}

function findEntityFlat(nodes: Entity[], id: number): Entity | null {
  for (const e of nodes) {
    if (e.id === id) return e;
    if (e.children) {
      const found = findEntityFlat(e.children, id);
      if (found) return found;
    }
  }
  return null;
}
