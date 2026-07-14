import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FileUp, Paperclip, X } from "lucide-react";
import { api } from "../../api";
import { useAuth } from "../../core/AuthContext";
import ContactCombobox from "../../core/ContactCombobox";
import ConfirmDialog from "../../core/ConfirmDialog";
import { formatEuros } from "../../utils/format";
import { notifyBadgesChanged } from "../../utils/events";

// Libellés français des statuts (design system : chips fond couleur+"20").
export const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  pending: { label: "En attente", color: "#F2C48D" },
  approved: { label: "Approuvée", color: "#00C853" },
  rejected: { label: "Refusée", color: "#FF5252" },
  cancelled: { label: "Annulée", color: "#B0B0B0" },
};

export function StatusChip({ status }: { status: string }) {
  const s = STATUS_LABELS[status] ?? { label: status, color: "#B0B0B0" };
  return (
    <span
      className="text-xs font-medium rounded-full px-2.5 py-0.5"
      style={{ backgroundColor: s.color + "20", color: s.color }}
    >
      {s.label}
    </span>
  );
}

// Aplatis l'arbre interne en gardant seulement les sous-arbres où le user est
// treasurer (l'admin voit tout). L'arbre renvoyé par /entities/tree est déjà
// scopé au périmètre global du user ; on restreint ici aux racines treasurer.
function flattenTreasurerEntities(tree: any[], treasurerRoots: Set<number>, isAdmin: boolean): any[] {
  const out: any[] = [];
  function walk(nodes: any[], depth: number, inScope: boolean) {
    for (const n of nodes) {
      const scoped = isAdmin || inScope || treasurerRoots.has(n.id);
      if (scoped) out.push({ ...n, depth });
      walk(n.children ?? [], scoped ? depth + 1 : depth, scoped);
    }
  }
  walk(tree, 0, false);
  return out;
}

