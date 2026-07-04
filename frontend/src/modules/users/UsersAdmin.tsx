import { useEffect, useMemo, useState } from "react";
import { Plus, Pencil, Trash2, X, Copy, Check, ShieldCheck, Users } from "lucide-react";
import { api } from "../../api";
import { useAuth } from "../../core/AuthContext";
import { useEntity } from "../../core/EntityContext";
import { Entity } from "../../types";
import EmptyState from "../../core/EmptyState";

type RoleName = "treasurer" | "viewer";

interface RoleRow {
  entity_id: number;
  role: RoleName;
}

interface UserAccount {
  id: number;
  email: string;
  display_name: string;
  is_admin: number;
  is_active: number;
  roles: RoleRow[];
  allowed_entity_ids: number[] | null;
  last_login_at: string | null;
}

interface Invitation {
  id: number;
  email: string;
  is_admin: number;
  roles: RoleRow[];
  expires_at: string;
  created_at: string;
}

interface CreatedInvitation {
  id: number;
  token: string;
  url_path: string;
  email: string;
  expires_at: string;
}

interface FlatEntity {
  id: number;
  name: string;
  depth: number;
}

const ROLE_LABELS: Record<RoleName, string> = { treasurer: "Trésorier", viewer: "Lecteur" };

const inputClass = "w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#444]";
const labelClass = "block text-sm font-medium text-[#B0B0B0] mb-1.5";

