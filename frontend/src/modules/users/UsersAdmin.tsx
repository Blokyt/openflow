import { useEffect, useMemo, useState } from "react";
import { Plus, Pencil, Trash2, X, Copy, Check, ShieldCheck, Users } from "lucide-react";
import { api } from "../../api";
import { useAuth } from "../../core/AuthContext";
import { useEntity } from "../../core/EntityContext";
import { useToast } from "../../core/ToastContext";
import { Entity } from "../../types";
import EmptyState from "../../core/EmptyState";
import PageLoader from "../../core/PageLoader";
import { inputClass, labelClass } from "../../core/formStyles";

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

interface LoginEvent {
  id: number;
  email: string;
  ip: string;
  success: number;
  created_at: string;
  user_agent: string;
}

const ROLE_LABELS: Record<RoleName, string> = { treasurer: "Trésorier", viewer: "Lecteur" };

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
      ? "bg-accent-sand text-black border-accent-sand"
      : "bg-[#0a0a0a] text-text-secondary border-border hover:border-border-hover"
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
    return <p className="text-xs text-[#8a8a8a]">Aucune entité disponible : crée d'abord une entité.</p>;
  }

  return (
    <div className="space-y-2">
      {rows.length === 0 && (
        <p className="text-xs text-[#8a8a8a] mb-1">Aucun rôle attribué pour l'instant.</p>
      )}
      {rows.map((r, idx) => (
        <div key={idx} className="flex items-center gap-2">
          <select
            value={r.entity_id}
            onChange={(e) => updateRow(idx, { entity_id: Number(e.target.value) })}
            className="flex-1 bg-[#0a0a0a] border border-border rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-accent-sand transition-colors"
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
            className="w-32 bg-[#0a0a0a] border border-border rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-accent-sand transition-colors"
          >
            <option value="treasurer">Trésorier</option>
            <option value="viewer">Lecteur</option>
          </select>
          <button
            type="button"
            onClick={() => removeRow(idx)}
            className="p-2 text-[#8a8a8a] hover:text-alert rounded-lg hover:bg-[#222] transition-colors"
            title="Retirer ce rôle"
          >
            <Trash2 size={14} strokeWidth={1.5} />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={addRow}
        className="flex items-center gap-1.5 text-xs font-medium text-accent-sand hover:text-[#e8b87a] transition-colors"
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
  const [loginEvents, setLoginEvents] = useState<LoginEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  // Modal : édition des rôles d'un compte existant
  const [rolesUser, setRolesUser] = useState<UserAccount | null>(null);
  const [rolesDraft, setRolesDraft] = useState<RoleRow[]>([]);
  const [savingRoles, setSavingRoles] = useState(false);
  const [rolesError, setRolesError] = useState<string | null>(null);

  // Modal: edit user info (email + display_name)
  const [editUser, setEditUser] = useState<UserAccount | null>(null);
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Reset password link
  const [resetLinkResult, setResetLinkResult] = useState<{ url_path: string; email: string } | null>(null);
  const [resetLinkCopied, setResetLinkCopied] = useState(false);
  const [generatingReset, setGeneratingReset] = useState<number | null>(null);

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
    setError(null);
    try {
      const [u, inv, events] = await Promise.all([
        api.listUsers(), api.listInvitations(), api.listLoginEvents(100),
      ]);
      setUsers(u);
      setInvitations(inv);
      setLoginEvents(events);
    } catch (e: any) {
      // Sans ceci, un échec de chargement afficherait le faux état vide
      // « Aucun compte pour l'instant », indistinguable d'une vraie liste vide.
      setError(e.message);
      toast.error(e.message);
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
      toast.success("Rôles enregistrés avec succès.");
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
      toast.success(`Compte ${updated.is_active ? "réactivé" : "suspendu"}.`);
    } catch (e: any) {
      toast.error(e.message);
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
      toast.success("Sessions révoquées.");
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setRevokingId(null);
    }
  }

  function openEdit(u: UserAccount) {
    setEditError(null);
    setEditUser(u);
    setEditName(u.display_name);
    setEditEmail(u.email);
  }
  function closeEdit() {
    setEditUser(null);
    setEditName("");
    setEditEmail("");
  }
  async function saveEdit() {
    if (!editUser) return;
    setSavingEdit(true);
    setEditError(null);
    try {
      const updated = await api.updateUser(editUser.id, {
        display_name: editName.trim() || undefined,
        email: editEmail.trim() || undefined,
      });
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? { ...u, ...updated } : u)));
      toast.success("Compte mis à jour avec succès.");
      closeEdit();
    } catch (e: any) {
      setEditError(e.message);
    } finally {
      setSavingEdit(false);
    }
  }

  async function generateResetLink(u: UserAccount) {
    setGeneratingReset(u.id);
    try {
      const result = await api.createResetLink(u.id);
      setResetLinkResult(result);
      setResetLinkCopied(false);
      toast.success("Lien de réinitialisation généré.");
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setGeneratingReset(null);
    }
  }

  async function copyResetLink() {
    if (!resetLinkResult) return;
    const fullUrl = `${window.location.origin}${resetLinkResult.url_path}`;
    try {
      await navigator.clipboard.writeText(fullUrl);
      setResetLinkCopied(true);
      setTimeout(() => setResetLinkCopied(false), 2000);
      toast.success("Lien copié dans le presse-papier !");
    } catch {
      toast.error("Impossible de copier le lien automatiquement.");
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
          <p className="text-sm text-[#8a8a8a] mt-1">Comptes, connexions et rôles par entité.</p>
        </div>
        <button onClick={openInvite} className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-full hover:bg-accent-sand transition-colors">
          <Plus size={15} /> Inviter
        </button>
      </div>

      {error && (
        <div className="mb-4 bg-[#1a0a0a] border border-alert/30 text-alert rounded-2xl p-4 text-sm flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)} className="text-alert/70 hover:text-alert"><X size={16} /></button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <PageLoader fullScreen={false} />
        </div>
      ) : users.length === 0 && !error ? (
        <EmptyState
          icon={Users}
          title="Aucun compte pour l'instant"
          description="Invite ton premier utilisateur pour lui donner accès à OpenFlow."
          ctaLabel="Inviter un utilisateur"
          onCta={openInvite}
        />
      ) : (
        <div className="bg-bg-card border border-border rounded-2xl overflow-hidden mb-10">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Email</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Nom</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Rôles</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Dernière connexion</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Statut</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u, idx) => {
                const isSelf = me?.id === u.id;
                return (
                  <tr key={u.id} className={idx > 0 ? "border-t border-[#1a1a1a]" : ""}>
                    <td className="px-5 py-3.5 font-medium text-white">{u.email}</td>
                    <td className="px-5 py-3.5 text-text-secondary">
                      {u.display_name || <span className="text-[#444]">Non renseigné</span>}
                    </td>
                    <td className="px-5 py-3.5">
                      {u.is_admin ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border border-accent-sand/40 bg-accent-sand/10 text-accent-sand">
                          <ShieldCheck size={12} /> Admin
                        </span>
                      ) : u.roles.length === 0 ? (
                        <span className="text-xs text-[#555]">Aucun rôle</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {u.roles.map((r) => (
                            <span key={r.entity_id} className="inline-block px-2 py-0.5 rounded-full text-xs border border-border-hover text-text-secondary">
                              {entityName(r.entity_id)} · {ROLE_LABELS[r.role]}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-text-secondary">{formatDateTime(u.last_login_at)}</td>
                    <td className="px-5 py-3.5">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-xs border ${
                        u.is_active
                          ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                          : "bg-alert/10 text-alert border-alert/30"
                      }`}>
                        {u.is_active ? "Actif" : "Désactivé"}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <div className="flex items-center justify-end gap-3 text-xs whitespace-nowrap">
                        <button onClick={() => openEdit(u)} className="font-medium text-accent-sand hover:text-[#e8b87a] transition-colors flex items-center gap-1">
                          <Pencil size={12} /> Modifier
                        </button>
                        {!u.is_admin && (
                          <button onClick={() => openRoles(u)} className="font-medium text-accent-sand hover:text-[#e8b87a] transition-colors flex items-center gap-1">
                            <Pencil size={12} /> Rôles
                          </button>
                        )}
                        <button
                          onClick={() => toggleActive(u)}
                          disabled={isSelf || (!!u.is_admin && !!u.is_active) || togglingId === u.id}
                          title={
                            isSelf
                              ? "Impossible de désactiver son propre compte"
                              : u.is_admin && u.is_active
                                ? "Impossible de désactiver un compte administrateur"
                                : undefined
                          }
                          className="font-medium text-text-secondary hover:text-white disabled:opacity-30 disabled:hover:text-text-secondary transition-colors"
                        >
                          {togglingId === u.id ? "..." : u.is_active ? "Désactiver" : "Réactiver"}
                        </button>
                        <button
                          onClick={() => revokeSessions(u)}
                          disabled={revokingId === u.id}
                          className="font-medium text-text-secondary hover:text-white disabled:opacity-30 transition-colors"
                        >
                          {revokedOkId === u.id ? "Déconnecté" : revokingId === u.id ? "..." : "Déconnecter partout"}
                        </button>
                        {!isSelf && (
                          <button
                            onClick={() => generateResetLink(u)}
                            disabled={generatingReset === u.id}
                            className="font-medium text-text-secondary hover:text-white disabled:opacity-30 transition-colors"
                          >
                            {generatingReset === u.id ? "..." : "Réinitialiser mdp"}
                          </button>
                        )}
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
        <p className="text-sm text-[#555] bg-bg-card border border-border rounded-2xl p-6 text-center">
          Aucune invitation en attente.
        </p>
      ) : !loading && (
        <div className="bg-bg-card border border-border rounded-2xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Email</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Rôle prévu</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Expire le</th>
                <th className="px-5 py-3.5 text-right text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {invitations.map((inv, idx) => (
                <tr key={inv.id} className={idx > 0 ? "border-t border-[#1a1a1a]" : ""}>
                  <td className="px-5 py-3.5 text-white">{inv.email}</td>
                  <td className="px-5 py-3.5 text-text-secondary">
                    {inv.is_admin
                      ? "Admin"
                      : inv.roles.length === 0
                        ? "Aucun rôle"
                        : inv.roles.map((r) => `${entityName(r.entity_id)} · ${ROLE_LABELS[r.role]}`).join(", ")}
                  </td>
                  <td className="px-5 py-3.5 text-text-secondary">{formatDateTime(inv.expires_at)}</td>
                  <td className="px-5 py-3.5 text-right">
                    {confirmDeleteInvite === inv.id ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="text-xs text-[#8a8a8a]">Supprimer ?</span>
                        <button onClick={() => handleDeleteInvitation(inv.id)} className="text-xs font-medium text-alert hover:text-red-400">Oui</button>
                        <button onClick={() => setConfirmDeleteInvite(null)} className="text-xs font-medium text-[#8a8a8a] hover:text-white">Non</button>
                      </span>
                    ) : (
                      <button onClick={() => setConfirmDeleteInvite(inv.id)} className="p-1.5 text-[#8a8a8a] hover:text-alert rounded-lg hover:bg-[#222] transition-colors" title="Supprimer">
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

      <div className="flex items-center justify-between mt-10 mb-4">
        <h2 className="text-lg font-semibold text-white">Journal des connexions</h2>
        {loginEvents.length > 0 && (
          <span className="text-xs text-[#555]">{loginEvents.length} dernières tentatives</span>
        )}
      </div>
      {!loading && loginEvents.length === 0 ? (
        <p className="text-sm text-[#555] bg-bg-card border border-border rounded-2xl p-6 text-center">
          Aucune tentative de connexion enregistrée pour l'instant.
        </p>
      ) : !loading && (
        <div className="bg-bg-card border border-border rounded-2xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Date</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Email</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Adresse IP</th>
                <th className="px-5 py-3.5 text-left text-xs font-medium text-[#8a8a8a] uppercase tracking-wider">Résultat</th>
              </tr>
            </thead>
            <tbody>
              {loginEvents.map((ev, idx) => (
                <tr key={ev.id} className={idx > 0 ? "border-t border-[#1a1a1a]" : ""}>
                  <td className="px-5 py-3.5 text-text-secondary whitespace-nowrap">{formatDateTime(ev.created_at)}</td>
                  <td className="px-5 py-3.5 text-white">{ev.email}</td>
                  <td className="px-5 py-3.5 text-text-secondary">{ev.ip || "Inconnue"}</td>
                  <td className="px-5 py-3.5">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs border ${
                      ev.success
                        ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                        : "bg-alert/10 text-alert border-alert/30"
                    }`}>
                      {ev.success ? "Réussie" : "Échouée"}
                    </span>
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
          <div className="w-full max-w-lg bg-bg-card border border-border rounded-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="border-b border-[#1a1a1a] px-6 py-4 flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-white">Modifier les rôles</h2>
                <p className="text-xs text-[#8a8a8a] mt-0.5">{rolesUser.email}</p>
              </div>
              <button onClick={closeRoles} className="text-[#8a8a8a] hover:text-white"><X size={18} /></button>
            </div>
            {rolesError && (
              <div className="mx-6 mt-4 bg-[#1a0a0a] border border-alert/30 text-alert rounded-xl p-3 text-sm">{rolesError}</div>
            )}
            <div className="px-6 py-6">
              <RolesEditor rows={rolesDraft} onChange={setRolesDraft} entities={flatEntities} />
            </div>
            <div className="px-6 pb-6 flex justify-end gap-3">
              <button type="button" onClick={closeRoles} className="px-5 py-2.5 text-sm font-semibold text-white border border-border-hover rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors">Annuler</button>
              <button type="button" onClick={saveRoles} disabled={savingRoles} className="px-5 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-full hover:bg-accent-sand disabled:opacity-50 transition-colors">
                {savingRoles ? "Enregistrement..." : "Enregistrer"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal : modifier nom et email */}
      {editUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => !savingEdit && closeEdit()}>
          <div className="w-full max-w-lg bg-bg-card border border-border rounded-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="border-b border-[#1a1a1a] px-6 py-4 flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-white">Modifier le compte</h2>
                <p className="text-xs text-[#8a8a8a] mt-0.5">{editUser.email}</p>
              </div>
              <button onClick={closeEdit} className="text-[#8a8a8a] hover:text-white"><X size={18} /></button>
            </div>
            {editError && (
              <div className="mx-6 mt-4 bg-[#1a0a0a] border border-alert/30 text-alert rounded-xl p-3 text-sm">{editError}</div>
            )}
            <div className="px-6 py-6 space-y-4">
              <div>
                <label className={labelClass}>Nom d'affichage</label>
                <input
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className={inputClass}
                  placeholder="Prénom Nom"
                />
              </div>
              <div>
                <label className={labelClass}>Email</label>
                <input
                  type="email"
                  value={editEmail}
                  onChange={(e) => setEditEmail(e.target.value)}
                  className={inputClass}
                  placeholder="email@exemple.fr"
                />
              </div>
            </div>
            <div className="px-6 pb-6 flex justify-end gap-3">
              <button type="button" onClick={closeEdit} className="px-5 py-2.5 text-sm font-semibold text-white border border-border-hover rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors">Annuler</button>
              <button type="button" onClick={saveEdit} disabled={savingEdit} className="px-5 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-full hover:bg-accent-sand disabled:opacity-50 transition-colors">
                {savingEdit ? "Enregistrement..." : "Enregistrer"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal : lien de réinitialisation */}
      {resetLinkResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setResetLinkResult(null)}>
          <div className="w-full max-w-lg bg-bg-card border border-border rounded-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="border-b border-[#1a1a1a] px-6 py-4 flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-white">Lien de réinitialisation</h2>
                <p className="text-xs text-[#8a8a8a] mt-0.5">Pour {resetLinkResult.email}</p>
              </div>
              <button onClick={() => setResetLinkResult(null)} className="text-[#8a8a8a] hover:text-white"><X size={18} /></button>
            </div>
            <div className="px-6 py-6 space-y-4">
              <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-xl p-4">
                <p className="text-sm text-emerald-300">
                  Lien généré ! Transmets-le à <span className="font-semibold">{resetLinkResult.email}</span> pour qu'il puisse choisir un nouveau mot de passe.
                </p>
              </div>
              <div>
                <label className={labelClass}>Lien de réinitialisation</label>
                <div className="flex items-center gap-2">
                  <input
                    readOnly
                    value={`${window.location.origin}${resetLinkResult.url_path}`}
                    onFocus={(e) => e.target.select()}
                    className={`${inputClass} text-xs`}
                  />
                  <button
                    type="button"
                    onClick={copyResetLink}
                    className="flex-shrink-0 flex items-center gap-1.5 px-4 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-xl hover:bg-accent-sand transition-colors"
                  >
                    {resetLinkCopied ? <><Check size={14} /> Copié</> : <><Copy size={14} /> Copier</>}
                  </button>
                </div>
                <p className="text-xs text-alert mt-2">
                  Ce lien ne sera affiché qu'une seule fois. Il expire dans 72 h.
                </p>
              </div>
              <div className="flex justify-end pt-2">
                <button type="button" onClick={() => setResetLinkResult(null)} className="px-5 py-2.5 text-sm font-semibold text-white border border-border-hover rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors">
                  Fermer
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal : inviter un utilisateur */}
      {showInvite && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => !inviting && closeInvite()}>
          <div className="w-full max-w-lg bg-bg-card border border-border rounded-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="border-b border-[#1a1a1a] px-6 py-4 flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-white">Inviter un utilisateur</h2>
                <p className="text-xs text-[#8a8a8a] mt-0.5">Génère un lien d'invitation à usage unique.</p>
              </div>
              <button onClick={closeInvite} className="text-[#8a8a8a] hover:text-white"><X size={18} /></button>
            </div>

            {inviteError && (
              <div className="mx-6 mt-4 bg-[#1a0a0a] border border-alert/30 text-alert rounded-xl p-3 text-sm">{inviteError}</div>
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
                      className="flex-shrink-0 flex items-center gap-1.5 px-4 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-xl hover:bg-accent-sand transition-colors"
                    >
                      {linkCopied ? <><Check size={14} /> Lien copié</> : <><Copy size={14} /> Copier le lien</>}
                    </button>
                  </div>
                  <p className="text-xs text-alert mt-2">
                    Ce lien ne sera affiché qu'une seule fois : note-le ou transmets-le maintenant.
                  </p>
                </div>
                <div className="flex justify-end pt-2">
                  <button type="button" onClick={closeInvite} className="px-5 py-2.5 text-sm font-semibold text-white border border-border-hover rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors">
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
                  <p className="text-xs text-[#8a8a8a] mt-1.5">Un administrateur a accès à toutes les entités et à toutes les fonctionnalités.</p>
                </div>
                {!inviteIsAdmin && (
                  <div>
                    <label className={labelClass}>Rôles</label>
                    <RolesEditor rows={inviteRoles} onChange={setInviteRoles} entities={flatEntities} />
                  </div>
                )}
                <div className="flex justify-end gap-3 pt-2">
                  <button type="button" onClick={closeInvite} className="px-5 py-2.5 text-sm font-semibold text-white border border-border-hover rounded-full hover:border-[#444] hover:bg-[#1a1a1a] transition-colors">
                    Annuler
                  </button>
                  <button type="submit" disabled={inviting} className="px-5 py-2.5 text-sm font-semibold text-black bg-accent-sand rounded-full hover:bg-accent-sand disabled:opacity-50 transition-colors">
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
