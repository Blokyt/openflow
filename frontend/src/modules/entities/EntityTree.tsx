import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api";
import { Entity, EntityBalance, ConsolidatedBalance } from "../../types";
import { GitBranch, Plus, Building2, Users, Trash2, ChevronRight, ChevronDown, X, ArrowRight, Pencil } from "lucide-react";
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
  const { entities: entityTree, setSelectedEntityId } = useEntity();
  const navigate = useNavigate();

  // Ref edition form state
  const [editingRef, setEditingRef] = useState(false);
  const [refDate, setRefDate] = useState("");
  const [refAmount, setRefAmount] = useState("");
  const [refSaving, setRefSaving] = useState(false);
  const [refError, setRefError] = useState<string | null>(null);

  // Bank total calculator state
  const [bankTotal, setBankTotal] = useState("");

  function findName(tree: typeof entityTree, id: number): string | null {
    for (const e of tree) {
      if (e.id === id) return e.name;
      if (e.children) {
        const n = findName(e.children, id);
        if (n) return n;
      }
    }
    return null;
  }

  async function loadBalances() {
    return Promise.all([
      api.getEntityBalance(entityId).catch(() => null),
      api.getConsolidatedBalance(entityId).catch(() => null),
    ]).then(([b, c]) => {
      setBalance(b);
      setConsolidated(c);
    });
  }

  useEffect(() => {
    setLoading(true);
    loadBalances().finally(() => setLoading(false));
  }, [entityId]);

  function openEditForm() {
    setRefDate(balance?.reference_date ?? new Date().toISOString().slice(0, 10));
    setRefAmount(balance?.reference_amount != null ? String(balance.reference_amount) : "");
    setRefError(null);
    setEditingRef(true);
  }

  async function handleSaveRef(e: React.FormEvent) {
    e.preventDefault();
    setRefSaving(true);
    setRefError(null);
    try {
      await api.updateBalanceRef(entityId, {
        reference_date: refDate,
        reference_amount: parseFloat(refAmount),
      });
      await loadBalances();
      setEditingRef(false);
    } catch (err: any) {
      setRefError(err.message || "Erreur lors de la sauvegarde");
    } finally {
      setRefSaving(false);
    }
  }

  const hasChildren = consolidated && consolidated.children && consolidated.children.length > 0;
  const sumChildren = hasChildren
    ? consolidated!.children.reduce((acc, c) => acc + c.balance, 0)
    : 0;
  const bankTotalNum = bankTotal !== "" ? parseFloat(bankTotal) : null;
  const calculatedOwn = bankTotalNum !== null ? bankTotalNum - sumChildren : null;

  return (
    <div className="bg-[#0d0d0d] border border-[#222] rounded-2xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white">{entityName}</h3>
        <div className="flex items-center gap-2">
          <button
            onClick={() => { setSelectedEntityId(entityId); navigate("/transactions"); }}
            className="text-xs text-[#F2C48D] hover:underline inline-flex items-center gap-1"
            title="Voir les transactions de cette entité"
          >
            Transactions <ArrowRight size={11} />
          </button>
          <button onClick={onClose} className="text-[#666] hover:text-white">
            <X size={16} />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-4">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[#F2C48D]" />
        </div>
      ) : (
        <div className="space-y-3">
          {balance && (
            <div className="bg-[#111] border border-[#222] rounded-xl p-4">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs text-[#666] uppercase tracking-wider">Solde propre</p>
                {!editingRef && (
                  <button
                    onClick={openEditForm}
                    className="text-[#666] hover:text-[#F2C48D] transition-colors"
                    title="Modifier le solde de référence"
                  >
                    <Pencil size={13} />
                  </button>
                )}
              </div>
              <p className={`text-2xl font-bold ${balance.balance >= 0 ? "text-white" : "text-[#FF5252]"}`}>
                {eurFormatter.format(balance.balance)}
              </p>
              {balance.reference_date && (
                <p className="text-xs text-[#555] mt-1">
                  Réf. {balance.reference_date} : {eurFormatter.format(balance.reference_amount)}
                </p>
              )}

              {editingRef && (
                <form onSubmit={handleSaveRef} className="mt-3 space-y-2">
                  <div className="flex gap-2">
                    <input
                      type="date"
                      value={refDate}
                      onChange={(e) => setRefDate(e.target.value)}
                      className="flex-1 bg-[#1a1a1a] border border-[#333] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#F2C48D]/50"
                      required
                    />
                    <input
                      type="number"
                      step="0.01"
                      value={refAmount}
                      onChange={(e) => setRefAmount(e.target.value)}
                      placeholder="Montant"
                      className="flex-1 bg-[#1a1a1a] border border-[#333] rounded-lg px-3 py-2 text-sm text-white placeholder-[#555] focus:outline-none focus:border-[#F2C48D]/50"
                      required
                    />
                  </div>
                  {refError && (
                    <p className="text-xs text-[#FF5252]">{refError}</p>
                  )}
                  <div className="flex gap-2">
                    <button
                      type="submit"
                      disabled={refSaving}
                      className="flex-1 px-3 py-1.5 rounded-lg bg-[#F2C48D] text-black text-sm font-medium hover:bg-[#e5b57e] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {refSaving ? "..." : "Enregistrer"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditingRef(false)}
                      className="flex-1 px-3 py-1.5 rounded-lg border border-[#333] text-sm text-[#666] hover:text-white hover:border-[#444] transition-colors"
                    >
                      Annuler
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}

          {hasChildren && (
            <div className="bg-[#111] border border-[#222] rounded-xl p-4">
              <p className="text-xs text-[#666] uppercase tracking-wider mb-2">Solde consolidé</p>
              <p className={`text-2xl font-bold ${consolidated!.consolidated_balance >= 0 ? "text-[#F2C48D]" : "text-[#FF5252]"}`}>
                {eurFormatter.format(consolidated!.consolidated_balance)}
              </p>
              <div className="mt-3 space-y-1">
                {consolidated!.children.map((child) => (
                  <div key={child.entity_id} className="flex justify-between text-xs">
                    <span className="text-[#B0B0B0]">{findName(entityTree, child.entity_id) ?? `Entité #${child.entity_id}`}</span>
                    <span className={child.balance >= 0 ? "text-[#B0B0B0]" : "text-[#FF5252]"}>
                      {eurFormatter.format(child.balance)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {hasChildren && (
            <div className="bg-[#111] border border-[#222] rounded-xl p-4">
              <p className="text-xs text-[#666] uppercase tracking-wider mb-2">Calculer le solde propre</p>
              <p className="text-xs text-[#666] mb-3 leading-relaxed">
                Si tu connais le total du compte bancaire, le solde propre se déduit automatiquement.
              </p>
              <input
                type="number"
                step="0.01"
                value={bankTotal}
                onChange={(e) => setBankTotal(e.target.value)}
                placeholder="Total compte bancaire"
                className="w-full bg-[#1a1a1a] border border-[#333] rounded-lg px-3 py-2 text-sm text-white placeholder-[#555] focus:outline-none focus:border-[#F2C48D]/50"
              />
              {calculatedOwn !== null && (
                <div className="mt-3 space-y-2">
                  <p className="text-xs text-[#666]">
                    Solde propre calculé ={" "}
                    <span className="text-[#B0B0B0]">{eurFormatter.format(bankTotalNum!)}</span>
                    {" − "}
                    <span className="text-[#B0B0B0]">{eurFormatter.format(sumChildren)}</span>
                    {" = "}
                    <span className={`font-bold ${calculatedOwn >= 0 ? "text-white" : "text-[#FF5252]"}`}>
                      {eurFormatter.format(calculatedOwn)}
                    </span>
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      setRefAmount(String(calculatedOwn));
                      setRefDate(balance?.reference_date ?? new Date().toISOString().slice(0, 10));
                      setRefError(null);
                      setEditingRef(true);
                    }}
                    className="w-full px-3 py-1.5 rounded-lg border border-[#F2C48D]/40 text-sm text-[#F2C48D] hover:bg-[#F2C48D]/5 hover:border-[#F2C48D]/70 transition-colors"
                  >
                    Utiliser cette valeur
                  </button>
                </div>
              )}
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
        <p className="text-sm text-[#B0B0B0] leading-relaxed">
          Les entités représentent <span className="text-white font-medium">qui gère le budget</span> :
          ta structure (BDA) et ses <em>sous-clubs, pôles, sections</em> — ainsi que les{" "}
          <em>tiers externes</em> (banque, fournisseurs).
        </p>
        <p className="text-xs text-[#666] mt-1 leading-relaxed">
          Pour classer <span className="text-[#B0B0B0]">la nature</span> des dépenses (matériel,
          transport…), utilise plutôt{" "}
          <a href="/categories" className="text-[#F2C48D] hover:underline">Catégories</a>.
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
