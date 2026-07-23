import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../../api";
import { Entity, EntityBalance, ConsolidatedBalance } from "../../types";
import { GitBranch, Plus, Building2, Users, Trash2, ChevronRight, ChevronDown, X, ArrowRight, Pencil } from "lucide-react";
import { useEntity } from "../../core/EntityContext";
import { useAuth } from "../../core/AuthContext";
import { formatEuros, formatDate, eurosToCents, centsToEuros } from "../../utils/format";
import ConfirmDialog from "../../core/ConfirmDialog";
import PageLoader from "../../core/PageLoader";

/** Retourne la date locale du jour au format YYYY-MM-DD. */
function localToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// ─── Entity tree node ────────────────────────────────────────────────────────

function EntityNode({
  entity,
  depth,
  onDelete,
  onEdit,
  onSelect,
}: {
  entity: Entity;
  depth: number;
  onDelete: (id: number) => void;
  onEdit: (entity: Entity) => void;
  onSelect: (id: number) => void;
}) {
  const { isAdmin } = useAuth();
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
          <span className="text-[10px] text-accent-sand border border-accent-sand/30 rounded px-1.5 py-0.5">
            défaut
          </span>
        )}

        {isAdmin && (
          <>
            <button
              className="opacity-0 group-hover:opacity-100 text-[#8a8a8a] hover:text-white transition-opacity ml-1"
              onClick={(e) => { e.stopPropagation(); onEdit(entity); }}
              title="Modifier"
            >
              <Pencil size={13} />
            </button>
            <button
              className="opacity-0 group-hover:opacity-100 text-[#8a8a8a] hover:text-alert transition-opacity"
              onClick={(e) => { e.stopPropagation(); onDelete(entity.id); }}
              title="Supprimer"
            >
              <Trash2 size={13} />
            </button>
          </>
        )}
      </div>

      {hasChildren && expanded && (
        <div>
          {entity.children!.map((child) => (
            <EntityNode
              key={child.id}
              entity={child}
              depth={depth + 1}
              onDelete={onDelete}
              onEdit={onEdit}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Entity create / edit modal ───────────────────────────────────────────────

function EntityModal({
  type,
  entity,
  internalEntities,
  onClose,
  onSaved,
}: {
  type: "internal" | "external";
  entity?: Entity | null;
  internalEntities: Entity[];
  onClose: () => void;
  onSaved: (updated?: Entity) => void;
}) {
  const isEdit = !!entity;
  const [name, setName] = useState(entity?.name ?? "");
  const [description, setDescription] = useState(entity?.description ?? "");
  const [parentId, setParentId] = useState<number | "">(entity?.parent_id ?? "");
  const [color, setColor] = useState(entity?.color ?? "#F2C48D");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      if (isEdit) {
        const payload: any = { name: name.trim(), description: description.trim(), color };
        if (type === "internal") payload.parent_id = parentId !== "" ? parentId : null;
        const updated = await api.updateEntityNode(entity!.id, payload);
        onSaved(updated);
      } else {
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
        onSaved();
      }
      onClose();
    } catch (err: any) {
      setError(err.message || "Erreur lors de l'enregistrement");
    } finally {
      setSaving(false);
    }
  }

  // En édition d'une entité interne, elle ne peut pas être son propre parent.
  const parentChoices = internalEntities.filter((e) => !isEdit || e.id !== entity!.id);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-bg-card border border-border rounded-2xl p-6 w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-base font-semibold text-white">
            {isEdit ? "Modifier l'entité" : "Nouvelle entité"} {type === "internal" ? "interne" : "externe"}
          </h2>
          <button onClick={onClose} className="text-[#8a8a8a] hover:text-white">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">Nom *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-[#1a1a1a] border border-border-hover rounded-lg px-3 py-2 text-sm text-white placeholder-[#555] focus:outline-none focus:border-accent-sand/50"
              placeholder="Nom de l'entité"
              required
              autoFocus
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">Description</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full bg-[#1a1a1a] border border-border-hover rounded-lg px-3 py-2 text-sm text-white placeholder-[#555] focus:outline-none focus:border-accent-sand/50"
              placeholder="Description optionnelle"
            />
          </div>

          {type === "internal" && parentChoices.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1.5">Entité parente</label>
              <select
                value={parentId}
                onChange={(e) => setParentId(e.target.value !== "" ? parseInt(e.target.value, 10) : "")}
                className="w-full bg-[#1a1a1a] border border-border-hover rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-accent-sand/50"
              >
                <option value="">Aucune (racine)</option>
                {parentChoices.map((e) => (
                  <option key={e.id} value={e.id}>{e.name}</option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">Couleur</label>
            <div className="flex items-center gap-3">
              <input
                type="color"
                value={color}
                onChange={(e) => setColor(e.target.value)}
                className="w-10 h-10 rounded-lg border border-border-hover bg-[#1a1a1a] cursor-pointer"
              />
              <span className="text-sm text-[#8a8a8a]">{color}</span>
            </div>
          </div>

          {error && (
            <div className="text-sm text-alert bg-[#1a0a0a] border border-alert/20 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 rounded-lg border border-border-hover text-sm text-[#8a8a8a] hover:text-white hover:border-[#444] transition-colors"
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={saving || !name.trim()}
              className="flex-1 px-4 py-2 rounded-lg bg-accent-sand text-black text-sm font-medium hover:bg-[#e5b57e] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isEdit ? (saving ? "..." : "Enregistrer") : (saving ? "Création..." : "Créer")}
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
  const { isAdmin } = useAuth();
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

  function findEntity(tree: typeof entityTree, id: number): Entity | null {
    for (const e of tree) {
      if (e.id === id) return e;
      if (e.children) {
        const found = findEntity(e.children, id);
        if (found) return found;
      }
    }
    return null;
  }

  const entity = findEntity(entityTree, entityId);
  const isAggregate = entity?.balance_mode === "aggregate";

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
    setRefDate(balance?.reference_date ?? localToday());
    // reference_amount est en centimes -> convertir en euros pour le champ de saisie
    setRefAmount(balance?.reference_amount != null ? String(centsToEuros(balance.reference_amount)) : "");
    setRefError(null);
    setEditingRef(true);
  }

  async function handleSaveRef(e: React.FormEvent) {
    e.preventDefault();
    setRefSaving(true);
    setRefError(null);
    try {
      // La saisie est en euros -> envoyer en centimes entiers à l'API
      await api.updateBalanceRef(entityId, {
        reference_date: refDate,
        reference_amount: eurosToCents(refAmount),
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
  // Pour une entité agrégée (BDA), le consolidé = total réel en Trésorerie
  // (propre déduit + clubs), et non l'ancien solde consolidé par référence.
  const consolidatedCents =
    isAggregate && balance?.treasury_total_cents != null
      ? balance.treasury_total_cents
      : consolidated
        ? consolidated.consolidated_balance
        : 0;

  return (
    <div className="bg-[#0d0d0d] border border-border rounded-2xl p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-white">{entityName}</h3>
          {isAggregate && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-accent-sand/10 text-accent-sand border border-accent-sand/30">
              Agrégé
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => { setSelectedEntityId(entityId); navigate("/transactions"); }}
            className="text-xs text-accent-sand hover:underline inline-flex items-center gap-1"
            title="Voir les transactions de cette entité"
          >
            Transactions <ArrowRight size={11} />
          </button>
          <button onClick={onClose} className="text-[#8a8a8a] hover:text-white">
            <X size={16} />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-4">
          <PageLoader fullScreen={false} />
        </div>
      ) : (
        <div className="space-y-3">
          {balance && (
            <div className="bg-bg-card border border-border rounded-xl p-4">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs text-[#8a8a8a] uppercase tracking-wider">
                  {isAggregate ? "Solde propre (déduit)" : "Solde propre"}
                </p>
                {isAdmin && !isAggregate && !editingRef && (
                  <button
                    onClick={openEditForm}
                    className="text-[#8a8a8a] hover:text-accent-sand transition-colors"
                    title="Modifier le solde de référence"
                  >
                    <Pencil size={13} />
                  </button>
                )}
                {isAggregate && isAdmin && (
                  <Link
                    to="/treasury"
                    className="text-xs text-accent-sand hover:underline inline-flex items-center gap-0.5"
                    title="Le solde propre se déduit de la Trésorerie"
                  >
                    Trésorerie →
                  </Link>
                )}
              </div>
              <p className={`text-2xl font-bold ${balance.balance >= 0 ? "text-white" : "text-alert"}`}>
                {formatEuros(balance.balance)}
              </p>
              {isAggregate ? (
                <p className="text-xs text-[#555] mt-1">
                  Déduit : Trésorerie
                  {balance.treasury_total_cents != null ? ` ${formatEuros(balance.treasury_total_cents)}` : ""}
                  {" − clubs "}
                  {formatEuros(sumChildren)}
                </p>
              ) : balance.reference_date ? (
                <p className="text-xs text-[#555] mt-1">
                  Réf. {formatDate(balance.reference_date)} : {formatEuros(balance.reference_amount)}
                </p>
              ) : null}

              {!isAggregate && editingRef && (
                <form onSubmit={handleSaveRef} className="mt-3 space-y-2">
                  <div className="flex gap-2">
                    <input
                      type="date"
                      value={refDate}
                      onChange={(e) => setRefDate(e.target.value)}
                      className="flex-1 bg-[#1a1a1a] border border-border-hover rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-accent-sand/50"
                      required
                    />
                    <input
                      type="number"
                      step="0.01"
                      value={refAmount}
                      onChange={(e) => setRefAmount(e.target.value)}
                      placeholder="Montant"
                      className="flex-1 bg-[#1a1a1a] border border-border-hover rounded-lg px-3 py-2 text-sm text-white placeholder-[#555] focus:outline-none focus:border-accent-sand/50"
                      required
                    />
                  </div>
                  {refError && (
                    <p className="text-xs text-alert">{refError}</p>
                  )}
                  <div className="flex gap-2">
                    <button
                      type="submit"
                      disabled={refSaving}
                      className="flex-1 px-3 py-1.5 rounded-lg bg-accent-sand text-black text-sm font-medium hover:bg-[#e5b57e] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {refSaving ? "..." : "Enregistrer"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditingRef(false)}
                      className="flex-1 px-3 py-1.5 rounded-lg border border-border-hover text-sm text-[#8a8a8a] hover:text-white hover:border-[#444] transition-colors"
                    >
                      Annuler
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}

          {hasChildren && (
            <div className="bg-bg-card border border-border rounded-xl p-4">
              <p className="text-xs text-[#8a8a8a] uppercase tracking-wider mb-2">Solde consolidé</p>
              <p className={`text-2xl font-bold ${consolidatedCents >= 0 ? "text-accent-sand" : "text-alert"}`}>
                {formatEuros(consolidatedCents)}
              </p>
              {isAggregate && (
                <p className="text-xs text-[#555] mt-1">= total en Trésorerie (BDA + clubs)</p>
              )}
              <div className="mt-3 space-y-1">
                {consolidated!.children.map((child) => (
                  <div key={child.entity_id} className="flex justify-between text-xs">
                    <span className="text-text-secondary">{findName(entityTree, child.entity_id) ?? `Entité #${child.entity_id}`}</span>
                    <span className={child.balance >= 0 ? "text-text-secondary" : "text-alert"}>
                      {formatEuros(child.balance)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!balance && !consolidated && (
            <p className="text-sm text-[#8a8a8a] text-center py-2">Aucune donnée disponible</p>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function EntityTree() {
  const { isAdmin } = useAuth();
  const { entities, reload } = useEntity();
  const [externalEntities, setExternalEntities] = useState<Entity[]>([]);
  const [showCreateModal, setShowCreateModal] = useState<"internal" | "external" | null>(null);
  const [editingEntity, setEditingEntity] = useState<Entity | null>(null);
  const [selectedEntityId, setSelectedEntityId] = useState<number | null>(null);
  const [selectedEntityName, setSelectedEntityName] = useState<string>("");
  const [deleteTarget, setDeleteTarget] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);

  useEffect(() => {
    api.getEntities("external")
      .then(setExternalEntities)
      .catch(() => setExternalEntities([]));
  }, []);

  function requestDelete(id: number) {
    setPageError(null);
    setDeleteTarget(id);
  }

  async function confirmDelete() {
    if (deleteTarget == null) return;
    setDeleting(true);
    setPageError(null);
    try {
      await api.deleteEntity(deleteTarget);
      await reload();
      api.getEntities("external").then(setExternalEntities).catch(() => {});
      if (selectedEntityId === deleteTarget) setSelectedEntityId(null);
      setDeleteTarget(null);
    } catch (err: any) {
      setPageError(err.message || "Erreur lors de la suppression");
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  }

  function handleSelectEntity(id: number) {
    const found = findEntityFlat([...entities, ...externalEntities], id);
    if (found) {
      setSelectedEntityId(id);
      setSelectedEntityName(found.name);
    }
  }

  async function handleSaved(updated?: Entity) {
    await reload();
    await api.getEntities("external").then(setExternalEntities).catch(() => {});
    // Si l'entité modifiée est celle affichée dans le panneau de détail, on
    // reflète immédiatement son nouveau nom (sinon le titre resterait figé
    // sur l'ancien nom jusqu'à une nouvelle sélection).
    if (updated && selectedEntityId === updated.id) {
      setSelectedEntityName(updated.name);
    }
  }

  // Flatten internal entities for parent selector
  const flatInternal = flattenTree(entities);

  return (
    <div className="p-8 max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white mb-2" style={{ letterSpacing: "-0.02em" }}>Entités</h1>
        <p className="text-sm text-text-secondary leading-relaxed">
          Les entités représentent <span className="text-white font-medium">qui gère le budget</span> :
          ta structure et ses <em>sous-clubs, pôles, sections</em>, ainsi que les{" "}
          <em>tiers externes</em> (banque, fournisseurs).
        </p>
        <p className="text-xs text-[#8a8a8a] mt-1 leading-relaxed">
          Pour classer <span className="text-text-secondary">la nature</span> des dépenses (matériel,
          transport…), utilise plutôt{" "}
          <a href="/categories" className="text-accent-sand hover:underline">Catégories</a>.
        </p>
      </div>

      {pageError && (
        <div className="mb-4 bg-[#1a0a0a] border border-alert/30 text-alert rounded-2xl p-4 text-sm flex items-center justify-between">
          {pageError}
          <button onClick={() => setPageError(null)} className="text-alert/70 hover:text-alert">
            <X size={16} />
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column: trees */}
        <div className="lg:col-span-2 space-y-6">
          {/* Internal entities */}
          <div className="bg-bg-card border border-border rounded-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <div className="flex items-center gap-2">
                <Building2 size={16} className="text-accent-sand" strokeWidth={1.5} />
                <span className="text-sm font-semibold text-white">Entités internes</span>
                <span className="text-xs text-[#555] bg-[#1a1a1a] border border-[#2a2a2a] rounded-full px-2 py-0.5">
                  {flatInternal.length}
                </span>
              </div>
              {isAdmin && (
                <button
                  onClick={() => setShowCreateModal("internal")}
                  className="flex items-center gap-1.5 text-xs text-accent-sand border border-accent-sand/30 hover:border-accent-sand/60 hover:bg-accent-sand/5 rounded-lg px-3 py-1.5 transition-colors"
                >
                  <Plus size={13} />
                  Nouvelle
                </button>
              )}
            </div>

            <div className="p-2">
              {entities.length === 0 ? (
                <div className="text-center py-8 text-sm text-[#555]">
                  Aucune entité interne. Crée-en une pour commencer.
                </div>
              ) : (
                entities.map((e) => (
                  <EntityNode
                    key={e.id}
                    entity={e}
                    depth={0}
                    onDelete={requestDelete}
                    onEdit={setEditingEntity}
                    onSelect={handleSelectEntity}
                  />
                ))
              )}
            </div>
          </div>

          {/* External entities */}
          <div className="bg-bg-card border border-border rounded-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <div className="flex items-center gap-2">
                <Users size={16} className="text-text-secondary" strokeWidth={1.5} />
                <span className="text-sm font-semibold text-white">Entités externes</span>
                <span className="text-xs text-[#555] bg-[#1a1a1a] border border-[#2a2a2a] rounded-full px-2 py-0.5">
                  {externalEntities.length}
                </span>
              </div>
              {isAdmin && (
                <button
                  onClick={() => setShowCreateModal("external")}
                  className="flex items-center gap-1.5 text-xs text-text-secondary border border-border-hover hover:border-[#555] hover:bg-[#1a1a1a] rounded-lg px-3 py-1.5 transition-colors"
                >
                  <Plus size={13} />
                  Nouvelle
                </button>
              )}
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
                    {isAdmin && (
                      <>
                        <button
                          className="opacity-0 group-hover:opacity-100 text-[#8a8a8a] hover:text-white transition-opacity"
                          onClick={(e2) => { e2.stopPropagation(); setEditingEntity(e); }}
                          title="Modifier"
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          className="opacity-0 group-hover:opacity-100 text-[#8a8a8a] hover:text-alert transition-opacity"
                          onClick={(e2) => { e2.stopPropagation(); requestDelete(e.id); }}
                          title="Supprimer"
                        >
                          <Trash2 size={13} />
                        </button>
                      </>
                    )}
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
                Clique sur une entité pour voir son solde
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Create / edit modal */}
      {(showCreateModal || editingEntity) && (
        <EntityModal
          type={editingEntity ? (editingEntity.type as "internal" | "external") : showCreateModal!}
          entity={editingEntity}
          internalEntities={flatInternal}
          onClose={() => { setShowCreateModal(null); setEditingEntity(null); }}
          onSaved={handleSaved}
        />
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Supprimer cette entité ?"
        message="Cette action est irréversible. Les transactions liées ne sont pas supprimées."
        confirmLabel="Supprimer"
        danger
        busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
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
