import { useEffect, useState } from "react";
import { api } from "../../api";
import { useAuth } from "../../core/AuthContext";
import { Users, Plus, Trash2, Shield, Eye, X, ChevronDown, ChevronUp } from "lucide-react";

interface User {
  id: number;
  username: string;
  display_name: string;
  role: string;
  active: boolean;
}

interface UserEntity {
  entity_id: number;
  entity_name: string;
  role: string;
}

interface Entity {
  id: number;
  name: string;
}

const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  tresorier: "Trésorier",
  reader: "Lecteur",
};

const ROLE_ICON: Record<string, typeof Shield> = {
  admin: Shield,
  tresorier: Shield,
  reader: Eye,
};

function RoleBadge({ role }: { role: string }) {
  const Icon = ROLE_ICON[role] || Eye;
  const colors: Record<string, string> = {
    admin: "text-[#F2C48D] bg-[#F2C48D]/10 border-[#F2C48D]/20",
    tresorier: "text-[#64B5F6] bg-[#64B5F6]/10 border-[#64B5F6]/20",
    reader: "text-[#888] bg-[#1a1a1a] border-[#333]",
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border ${colors[role] || colors.reader}`}>
      <Icon size={11} strokeWidth={2} />
      {ROLE_LABELS[role] || role}
    </span>
  );
}

// ─── Create User Modal ────────────────────────────────────────────────────────

function CreateUserModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("reader");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      await api.createUser({ username, display_name: displayName, password, role });
      onCreated();
      onClose();
    } catch (err: any) {
      setError(err.message || "Erreur lors de la création");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="bg-[#111] border border-[#222] rounded-2xl p-6 w-full max-w-md">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-base font-semibold text-white">Nouvel utilisateur</h3>
          <button onClick={onClose} className="text-[#666] hover:text-white transition-colors">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-[#666] mb-1.5">Identifiant</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D]"
              required
              autoFocus
            />
          </div>
          <div>
            <label className="block text-xs text-[#666] mb-1.5">Nom affiché</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D]"
            />
          </div>
          <div>
            <label className="block text-xs text-[#666] mb-1.5">Mot de passe</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D]"
              required
            />
          </div>
          <div>
            <label className="block text-xs text-[#666] mb-1.5">Rôle global</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D]"
            >
              <option value="reader">Lecteur</option>
              <option value="tresorier">Trésorier</option>
              <option value="admin">Admin</option>
            </select>
          </div>

          {error && <p className="text-[#FF5252] text-xs">{error}</p>}

          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 border border-[#333] text-[#666] hover:text-white rounded-lg py-2.5 text-sm transition-colors"
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={saving}
              className="flex-1 bg-[#F2C48D] text-black font-medium rounded-lg py-2.5 text-sm hover:bg-[#e5b87e] transition-colors disabled:opacity-50"
            >
              {saving ? "Création..." : "Créer"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── User Row with entity access ──────────────────────────────────────────────

function UserRow({
  user,
  entities,
  onDelete,
}: {
  user: User;
  entities: Entity[];
  onDelete: (id: number) => void;
}) {
  const { user: me } = useAuth();
  const [expanded, setExpanded] = useState(false);
  const [userEntities, setUserEntities] = useState<UserEntity[]>([]);
  const [loadingEntities, setLoadingEntities] = useState(false);
  const [assignEntityId, setAssignEntityId] = useState("");
  const [assignRole, setAssignRole] = useState("reader");
  const [assigning, setAssigning] = useState(false);
  const [error, setError] = useState("");

  async function loadEntities() {
    setLoadingEntities(true);
    try {
      const data = await api.getUserEntities(user.id);
      setUserEntities(data);
    } catch {
      // ignore
    } finally {
      setLoadingEntities(false);
    }
  }

  function toggleExpanded() {
    if (!expanded) loadEntities();
    setExpanded((v) => !v);
  }

  async function handleAssign(e: React.FormEvent) {
    e.preventDefault();
    if (!assignEntityId) return;
    setAssigning(true);
    setError("");
    try {
      await api.assignUserEntity(user.id, { entity_id: parseInt(assignEntityId), role: assignRole });
      await loadEntities();
      setAssignEntityId("");
    } catch (err: any) {
      setError(err.message || "Erreur");
    } finally {
      setAssigning(false);
    }
  }

  async function handleRemoveEntity(entityId: number) {
    try {
      await api.removeUserEntity(user.id, entityId);
      setUserEntities((prev) => prev.filter((e) => e.entity_id !== entityId));
    } catch {
      // ignore
    }
  }

  const isSelf = me?.id === user.id;

  return (
    <div className="border-b border-[#1a1a1a] last:border-0">
      <div className="flex items-center justify-between px-5 py-4">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-full bg-[#1a1a1a] border border-[#333] flex items-center justify-center flex-shrink-0">
            <span className="text-xs text-[#666] font-medium uppercase">
              {(user.display_name || user.username).charAt(0)}
            </span>
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-white truncate">
                {user.display_name || user.username}
              </span>
              {isSelf && (
                <span className="text-xs text-[#555] bg-[#1a1a1a] border border-[#222] px-1.5 py-0.5 rounded-full">
                  vous
                </span>
              )}
            </div>
            <span className="text-xs text-[#555]">{user.username}</span>
          </div>
        </div>

        <div className="flex items-center gap-3 flex-shrink-0">
          <RoleBadge role={user.role} />
          <button
            onClick={toggleExpanded}
            className="text-[#555] hover:text-[#F2C48D] transition-colors p-1"
            title="Accès entités"
          >
            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
          {!isSelf && (
            <button
              onClick={() => onDelete(user.id)}
              className="text-[#555] hover:text-[#FF5252] transition-colors p-1"
              title="Supprimer"
            >
              <Trash2 size={15} />
            </button>
          )}
        </div>
      </div>

      {expanded && (
        <div className="px-5 pb-4 space-y-3">
          {loadingEntities ? (
            <div className="flex items-center justify-center py-4">
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-[#F2C48D]" />
            </div>
          ) : (
            <>
              {userEntities.length === 0 ? (
                <p className="text-xs text-[#555] py-2">Aucun accès entité spécifique.</p>
              ) : (
                <div className="space-y-1.5">
                  {userEntities.map((ue) => (
                    <div
                      key={ue.entity_id}
                      className="flex items-center justify-between bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg px-3 py-2"
                    >
                      <span className="text-sm text-white">{ue.entity_name}</span>
                      <div className="flex items-center gap-2">
                        <RoleBadge role={ue.role} />
                        <button
                          onClick={() => handleRemoveEntity(ue.entity_id)}
                          className="text-[#555] hover:text-[#FF5252] transition-colors p-0.5"
                        >
                          <X size={13} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <form onSubmit={handleAssign} className="flex gap-2 pt-1">
                <select
                  value={assignEntityId}
                  onChange={(e) => setAssignEntityId(e.target.value)}
                  className="flex-1 bg-[#0a0a0a] border border-[#333] rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-[#F2C48D]"
                >
                  <option value="">Choisir une entité...</option>
                  {entities
                    .filter((en) => !userEntities.find((ue) => ue.entity_id === en.id))
                    .map((en) => (
                      <option key={en.id} value={en.id}>
                        {en.name}
                      </option>
                    ))}
                </select>
                <select
                  value={assignRole}
                  onChange={(e) => setAssignRole(e.target.value)}
                  className="bg-[#0a0a0a] border border-[#333] rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-[#F2C48D]"
                >
                  <option value="reader">Lecteur</option>
                  <option value="tresorier">Trésorier</option>
                  <option value="admin">Admin</option>
                </select>
                <button
                  type="submit"
                  disabled={!assignEntityId || assigning}
                  className="bg-[#F2C48D] text-black font-medium rounded-lg px-3 py-2 text-xs hover:bg-[#e5b87e] transition-colors disabled:opacity-40"
                >
                  <Plus size={14} />
                </button>
              </form>
              {error && <p className="text-[#FF5252] text-xs">{error}</p>}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main UserManager ─────────────────────────────────────────────────────────

export default function UserManager() {
  const [users, setUsers] = useState<User[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    try {
      const [u, e] = await Promise.all([api.getUsers(), api.getEntities()]);
      setUsers(u);
      setEntities(e);
    } catch (err: any) {
      setError(err.message || "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleDelete(id: number) {
    if (!confirm("Supprimer cet utilisateur ?")) return;
    try {
      await api.deleteUser(id);
      setUsers((prev) => prev.filter((u) => u.id !== id));
    } catch (err: any) {
      setError(err.message || "Erreur de suppression");
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#F2C48D]" />
      </div>
    );
  }

  return (
    <div className="p-8 max-w-2xl">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1
            className="text-3xl font-bold text-white"
            style={{ letterSpacing: "-0.02em" }}
          >
            Utilisateurs
          </h1>
          <p className="text-[#555] text-sm mt-1">
            {users.length} utilisateur{users.length !== 1 ? "s" : ""}
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 bg-[#F2C48D] text-black font-medium rounded-xl px-4 py-2.5 text-sm hover:bg-[#e5b87e] transition-colors"
        >
          <Plus size={16} />
          Nouveau
        </button>
      </div>

      {error && (
        <div className="mb-4 bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-2xl p-4 text-sm flex justify-between items-center">
          <span>{error}</span>
          <button onClick={() => setError("")} className="text-xs underline ml-2">
            Fermer
          </button>
        </div>
      )}

      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
        {users.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <Users size={32} className="text-[#333] mb-3" strokeWidth={1.5} />
            <p className="text-[#555] text-sm">Aucun utilisateur</p>
          </div>
        ) : (
          users.map((user) => (
            <UserRow
              key={user.id}
              user={user}
              entities={entities}
              onDelete={handleDelete}
            />
          ))
        )}
      </div>

      {showCreate && (
        <CreateUserModal
          onClose={() => setShowCreate(false)}
          onCreated={load}
        />
      )}
    </div>
  );
}