function flattenEntities(nodes: Entity[], depth = 0, out: FlatEntity[] = []): FlatEntity[] {
  for (const n of nodes) {
    out.push({ id: n.id, name: n.name, depth });
    if (n.children && n.children.length > 0) flattenEntities(n.children, depth + 1, out);
  }
  return out;
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "Jamais connecté";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Date inconnue";
  return d.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

function segBtnClass(active: boolean): string {
  return `flex-1 px-4 py-2 text-sm font-semibold rounded-xl border transition-colors ${
    active
      ? "bg-[#F2C48D] text-black border-[#F2C48D]"
      : "bg-[#0a0a0a] text-[#B0B0B0] border-[#222] hover:border-[#333]"
  }`;
}

function RolesEditor({
  rows, onChange, entities,
}: { rows: RoleRow[]; onChange: (rows: RoleRow[]) => void; entities: FlatEntity[] }) {
  function updateRow(idx: number, patch: Partial<RoleRow>) {
    onChange(rows.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  }
  function removeRow(idx: number) {
    onChange(rows.filter((_, i) => i !== idx));
  }
  function addRow() {
    const used = new Set(rows.map((r) => r.entity_id));
    const next = entities.find((e) => !used.has(e.id)) ?? entities[0];
    if (!next) return;
    onChange([...rows, { entity_id: next.id, role: "viewer" }]);
  }

  if (entities.length === 0) {
    return <p className="text-xs text-[#666]">Aucune entité disponible : crée d'abord une entité.</p>;
  }

  return (
    <div className="space-y-2">
      {rows.length === 0 && (
        <p className="text-xs text-[#666] mb-1">Aucun rôle attribué pour l'instant.</p>
      )}
      {rows.map((r, idx) => (
        <div key={idx} className="flex items-center gap-2">
          <select
            value={r.entity_id}
            onChange={(e) => updateRow(idx, { entity_id: Number(e.target.value) })}
            className="flex-1 bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors"
          >
            {entities.map((e) => (
              <option key={e.id} value={e.id}>
                {"  ".repeat(e.depth)}{e.name}
              </option>
            ))}
          </select>
          <select
            value={r.role}
            onChange={(e) => updateRow(idx, { role: e.target.value as RoleName })}
            className="w-32 bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors"
          >
            <option value="treasurer">Trésorier</option>
            <option value="viewer">Lecteur</option>
          </select>
          <button
            type="button"
            onClick={() => removeRow(idx)}
            className="p-2 text-[#666] hover:text-[#FF5252] rounded-lg hover:bg-[#222] transition-colors"
            title="Retirer ce rôle"
          >
            <Trash2 size={14} strokeWidth={1.5} />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={addRow}
        className="flex items-center gap-1.5 text-xs font-medium text-[#F2C48D] hover:text-[#e8b87a] transition-colors"
      >
        <Plus size={13} /> Ajouter un rôle
      </button>
    </div>
  );
}

export default function UsersAdmin() {
  const { user: me } = useAuth();
  const { entities } = useEntity();
  const flatEntities = useMemo(() => flattenEntities(entities), [entities]);

  const [users, setUsers] = useState<UserAccount[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal : édition des rôles d'un compte existant
  const [rolesUser, setRolesUser] = useState<UserAccount | null>(null);
  const [rolesDraft, setRolesDraft] = useState<RoleRow[]>([]);
  const [savingRoles, setSavingRoles] = useState(false);
  const [rolesError, setRolesError] = useState<string | null>(null);

  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [revokingId, setRevokingId] = useState<number | null>(null);
  const [revokedOkId, setRevokedOkId] = useState<number | null>(null);

  const [confirmDeleteInvite, setConfirmDeleteInvite] = useState<number | null>(null);

  // Modal : invitation
  const [showInvite, setShowInvite] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteIsAdmin, setInviteIsAdmin] = useState(false);
  const [inviteRoles, setInviteRoles] = useState<RoleRow[]>([]);
  const [inviting, setInviting] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [createdInvitation, setCreatedInvitation] = useState<CreatedInvitation | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);

  async function loadAll() {
    setLoading(true);
    try {
      const [u, inv] = await Promise.all([api.listUsers(), api.listInvitations()]);
      setUsers(u);
      setInvitations(inv);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadAll(); }, []);

  function entityName(id: number): string {
    return flatEntities.find((e) => e.id === id)?.name || `Entité ${id}`;
  }

  function openRoles(u: UserAccount) {
    setRolesError(null);
    setRolesUser(u);
    setRolesDraft(u.roles.map((r) => ({ ...r })));
  }
  function closeRoles() {
    setRolesUser(null);
    setRolesDraft([]);
  }

  async function saveRoles() {
    if (!rolesUser) return;
    setSavingRoles(true);
    setRolesError(null);
    try {
      const updated = await api.setUserRoles(rolesUser.id, rolesDraft);
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? { ...u, ...updated } : u)));
      closeRoles();
    } catch (e: any) {
      setRolesError(e.message);
    } finally {
      setSavingRoles(false);
    }
  }

  async function toggleActive(u: UserAccount) {
    setTogglingId(u.id);
    try {
      const updated = await api.updateUser(u.id, { is_active: !u.is_active });
      setUsers((prev) => prev.map((x) => (x.id === updated.id ? { ...x, ...updated } : x)));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setTogglingId(null);
    }
  }

  async function revokeSessions(u: UserAccount) {
    setRevokingId(u.id);
    try {
      await api.revokeUserSessions(u.id);
      setRevokedOkId(u.id);
      setTimeout(() => setRevokedOkId((cur) => (cur === u.id ? null : cur)), 2000);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRevokingId(null);
    }
  }

  async function handleDeleteInvitation(id: number) {
    try {
      await api.deleteInvitation(id);
      setInvitations((prev) => prev.filter((i) => i.id !== id));
      setConfirmDeleteInvite(null);
    } catch (e: any) {
      setError(e.message);
    }
  }

  function openInvite() {
    setInviteEmail("");
    setInviteIsAdmin(false);
    setInviteRoles([]);
    setInviteError(null);
    setCreatedInvitation(null);
    setLinkCopied(false);
    setShowInvite(true);
  }
  function closeInvite() {
    const hadCreated = !!createdInvitation;
    setShowInvite(false);
    if (hadCreated) loadAll();
  }

  async function submitInvite(e: React.FormEvent) {
    e.preventDefault();
    setInviting(true);
    setInviteError(null);
    try {
      const created = await api.createInvitation({
        email: inviteEmail.trim(),
        is_admin: inviteIsAdmin,
        roles: inviteIsAdmin ? [] : inviteRoles,
      });
      setCreatedInvitation(created);
    } catch (e: any) {
      setInviteError(e.message);
    } finally {
      setInviting(false);
    }
  }

  async function copyLink() {
    if (!createdInvitation) return;
    const fullUrl = `${window.location.origin}${createdInvitation.url_path}`;
    try {
      await navigator.clipboard.writeText(fullUrl);
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 2000);
    } catch {
      setInviteError("Impossible de copier le lien automatiquement : copie-le manuellement.");
    }
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>Utilisateurs</h1>
          <p className="text-sm text-[#666] mt-1">Comptes, connexions et rôles par entité.</p>
        </div>
        <button onClick={openInvite} className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] transition-colors">
          <Plus size={15} /> Inviter
        </button>
      </div>

      {error && (
        <div className="mb-4 bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-2xl p-4 text-sm flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)} className="text-[#FF5252]/70 hover:text-[#FF5252]"><X size={16} /></button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#F2C48D]" />
        </div>
      ) : users.length === 0 ? (
        <EmptyState
          icon={Users}
          title="Aucun compte pour l'instant"
          description="Invite ton premier utilisateur pour lui donner accès à OpenFlow."
          ctaLabel="Inviter un utilisateur"
          onCta={openInvite}
        />
      ) : (
        <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden mb-10">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Email</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Nom</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Rôles</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Dernière connexion</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Statut</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u, idx) => {
                const isSelf = me?.id === u.id;
                return (
                  <tr key={u.id} className={idx > 0 ? "border-t border-[#1a1a1a]" : ""}>
                    <td className="px-5 py-3.5 font-medium text-white">{u.email}</td>
                    <td className="px-5 py-3.5 text-[#B0B0B0]">
                      {u.display_name || <span className="text-[#444]">Non renseigné</span>}
                    </td>
                    <td className="px-5 py-3.5">
                      {u.is_admin ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border border-[#F2C48D]/40 bg-[#F2C48D]/10 text-[#F2C48D]">
                          <ShieldCheck size={12} /> Admin
                        </span>
                      ) : u.roles.length === 0 ? (
                        <span className="text-xs text-[#555]">Aucun rôle</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {u.roles.map((r) => (
                            <span key={r.entity_id} className="inline-block px-2 py-0.5 rounded-full text-xs border border-[#333] text-[#B0B0B0]">
                              {entityName(r.entity_id)} · {ROLE_LABELS[r.role]}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-[#B0B0B0]">{formatDateTime(u.last_login_at)}</td>
                    <td className="px-5 py-3.5">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-xs border ${
                        u.is_active
                          ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                          : "bg-[#FF5252]/10 text-[#FF5252] border-[#FF5252]/30"
                      }`}>
                        {u.is_active ? "Actif" : "Désactivé"}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <div className="flex items-center justify-end gap-3 text-xs whitespace-nowrap">
                        {!u.is_admin && (
                          <button onClick={() => openRoles(u)} className="font-medium text-[#F2C48D] hover:text-[#e8b87a] transition-colors flex items-center gap-1">
                            <Pencil size={12} /> Rôles
                          </button>
                        )}
                        <button
                          onClick={() => toggleActive(u)}
                          disabled={isSelf || togglingId === u.id}
                          title={isSelf ? "Impossible de désactiver son propre compte" : undefined}
                          className="font-medium text-[#B0B0B0] hover:text-white disabled:opacity-30 disabled:hover:text-[#B0B0B0] transition-colors"
                        >
                          {togglingId === u.id ? "..." : u.is_active ? "Désactiver" : "Réactiver"}
                        </button>
                        <button
                          onClick={() => revokeSessions(u)}
                          disabled={revokingId === u.id}
                          className="font-medium text-[#B0B0B0] hover:text-white disabled:opacity-30 transition-colors"
                        >
                          {revokedOkId === u.id ? "Déconnecté" : revokingId === u.id ? "..." : "Déconnecter partout"}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">Invitations en attente</h2>
        {invitations.length > 0 && (
          <span className="text-xs text-[#555]">{invitations.length} invitation{invitations.length > 1 ? "s" : ""}</span>
        )}
      </div>
      {!loading && invitations.length === 0 ? (
        <p className="text-sm text-[#555] bg-[#111] border border-[#222] rounded-2xl p-6 text-center">
          Aucune invitation en attente.
        </p>
      ) : !loading && (
        <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Email</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Rôle prévu</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#666] uppercase tracking-wider">Expire le</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#666] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {invitations.map((inv, idx) => (
                <tr key={inv.id} className={idx > 0 ? "border-t border-[#1a1a1a]" : ""}>
                  <td className="px-5 py-3.5 text-white">{inv.email}</td>
                  <td className="px-5 py-3.5 text-[#B0B0B0]">
                    {inv.is_admin
                      ? "Admin"
                      : inv.roles.length === 0
                        ? "Aucun rôle"
                        : inv.roles.map((r) => `${entityName(r.entity_id)} · ${ROLE_LABELS[r.role]}`).join(", ")}
                  </td>
                  <td className="px-5 py-3.5 text-[#B0B0B0]">{formatDateTime(inv.expires_at)}</td>
                  <td className="px-5 py-3.5 text-right">
                    {confirmDeleteInvite === inv.id ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="text-xs text-[#666]">Supprimer ?</span>
                        <button onClick={() => handleDeleteInvitation(inv.id)} className="text-xs font-medium text-[#FF5252] hover:text-red-400">Oui</button>
                        <button onClick={() => setConfirmDeleteInvite(null)} className="text-xs font-medium text-[#666] hover:text-white">Non</button>
                      </span>
                    ) : (
                      <button onClick={() => setConfirmDeleteInvite(inv.id)} className="p-1.5 text-[#666] hover:text-[#FF5252] rounded-lg hover:bg-[#222] transition-colors" title="Supprimer">
                        <Trash2 size={14} strokeWidth={1.5} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal : modifier les rôles d'un compte */}
      {rolesUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => !savingRoles && closeRoles()}>
          <div className="w-full max-w-lg bg-[#111] border border-[#222] rounded-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="border-b border-[#1a1a1a] px-6 py-4 flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-white">Modifier les rôles</h2>
                <p className="text-xs text-[#666] mt-0.5">{rolesUser.email}</p>
              </div>
              <button onClick={closeRoles} className="text-[#666] hover:text-white"><X size={18} /></button>
            </div>
            {rolesError && (
              <div className="mx-6 mt-4 bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-xl p-3 text-sm">{rolesError}</div>
            )}
            <div className="px-6 py-6">
              <RolesEditor rows={rolesDraft} onChange={setRolesDraft} entities={flatEntities} />
            </div>
            <div className="px-6 pb-6 flex justify-end gap-3">
              <button type="button" onClick={closeRoles} className="px-5 py-2.5 text-sm font-semibold text-white border border-[#333] rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors">Annuler</button>
              <button type="button" onClick={saveRoles} disabled={savingRoles} className="px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-50 transition-colors">
                {savingRoles ? "Enregistrement..." : "Enregistrer"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal : inviter un utilisateur */}
      {showInvite && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => !inviting && closeInvite()}>
          <div className="w-full max-w-lg bg-[#111] border border-[#222] rounded-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="border-b border-[#1a1a1a] px-6 py-4 flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-white">Inviter un utilisateur</h2>
                <p className="text-xs text-[#666] mt-0.5">Génère un lien d'invitation à usage unique.</p>
              </div>
              <button onClick={closeInvite} className="text-[#666] hover:text-white"><X size={18} /></button>
            </div>

            {inviteError && (
              <div className="mx-6 mt-4 bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-xl p-3 text-sm">{inviteError}</div>
            )}

            {createdInvitation ? (
              <div className="px-6 py-6 space-y-4">
                <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-xl p-4">
                  <p className="text-sm text-emerald-300">
                    Invitation créée pour <span className="font-semibold">{createdInvitation.email}</span>.
                  </p>
                </div>
                <div>
                  <label className={labelClass}>Lien d'invitation</label>
                  <div className="flex items-center gap-2">
                    <input
                      readOnly
                      value={`${window.location.origin}${createdInvitation.url_path}`}
                      onFocus={(e) => e.target.select()}
                      className={`${inputClass} text-xs`}
                    />
                    <button
                      type="button"
                      onClick={copyLink}
                      className="flex-shrink-0 flex items-center gap-1.5 px-4 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-xl hover:bg-[#e8b87a] transition-colors"
                    >
                      {linkCopied ? <><Check size={14} /> Lien copié</> : <><Copy size={14} /> Copier le lien</>}
                    </button>
                  </div>
                  <p className="text-xs text-[#FF5252] mt-2">
                    Ce lien ne sera affiché qu'une seule fois : note-le ou transmets-le maintenant.
                  </p>
                </div>
                <div className="flex justify-end pt-2">
                  <button type="button" onClick={closeInvite} className="px-5 py-2.5 text-sm font-semibold text-white border border-[#333] rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors">
                    Fermer
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={submitInvite} className="px-6 py-6 space-y-4">
                <div>
                  <label className={labelClass}>Email</label>
                  <input
                    type="email"
                    required
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    className={inputClass}
                    placeholder="prenom.nom@mail.fr"
                  />
                </div>
                <div>
                  <label className={labelClass}>Administrateur</label>
                  <div className="flex gap-2">
                    <button type="button" onClick={() => setInviteIsAdmin(true)} className={segBtnClass(inviteIsAdmin)}>Oui</button>
                    <button type="button" onClick={() => setInviteIsAdmin(false)} className={segBtnClass(!inviteIsAdmin)}>Non</button>
                  </div>
                  <p className="text-xs text-[#666] mt-1.5">Un administrateur a accès à toutes les entités et à toutes les fonctionnalités.</p>
                </div>
                {!inviteIsAdmin && (
                  <div>
                    <label className={labelClass}>Rôles</label>
                    <RolesEditor rows={inviteRoles} onChange={setInviteRoles} entities={flatEntities} />
                  </div>
                )}
                <div className="flex justify-end gap-3 pt-2">
                  <button type="button" onClick={closeInvite} className="px-5 py-2.5 text-sm font-semibold text-white border border-[#333] rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors">
                    Annuler
                  </button>
                  <button type="submit" disabled={inviting} className="px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-50 transition-colors">
                    {inviting ? "Envoi..." : "Envoyer l'invitation"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
