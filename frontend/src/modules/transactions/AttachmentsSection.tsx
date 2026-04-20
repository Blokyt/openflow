import { useEffect, useState, useRef } from "react";
import { Paperclip, Download, Trash2, Upload } from "lucide-react";

interface Attachment {
  id: number;
  transaction_id: number;
  filename: string;
  original_name: string;
  mime_type: string;
  size: number;
  created_at: string;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function AttachmentsSection({ txId }: { txId: number }) {
  const [items, setItems] = useState<Attachment[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  async function fetchItems() {
    setLoading(true);
    try {
      const res = await fetch(`/api/attachments/transaction/${txId}`);
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

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`/api/attachments/transaction/${txId}`, { method: "POST", body: fd });
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
      await fetchItems();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function handleDelete(id: number) {
    if (!confirm("Supprimer cette pièce jointe ?")) return;
    try {
      const res = await fetch(`/api/attachments/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
      await fetchItems();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <div className="border-t border-[#1a1a1a] pt-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          <Paperclip size={14} className="text-[#F2C48D]" />
          Pièces jointes {items.length > 0 && <span className="text-[#666] text-xs">({items.length})</span>}
        </h3>
        <button
          onClick={() => fileInput.current?.click()}
          disabled={uploading}
          className="text-xs flex items-center gap-1 px-3 py-1.5 rounded-full border border-[#333] text-[#B0B0B0] hover:border-[#F2C48D] hover:text-[#F2C48D] disabled:opacity-50 transition-colors"
        >
          <Upload size={12} /> {uploading ? "Upload…" : "Ajouter"}
        </button>
        <input ref={fileInput} type="file" onChange={handleUpload} className="hidden" />
      </div>
      {error && (
        <div className="mb-3 text-xs text-[#FF5252] bg-[#1a0a0a] border border-[#FF5252]/30 rounded-lg p-2">
          {error}
        </div>
      )}
      {loading ? (
        <div className="text-xs text-[#666] py-2">Chargement…</div>
      ) : items.length === 0 ? (
        <div className="text-xs text-[#666] py-2">Aucune pièce jointe.</div>
      ) : (
        <div className="space-y-2">
          {items.map((a) => (
            <div key={a.id} className="bg-[#111] border border-[#222] rounded-xl p-3 flex items-center justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="text-sm text-white truncate">{a.original_name}</div>
                <div className="text-xs text-[#666]">{formatSize(a.size)}</div>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <a
                  href={`/api/attachments/${a.id}/download`}
                  className="p-1.5 text-[#666] hover:text-white rounded-lg hover:bg-[#222] transition-colors"
                  title="Télécharger"
                >
                  <Download size={14} strokeWidth={1.5} />
                </a>
                <button
                  onClick={() => handleDelete(a.id)}
                  className="p-1.5 text-[#666] hover:text-[#FF5252] rounded-lg hover:bg-[#222] transition-colors"
                  title="Supprimer"
                >
                  <Trash2 size={14} strokeWidth={1.5} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
