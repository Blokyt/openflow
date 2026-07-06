import { useCallback, useEffect, useMemo, useState } from "react";
import { FileUp, Paperclip, X } from "lucide-react";
import { api } from "../../api";
import { useAuth } from "../../core/AuthContext";
import { formatEuros } from "../../utils/format";

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
      });
      for (const file of files) {
        await api.uploadSubmissionAttachment(created.id, file);
      }
      setForm((f) => ({ ...f, label: "", description: "", amount: "" }));
      setFiles([]);
      onCreated();
    } catch (err: any) {
      setError(err?.message || "Erreur lors de la soumission.");
    } finally {
      setSaving(false);
    }
  }

  const inputCls =
    "w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2 text-sm text-white " +
    "focus:border-[#F2C48D] focus:outline-none [color-scheme:dark]";

  return (
    <form onSubmit={submit} className="bg-[#111] border border-[#222] rounded-2xl p-6 space-y-4">
      <h2 className="text-sm font-semibold text-white">Soumettre une dépense ou une recette</h2>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs uppercase tracking-wider text-[#666]">Sens</label>
          <select className={inputCls} value={form.direction}
            onChange={(e) => setForm({ ...form, direction: e.target.value })}>
            <option value="expense">Dépense</option>
            <option value="income">Recette</option>
          </select>
        </div>
        <div>
          <label className="text-xs uppercase tracking-wider text-[#666]">Date</label>
          <input type="date" required className={inputCls} value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })} />
        </div>
      </div>
      <div>
        <label className="text-xs uppercase tracking-wider text-[#666]">Libellé</label>
        <input required maxLength={200} className={inputCls} value={form.label}
          placeholder="Ex : courses pour l'atelier cuisine"
          onChange={(e) => setForm({ ...form, label: e.target.value })} />
      </div>
      <div>
        <label className="text-xs uppercase tracking-wider text-[#666]">Description (facultatif)</label>
        <textarea rows={2} className={inputCls} value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs uppercase tracking-wider text-[#666]">Montant (€)</label>
          <input required inputMode="decimal" placeholder="45,50" className={inputCls} value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })} />
        </div>
        <div>
          <label className="text-xs uppercase tracking-wider text-[#666]">Catégorie</label>
          <select className={inputCls} value={form.category_id}
            onChange={(e) => setForm({ ...form, category_id: e.target.value })}>
            <option value="">Aucune</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs uppercase tracking-wider text-[#666]">Entité</label>
          <select required className={inputCls} value={form.entity_id}
            onChange={(e) => setForm({ ...form, entity_id: e.target.value })}>
            <option value="">Choisir…</option>
            {entities.map((en) => (
              <option key={en.id} value={en.id}>{" ".repeat(en.depth * 2)}{en.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs uppercase tracking-wider text-[#666]">Contrepartie (tiers)</label>
          <select required className={inputCls} value={form.counterparty_entity_id}
            onChange={(e) => setForm({ ...form, counterparty_entity_id: e.target.value })}>
            <option value="">Choisir…</option>
            {externals.map((ex) => <option key={ex.id} value={ex.id}>{ex.name}</option>)}
          </select>
        </div>
      </div>
      <div>
        <label className="text-xs uppercase tracking-wider text-[#666]">Justificatifs (PDF, images)</label>
        <input type="file" multiple accept=".pdf,image/*"
          className="block w-full text-sm text-[#B0B0B0] file:mr-3 file:rounded-full file:border-0 file:bg-[#222] file:px-3 file:py-1.5 file:text-sm file:text-white"
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
        {files.length > 0 && (
          <p className="mt-1 text-xs text-[#666]">{files.length} fichier(s) sélectionné(s)</p>
        )}
      </div>
      {error && <p className="text-sm text-[#FF5252]">{error}</p>}
      <button type="submit" disabled={saving}
        className="rounded-full bg-[#F2C48D] px-5 py-2 text-sm font-semibold text-black hover:bg-[#e8b87a] transition-colors disabled:opacity-50">
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
          className="inline-flex items-center gap-1 text-xs text-[#B0B0B0] hover:text-white">
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

  const load = useCallback(() => {
    api.getMySubmissions().then(setItems).catch(() => {}).finally(() => setLoading(false));
  }, []);
  useEffect(load, [load, refreshKey]);

  async function cancel(id: number) {
    setError(null);
    try {
      await api.cancelSubmission(id);
      load();
    } catch (err: any) {
      setError(err?.message || "Erreur lors de l'annulation.");
    }
  }

  if (loading) return null;
  if (items.length === 0) {
    return (
      <p className="text-sm text-[#666]">
        Aucune soumission pour l'instant. Votre première demande apparaîtra ici avec son statut.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      {error && <p className="text-sm text-[#FF5252]">{error}</p>}
      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs uppercase tracking-wider text-[#666] text-left">
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
              <td className="px-4 py-3 text-[#B0B0B0]">{s.date}</td>
              <td className="px-4 py-3 text-white">
                {s.label}
                <AttachmentLinks submissionId={s.id} />
                {s.status === "rejected" && s.review_comment && (
                  <p className="text-xs text-[#FF5252] mt-1">Motif du refus : {s.review_comment}</p>
                )}
              </td>
              <td className="px-4 py-3 text-[#B0B0B0]">{s.entity_name}</td>
              <td className="px-4 py-3 text-right font-semibold"
                style={{ color: s.direction === "income" ? "#00C853" : "#FF5252" }}>
                {formatEuros(s.amount)}
              </td>
              <td className="px-4 py-3"><StatusChip status={s.status} /></td>
              <td className="px-4 py-3 text-right">
                {s.status === "pending" && (
                  <button onClick={() => cancel(s.id)} title="Annuler cette soumission"
                    className="text-[#666] hover:text-white transition-colors">
                    <X size={15} />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
}

function AdminQueue() {
  const [tab, setTab] = useState<"pending" | "all">("pending");
  const [items, setItems] = useState<any[]>([]);
  const [rejectingId, setRejectingId] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    const p = tab === "pending" ? api.getSubmissions("pending") : api.getSubmissions();
    p.then(setItems).catch(() => {});
  }, [tab]);
  useEffect(load, [load]);

  async function approve(id: number) {
    setError(null);
    try {
      await api.approveSubmission(id);
    } catch (err: any) {
      // Verrou d'exercice clôturé : on propose de forcer.
      if (String(err?.message || "").includes("Exercice clôturé")) {
        if (!window.confirm("Exercice clôturé : approuver quand même ?")) return;
        try {
          await api.approveSubmission(id, true);
        } catch (err2: any) {
          setError(err2?.message || "Erreur lors de l'approbation forcée.");
          return;
        }
      } else {
        setError(err?.message || "Erreur lors de l'approbation.");
        return;
      }
    }
    load();
  }

  async function reject(id: number) {
    setError(null);
    try {
      await api.rejectSubmission(id, comment);
      setRejectingId(null);
      setComment("");
      load();
    } catch (err: any) {
      setError(err?.message || "Erreur lors du refus.");
    }
  }

  const tabCls = (active: boolean) =>
    `px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
      active ? "bg-[#F2C48D] text-black" : "text-[#666] hover:text-white"
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
      {error && <p className="text-sm text-[#FF5252]">{error}</p>}
      {items.length === 0 ? (
        <p className="text-sm text-[#666]">
          {tab === "pending"
            ? "Aucune soumission en attente de validation."
            : "Aucune soumission enregistrée."}
        </p>
      ) : (
        <div className="space-y-3">
          {items.map((s) => (
            <div key={s.id} className="bg-[#111] border border-[#222] rounded-2xl p-5 space-y-2">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-white font-medium">{s.label}</p>
                  <p className="text-xs text-[#666]">
                    {s.date} · {s.entity_name} → {s.counterparty_name}
                    {s.category_name ? ` · ${s.category_name}` : ""} · par {s.submitted_by_name || s.submitted_by_email}
                  </p>
                  {s.description && <p className="text-sm text-[#B0B0B0] mt-1">{s.description}</p>}
                  <AttachmentLinks submissionId={s.id} />
                  {s.status === "rejected" && s.review_comment && (
                    <p className="text-xs text-[#FF5252] mt-1">Motif du refus : {s.review_comment}</p>
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
                      className="flex-1 bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2 text-sm text-white focus:border-[#F2C48D] focus:outline-none"
                      onChange={(e) => setComment(e.target.value)} />
                    <button onClick={() => reject(s.id)} disabled={!comment.trim()}
                      className="rounded-full bg-[#FF5252] px-4 py-2 text-sm font-semibold text-black disabled:opacity-40">
                      Refuser
                    </button>
                    <button onClick={() => { setRejectingId(null); setComment(""); }}
                      className="text-sm text-[#666] hover:text-white">
                      Annuler
                    </button>
                  </div>
                ) : (
                  <div className="flex gap-2 pt-1">
                    <button onClick={() => approve(s.id)}
                      className="rounded-full bg-[#F2C48D] px-4 py-2 text-sm font-semibold text-black hover:bg-[#e8b87a] transition-colors">
                      Approuver
                    </button>
                    <button onClick={() => setRejectingId(s.id)}
                      className="rounded-full border border-[#333] px-4 py-2 text-sm text-white hover:border-[#555] transition-colors">
                      Refuser…
                    </button>
                  </div>
                )
              )}
            </div>
          ))}
        </div>
      )}
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
        <FileUp size={22} className="text-[#F2C48D]" strokeWidth={1.5} />
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
            <div className="bg-[#111] border border-[#222] rounded-2xl p-6 text-sm text-[#666]">
              Vous n'êtes trésorier d'aucune entité. Vous ne pouvez pas créer de soumission.
              Contactez un administrateur si cela vous semble incorrect.
            </div>
          )}
          <div className="space-y-2">
            <h2 className="text-xs uppercase tracking-wider text-[#666]">Mes soumissions</h2>
            <MySubmissions refreshKey={refreshKey} />
          </div>
        </>
      )}
    </div>
  );
}
