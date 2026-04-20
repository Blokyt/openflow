import { useEffect, useState } from "react";
import { MessageSquare, Plus, Trash2 } from "lucide-react";

interface Annotation {
  id: number;
  transaction_id: number;
  content: string;
  created_at: string;
}

export default function AnnotationsSection({ txId }: { txId: number }) {
  const [items, setItems] = useState<Annotation[]>([]);
  const [loading, setLoading] = useState(true);
  const [newContent, setNewContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function fetchItems() {
    setLoading(true);
    try {
      const res = await fetch(`/api/annotations/transaction/${txId}`);
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
      setItems(await res.json());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchItems();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [txId]);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!newContent.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`/api/annotations/transaction/${txId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: newContent }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
      setNewContent("");
      await fetchItems();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number) {
    try {
      const res = await fetch(`/api/annotations/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
      await fetchItems();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <div className="border-t border-[#1a1a1a] pt-4">
      <h3 className="text-sm font-semibold text-white flex items-center gap-2 mb-3">
        <MessageSquare size={14} className="text-[#F2C48D]" />
        Notes {items.length > 0 && <span className="text-[#666] text-xs">({items.length})</span>}
      </h3>

      <form onSubmit={handleAdd} className="mb-3 flex gap-2">
        <input
          type="text"
          value={newContent}
          onChange={(e) => setNewContent(e.target.value)}
          placeholder="Ajouter une note…"
          className="flex-1 bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-[#F2C48D] transition-colors placeholder-[#444]"
        />
        <button
          type="submit"
          disabled={saving || !newContent.trim()}
          className="px-3 py-2 text-xs font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-50 transition-colors flex items-center gap-1"
        >
          <Plus size={12} /> {saving ? "…" : "Ajouter"}
        </button>
      </form>

      {error && (
        <div className="mb-3 text-xs text-[#FF5252] bg-[#1a0a0a] border border-[#FF5252]/30 rounded-lg p-2">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-xs text-[#666] py-2">Chargement…</div>
      ) : items.length === 0 ? (
        <div className="text-xs text-[#666] py-2">Aucune note.</div>
      ) : (
        <div className="space-y-2">
          {items.map((a) => (
            <div key={a.id} className="bg-[#111] border border-[#222] rounded-xl p-3 flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="text-sm text-white whitespace-pre-wrap break-words">{a.content}</div>
                <div className="text-xs text-[#555] mt-1">
                  {new Date(a.created_at).toLocaleString("fr-FR")}
                </div>
              </div>
              <button
                onClick={() => handleDelete(a.id)}
                className="p-1.5 text-[#666] hover:text-[#FF5252] rounded-lg hover:bg-[#222] transition-colors flex-shrink-0"
                title="Supprimer"
              >
                <Trash2 size={13} strokeWidth={1.5} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