function SubmissionForm({ onCreated }: { onCreated: () => void }) {
  const { user, isAdmin } = useAuth();
  const [entities, setEntities] = useState<any[]>([]);
  const [externals, setExternals] = useState<any[]>([]);
  const [categories, setCategories] = useState<any[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [payerContactId, setPayerContactId] = useState<string>("");
  const [payerName, setPayerName] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    date: new Date().toISOString().slice(0, 10),
    label: "",
    description: "",
    amount: "",
    category_id: "",
    entity_id: "",
    counterparty_entity_id: "",
    direction: "expense",
  });

  const treasurerRoots = useMemo(
    () => new Set((user?.roles ?? []).filter((r) => r.role === "treasurer").map((r) => r.entity_id)),
    [user],
  );

  useEffect(() => {
    api.getEntityTree().then((tree) => {
      const flat = flattenTreasurerEntities(tree, treasurerRoots, isAdmin);
      setEntities(flat);
      if (flat.length === 1) setForm((f) => ({ ...f, entity_id: String(flat[0].id) }));
    }).catch(() => {});
    api.getEntities("external").then(setExternals).catch(() => {});
    api.getCategories().then(setCategories).catch(() => {});
  }, [treasurerRoots, isAdmin]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const cents = Math.round(parseFloat(form.amount.replace(",", ".")) * 100);
    if (!Number.isFinite(cents) || cents <= 0) {
      setError("Le montant doit être un nombre strictement positif.");
      return;
    }
    setSaving(true);
    try {
      const created = await api.createSubmission({
        date: form.date,
        label: form.label,
        description: form.description,
        amount: cents,
        category_id: form.category_id ? Number(form.category_id) : null,
        entity_id: Number(form.entity_id),
        counterparty_entity_id: Number(form.counterparty_entity_id),
        direction: form.direction,
        payer_contact_id: payerContactId ? Number(payerContactId) : null,
      });
      for (const file of files) {
        await api.uploadSubmissionAttachment(created.id, file);
      }
      setForm((f) => ({ ...f, label: "", description: "", amount: "" }));
      setFiles([]);
      setPayerContactId("");
      setPayerName(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      notifyBadgesChanged();
      onCreated();
    } catch (err: any) {
      setError(err?.message || "Erreur lors de la soumission.");
    } finally {
      setSaving(false);
    }
  }

  const inputCls =
    "w-full bg-[#0a0a0a] border border-border rounded-xl px-3 py-2 text-sm text-white " +
    "focus:border-accent-sand focus:outline-none [color-scheme:dark]";

  return (
    <form onSubmit={submit} className="bg-bg-card border border-border rounded-2xl p-6 space-y-4">
      <h2 className="text-sm font-semibold text-white">Soumettre une dépense ou une recette</h2>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs uppercase tracking-wider text-[#8a8a8a]">Sens</label>
          <select className={inputCls} value={form.direction}
            onChange={(e) => setForm({ ...form, direction: e.target.value })}>
            <option value="expense">Dépense</option>
            <option value="income">Recette</option>
          </select>
        </div>
        <div>
          <label className="text-xs uppercase tracking-wider text-[#8a8a8a]">Date</label>
          <input type="date" required className={inputCls} value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })} />
        </div>
      </div>
      <div>
        <label className="text-xs uppercase tracking-wider text-[#8a8a8a]">Libellé</label>
        <input required maxLength={200} className={inputCls} value={form.label}
          placeholder="Ex : courses pour l'atelier cuisine"
          onChange={(e) => setForm({ ...form, label: e.target.value })} />
      </div>
      <div>
        <label className="text-xs uppercase tracking-wider text-[#8a8a8a]">Description (facultatif)</label>
        <textarea rows={2} className={inputCls} value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs uppercase tracking-wider text-[#8a8a8a]">Montant (€)</label>
          <input required inputMode="decimal" placeholder="45,50" className={inputCls} value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })} />
        </div>
        <div>
          <label className="text-xs uppercase tracking-wider text-[#8a8a8a]">Catégorie</label>
          <select className={inputCls} value={form.category_id}
            onChange={(e) => setForm({ ...form, category_id: e.target.value })}>
            <option value="">Aucune</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs uppercase tracking-wider text-[#8a8a8a]">Entité</label>
          <select required className={inputCls} value={form.entity_id}
            onChange={(e) => setForm({ ...form, entity_id: e.target.value })}>
            <option value="">Choisir…</option>
            {entities.map((en) => (
              <option key={en.id} value={en.id}>{" ".repeat(en.depth * 2)}{en.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs uppercase tracking-wider text-[#8a8a8a]">Contrepartie (tiers)</label>
          <select required className={inputCls} value={form.counterparty_entity_id}
            onChange={(e) => setForm({ ...form, counterparty_entity_id: e.target.value })}>
            <option value="">Choisir…</option>
            {externals.map((ex) => <option key={ex.id} value={ex.id}>{ex.name}</option>)}
          </select>
        </div>
      </div>
      <div>
        <label className="text-xs uppercase tracking-wider text-[#8a8a8a]">Avance de frais (payée par)</label>
        <ContactCombobox
          value={payerContactId}
          selectedName={payerName}
          onChange={setPayerContactId}
          onPick={(c) => setPayerName(c.name)}
          placeholder="Rechercher un membre..."
          allowCreate={isAdmin}
        />
        <p className="mt-1 text-xs text-[#8a8a8a]">
          Si un membre a avancé l'argent, sélectionne-le : la fiche de remboursement
          sera créée automatiquement à l'approbation.
        </p>
      </div>
      <div>
        <label className="text-xs uppercase tracking-wider text-[#8a8a8a]">Justificatifs (PDF, images)</label>
        <input type="file" multiple accept=".pdf,image/*" ref={fileInputRef}
          className="block w-full text-sm text-text-secondary file:mr-3 file:rounded-full file:border-0 file:bg-[#222] file:px-3 file:py-1.5 file:text-sm file:text-white"
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
        {files.length > 0 && (
          <p className="mt-1 text-xs text-[#8a8a8a]">{files.length} fichier(s) sélectionné(s)</p>
        )}
      </div>
      {error && <p className="text-sm text-alert">{error}</p>}
      <button type="submit" disabled={saving}
        className="rounded-full bg-accent-sand px-5 py-2 text-sm font-semibold text-black hover:bg-accent-sand transition-colors disabled:opacity-50">
        {saving ? "Envoi…" : "Soumettre"}
      </button>
    </form>
  );
}

function AttachmentLinks({ submissionId }: { submissionId: number }) {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => {
    api.listSubmissionAttachments(submissionId).then(setItems).catch(() => {});
  }, [submissionId]);
  if (items.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2 mt-1">
      {items.map((a) => (
        <a key={a.id} href={`/api/attachments/${a.id}/preview`} target="_blank" rel="noreferrer"
          className="inline-flex items-center gap-1 text-xs text-text-secondary hover:text-white">
          <Paperclip size={12} /> {a.original_name}
        </a>
      ))}
    </div>
  );
}

function MySubmissions({ refreshKey }: { refreshKey: number }) {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cancelingId, setCancelingId] = useState<number | null>(null);
  const [confirmCancel, setConfirmCancel] = useState<number | null>(null);

  const load = useCallback(() => {
    api.getMySubmissions().then(setItems).catch(() => {}).finally(() => setLoading(false));
  }, []);
  useEffect(load, [load, refreshKey]);

  async function cancel(id: number) {
    setError(null);
    setCancelingId(id);
    try {
      await api.cancelSubmission(id);
      setConfirmCancel(null);
      notifyBadgesChanged();
      load();
    } catch (err: any) {
      setError(err?.message || "Erreur lors de l'annulation.");
    } finally {
      setCancelingId(null);
    }
  }

  if (loading) return null;
  if (items.length === 0) {
    return (
      <p className="text-sm text-[#8a8a8a]">
        Aucune soumission pour l'instant. Votre première demande apparaîtra ici avec son statut.
      </p>
    );
  }
  const cancelTarget = items.find((s) => s.id === confirmCancel);
  return (
    <div className="space-y-2">
      {error && <p className="text-sm text-alert">{error}</p>}
      <div className="bg-bg-card border border-border rounded-2xl overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs uppercase tracking-wider text-[#8a8a8a] text-left">
            <th className="px-4 py-3">Date</th>
            <th className="px-4 py-3">Libellé</th>
            <th className="px-4 py-3">Entité</th>
            <th className="px-4 py-3 text-right">Montant</th>
            <th className="px-4 py-3">Statut</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr key={s.id} className="border-t border-[#1a1a1a] hover:bg-[#1a1a1a]">
              <td className="px-4 py-3 text-text-secondary">{s.date}</td>
              <td className="px-4 py-3 text-white">
                {s.label}
                <AttachmentLinks submissionId={s.id} />
                {s.payer_name && (
                  <p className="text-xs text-accent-sand mt-1">Avance de frais : {s.payer_name}</p>
                )}
                {s.status === "rejected" && s.review_comment && (
                  <p className="text-xs text-alert mt-1">Motif du refus : {s.review_comment}</p>
                )}
              </td>
              <td className="px-4 py-3 text-text-secondary">{s.entity_name}</td>
              <td className="px-4 py-3 text-right font-semibold"
                style={{ color: s.direction === "income" ? "#00C853" : "#FF5252" }}>
                {formatEuros(s.amount)}
              </td>
              <td className="px-4 py-3"><StatusChip status={s.status} /></td>
              <td className="px-4 py-3 text-right">
                {s.status === "pending" && (
                  <button onClick={() => setConfirmCancel(s.id)} title="Annuler cette soumission"
                    className="text-[#8a8a8a] hover:text-white transition-colors">
                    <X size={15} />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <ConfirmDialog
        open={confirmCancel !== null}
        title="Annuler la soumission"
        message={cancelTarget ? <>Annuler la soumission « {cancelTarget.label} » ?</> : "Annuler cette soumission ?"}
        confirmLabel="Oui, annuler"
        cancelLabel="Non"
        danger
        busy={cancelingId === confirmCancel}
        onConfirm={() => confirmCancel !== null && cancel(confirmCancel)}
        onCancel={() => setConfirmCancel(null)}
      />
    </div>
  );
}

function AdminQueue() {
  const [tab, setTab] = useState<"pending" | "all">("pending");
  const [items, setItems] = useState<any[]>([]);
  const [rejectingId, setRejectingId] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [forceApproveId, setForceApproveId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    const p = tab === "pending" ? api.getSubmissions("pending") : api.getSubmissions();
    p.then(setItems).catch(() => {});
  }, [tab]);
  useEffect(load, [load]);

  async function forceApprove() {
    if (forceApproveId === null) return;
    setBusy(true);
    setError(null);
    try {
      await api.approveSubmission(forceApproveId, true);
      setForceApproveId(null);
      notifyBadgesChanged();
      load();
    } catch (err: any) {
      setError(err?.message || "Erreur lors de l'approbation forcée.");
    } finally {
      setBusy(false);
    }
  }

  async function approve(id: number) {
    setError(null);
    try {
      await api.approveSubmission(id);
    } catch (err: any) {
      // Verrou d'exercice clôturé : on propose de forcer.
      if (String(err?.message || "").includes("Exercice clôturé")) {
        setForceApproveId(id);
        return;
      } else {
        setError(err?.message || "Erreur lors de l'approbation.");
        return;
      }
    }
    notifyBadgesChanged();
    load();
  }

  async function reject(id: number) {
    setError(null);
    try {
      await api.rejectSubmission(id, comment);
      setRejectingId(null);
      setComment("");
      notifyBadgesChanged();
      load();
    } catch (err: any) {
      setError(err?.message || "Erreur lors du refus.");
    }
  }

  const tabCls = (active: boolean) =>
    `px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
      active ? "bg-accent-sand text-black" : "text-[#8a8a8a] hover:text-white"
    }`;

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <button className={tabCls(tab === "pending")} onClick={() => setTab("pending")}>
          File de validation
        </button>
        <button className={tabCls(tab === "all")} onClick={() => setTab("all")}>
          Historique
        </button>
      </div>
      {error && <p className="text-sm text-alert">{error}</p>}
      {items.length === 0 ? (
        <p className="text-sm text-[#8a8a8a]">
          {tab === "pending"
            ? "Aucune soumission en attente de validation."
            : "Aucune soumission enregistrée."}
        </p>
      ) : (
        <div className="space-y-3">
          {items.map((s) => (
            <div key={s.id} className="bg-bg-card border border-border rounded-2xl p-5 space-y-2">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-white font-medium">{s.label}</p>
                  <p className="text-xs text-[#8a8a8a]">
                    {s.date} · {s.entity_name} → {s.counterparty_name}
                    {s.category_name ? ` · ${s.category_name}` : ""} · par {s.submitted_by_name || s.submitted_by_email}
                  </p>
                  {s.payer_name && (
                    <p className="text-xs text-accent-sand mt-1">
                      Avance de frais : {s.payer_name} (fiche de remboursement créée à l'approbation)
                    </p>
                  )}
                  {s.description && <p className="text-sm text-text-secondary mt-1">{s.description}</p>}
                  <AttachmentLinks submissionId={s.id} />
                  {s.status === "rejected" && s.review_comment && (
                    <p className="text-xs text-alert mt-1">Motif du refus : {s.review_comment}</p>
                  )}
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="font-semibold"
                    style={{ color: s.direction === "income" ? "#00C853" : "#FF5252" }}>
                    {s.direction === "income" ? "+" : "-"}{formatEuros(s.amount)}
                  </p>
                  <div className="mt-1"><StatusChip status={s.status} /></div>
                </div>
              </div>
              {s.status === "pending" && (
                rejectingId === s.id ? (
                  <div className="flex items-center gap-2 pt-1">
                    <input autoFocus value={comment} placeholder="Motif du refus (obligatoire)"
                      className="flex-1 bg-[#0a0a0a] border border-border rounded-xl px-3 py-2 text-sm text-white focus:border-accent-sand focus:outline-none"
                      onChange={(e) => setComment(e.target.value)} />
                    <button onClick={() => reject(s.id)} disabled={!comment.trim()}
                      className="rounded-full bg-alert px-4 py-2 text-sm font-semibold text-black disabled:opacity-40">
                      Refuser
                    </button>
                    <button onClick={() => { setRejectingId(null); setComment(""); }}
                      className="text-sm text-[#8a8a8a] hover:text-white">
                      Annuler
                    </button>
                  </div>
                ) : (
                  <div className="flex gap-2 pt-1">
                    <button onClick={() => approve(s.id)}
                      className="rounded-full bg-accent-sand px-4 py-2 text-sm font-semibold text-black hover:bg-accent-sand transition-colors">
                      Approuver
                    </button>
                    <button onClick={() => setRejectingId(s.id)}
                      className="rounded-full border border-border-hover px-4 py-2 text-sm text-white hover:border-[#555] transition-colors">
                      Refuser…
                    </button>
                  </div>
                )
              )}
            </div>
          ))}
        </div>
      )}
      <ConfirmDialog
        open={forceApproveId !== null}
        title="Approbation sur exercice clôturé"
        message="L'exercice fiscal lié à cette soumission est clôturé. Voulez-vous vraiment l'approuver et générer des transactions dans un exercice fermé ?"
        confirmLabel="Forcer l'approbation"
        danger={true}
        busy={busy}
        onConfirm={forceApprove}
        onCancel={() => setForceApproveId(null)}
      />
    </div>
  );
}

export default function SubmissionsPage() {
  const { user, isAdmin } = useAuth();
  const [refreshKey, setRefreshKey] = useState(0);
  const hasTreasurerRole = (user?.roles ?? []).some((r) => r.role === "treasurer");

  return (
    <div className="p-8 max-w-4xl space-y-6">
      <div className="flex items-center gap-3">
        <FileUp size={22} className="text-accent-sand" strokeWidth={1.5} />
        <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
          Soumissions
        </h1>
      </div>
      {isAdmin ? (
        <AdminQueue />
      ) : (
        <>
          {hasTreasurerRole ? (
            <SubmissionForm onCreated={() => setRefreshKey((k) => k + 1)} />
          ) : (
            <div className="bg-bg-card border border-border rounded-2xl p-6 text-sm text-[#8a8a8a]">
              Vous n'êtes trésorier d'aucune entité. Vous ne pouvez pas créer de soumission.
              Contactez un administrateur si cela vous semble incorrect.
            </div>
          )}
          <div className="space-y-2">
            <h2 className="text-xs uppercase tracking-wider text-[#8a8a8a]">Mes soumissions</h2>
            <MySubmissions refreshKey={refreshKey} />
          </div>
        </>
      )}
    </div>
  );
}
