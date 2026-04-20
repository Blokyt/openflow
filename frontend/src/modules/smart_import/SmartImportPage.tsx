import { useRef, useState } from "react";
import { Upload, FileUp, Check, AlertTriangle, Plus, Pencil, Minus, X, FileText } from "lucide-react";

interface ParserResult {
  parser_id: string;
  parser_name: string;
  confidence: number;
  transactions_count: number;
  errors: string[];
  warnings: string[];
  meta: any;
  diff: {
    stats: { new: number; modified: number; unchanged: number; total: number };
    items: Array<{
      status: "new" | "modified" | "unchanged";
      draft: { date: string; label: string; amount: number; description: string; category_hint: string };
      existing: { id: number; amount: number } | null;
    }>;
  };
  error?: string;
}

interface AnalyzeResponse {
  import_id: string;
  filename: string;
  extension: string;
  results: ParserResult[];
}

const eur = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

async function apiFetch(path: string, options: RequestInit = {}) {
  const r = await fetch(`/api${path}`, options);
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(err.detail || r.statusText);
  }
  return r.json();
}

export default function SmartImportPage() {
  const [analyzing, setAnalyzing] = useState(false);
  const [response, setResponse] = useState<AnalyzeResponse | null>(null);
  const [selectedParser, setSelectedParser] = useState<string | null>(null);
  const [committing, setCommitting] = useState(false);
  const [committed, setCommitted] = useState<{ created: number; updated: number; skipped: number } | null>(null);
  const [error, setError] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setAnalyzing(true);
    setError("");
    setResponse(null);
    setCommitted(null);
    setSelectedParser(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch("/api/smart_import/analyze", { method: "POST", body: fd });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(err.detail || r.statusText);
      }
      const data = await r.json();
      setResponse(data);
      if (data.results.length > 0) {
        setSelectedParser(data.results[0].parser_id);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleCommit() {
    if (!response || !selectedParser) return;
    setCommitting(true);
    setError("");
    try {
      const result = await apiFetch("/smart_import/commit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          import_id: response.import_id,
          parser_id: selectedParser,
          apply_new: true,
          apply_modifications: true,
        }),
      });
      setCommitted(result);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setCommitting(false);
    }
  }

  async function handleCancel() {
    if (response) {
      try {
        await fetch(`/api/smart_import/cancel/${response.import_id}`, { method: "DELETE" });
      } catch {}
    }
    setResponse(null);
    setSelectedParser(null);
    setCommitted(null);
    setError("");
    if (fileRef.current) fileRef.current.value = "";
  }

  const currentResult = response?.results.find((r) => r.parser_id === selectedParser);

  return (
    <div className="p-8 max-w-5xl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
          Import intelligent
        </h1>
        <p className="text-[#666] text-sm mt-1">
          Déposez un fichier (Excel, CSV), OpenFlow détecte le format automatiquement.
        </p>
      </div>

      {error && (
        <div className="mb-4 p-4 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 mt-0.5 shrink-0" />
          <span className="text-sm">{error}</span>
        </div>
      )}

      {committed && (
        <div className="mb-4 p-4 bg-green-500/10 border border-green-500/30 rounded-xl text-green-400">
          <div className="flex items-center gap-2 mb-1">
            <Check className="w-5 h-5" />
            <span className="font-medium">Import terminé</span>
          </div>
          <p className="text-sm text-green-400/80">
            {committed.created} nouvelles, {committed.updated} mises à jour, {committed.skipped} inchangées.
          </p>
          <button
            onClick={handleCancel}
            className="mt-3 text-xs text-green-400 hover:text-green-300 underline"
          >
            Nouvel import
          </button>
        </div>
      )}

      {!response && !committed && (
        <label
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            const file = e.dataTransfer.files?.[0];
            if (file) handleFile(file);
          }}
          className={`flex flex-col items-center justify-center gap-3 p-12 border-2 border-dashed rounded-2xl cursor-pointer transition-colors ${
            dragOver ? "border-[#F2C48D] bg-[#F2C48D]/5" :
            analyzing ? "border-[#555] bg-[#111]" :
            "border-[#333] hover:border-[#F2C48D] hover:bg-[#111]"
          }`}
        >
          {analyzing ? (
            <>
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#F2C48D]" />
              <span className="text-[#999]">Analyse en cours...</span>
            </>
          ) : (
            <>
              <Upload className="w-12 h-12 text-[#555]" strokeWidth={1.2} />
              <div className="text-center">
                <p className="text-white font-medium">Cliquez ou déposez un fichier</p>
                <p className="text-[#666] text-sm mt-1">Excel (.xlsx, .xls), CSV (.csv, .tsv)</p>
              </div>
            </>
          )}
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xls,.csv,.tsv,.txt"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleFile(file);
            }}
            disabled={analyzing}
            className="hidden"
          />
        </label>
      )}

      {response && !committed && (
        <div className="space-y-5">
          {/* File header */}
          <div className="flex items-center justify-between bg-[#111] border border-[#222] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <FileText className="text-[#F2C48D]" size={18} />
              <div>
                <p className="text-white font-medium text-sm">{response.filename}</p>
                <p className="text-[#666] text-xs">
                  {response.results.length} parser{response.results.length > 1 ? "s" : ""} détecté{response.results.length > 1 ? "s" : ""}
                </p>
              </div>
            </div>
            <button
              onClick={handleCancel}
              className="text-[#666] hover:text-[#FF5252] transition-colors p-1"
              title="Annuler"
            >
              <X size={18} />
            </button>
          </div>

          {/* Parser results */}
          {response.results.length === 0 ? (
            <div className="bg-[#111] border border-[#222] rounded-xl p-8 text-center">
              <AlertTriangle className="text-[#FF5252] mx-auto mb-3" size={32} />
              <p className="text-white font-medium">Aucun parser ne reconnaît ce format</p>
              <p className="text-[#666] text-sm mt-2">
                Envoyez-moi un échantillon de ce format pour que je puisse ajouter un parser dédié.
              </p>
            </div>
          ) : (
            <>
              <div className="space-y-2">
                <p className="text-xs text-[#666] uppercase tracking-wider">
                  Choisissez la bonne interprétation
                </p>
                {response.results.map((res) => (
                  <button
                    key={res.parser_id}
                    onClick={() => setSelectedParser(res.parser_id)}
                    className={`w-full text-left rounded-xl p-4 border transition-colors ${
                      selectedParser === res.parser_id
                        ? "bg-[#F2C48D]/10 border-[#F2C48D]"
                        : "bg-[#111] border-[#222] hover:border-[#333]"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <span className={`text-sm font-medium ${selectedParser === res.parser_id ? "text-[#F2C48D]" : "text-white"}`}>
                          {res.parser_name}
                        </span>
                        <span className="text-xs text-[#666] bg-[#1a1a1a] px-2 py-0.5 rounded-full">
                          Confiance {Math.round(res.confidence * 100)}%
                        </span>
                      </div>
                      {res.error && (
                        <span className="text-xs text-[#FF5252]">Erreur</span>
                      )}
                    </div>
                    {res.error ? (
                      <p className="text-xs text-[#FF5252]">{res.error}</p>
                    ) : (
                      <div className="flex items-center gap-4 text-xs">
                        <span className="text-[#00C853] flex items-center gap-1">
                          <Plus size={12} /> {res.diff.stats.new} nouvelles
                        </span>
                        <span className="text-[#F59E0B] flex items-center gap-1">
                          <Pencil size={12} /> {res.diff.stats.modified} modifiées
                        </span>
                        <span className="text-[#666] flex items-center gap-1">
                          <Minus size={12} /> {res.diff.stats.unchanged} inchangées
                        </span>
                        <span className="text-[#666] ml-auto">{res.transactions_count} lignes totales</span>
                      </div>
                    )}
                  </button>
                ))}
              </div>

              {/* Preview of selected parser */}
              {currentResult && !currentResult.error && (
                <div className="bg-[#111] border border-[#222] rounded-xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-[#222] flex items-center justify-between">
                    <span className="text-sm font-medium text-white">Aperçu</span>
                    <span className="text-xs text-[#666]">
                      {currentResult.diff.items.length} transactions
                    </span>
                  </div>

                  {currentResult.warnings.length > 0 && (
                    <div className="px-4 py-2 bg-[#F59E0B]/10 border-b border-[#222]">
                      <p className="text-xs text-[#F59E0B]">
                        {currentResult.warnings.length} avertissement{currentResult.warnings.length > 1 ? "s" : ""} : {currentResult.warnings.slice(0, 3).join(" / ")}
                      </p>
                    </div>
                  )}

                  <div className="max-h-96 overflow-y-auto">
                    <table className="w-full text-xs">
                      <thead className="sticky top-0 bg-[#111]">
                        <tr className="border-b border-[#1a1a1a]">
                          <th className="px-3 py-2 text-left text-[#666] uppercase">Statut</th>
                          <th className="px-3 py-2 text-left text-[#666] uppercase">Date</th>
                          <th className="px-3 py-2 text-left text-[#666] uppercase">Libellé</th>
                          <th className="px-3 py-2 text-right text-[#666] uppercase">Montant</th>
                        </tr>
                      </thead>
                      <tbody>
                        {currentResult.diff.items.slice(0, 100).map((item, idx) => (
                          <tr key={idx} className={`border-t border-[#1a1a1a] ${
                            item.status === "new" ? "bg-[#00C853]/5" :
                            item.status === "modified" ? "bg-[#F59E0B]/5" : ""
                          }`}>
                            <td className="px-3 py-2">
                              {item.status === "new" && <span className="text-[#00C853] flex items-center gap-1"><Plus size={11} /> nouvelle</span>}
                              {item.status === "modified" && <span className="text-[#F59E0B] flex items-center gap-1"><Pencil size={11} /> modif</span>}
                              {item.status === "unchanged" && <span className="text-[#555]">—</span>}
                            </td>
                            <td className="px-3 py-2 text-[#B0B0B0] whitespace-nowrap">{item.draft.date}</td>
                            <td className="px-3 py-2 text-white">{item.draft.label}</td>
                            <td className={`px-3 py-2 text-right font-medium whitespace-nowrap ${
                              item.draft.amount >= 0 ? "text-[#00C853]" : "text-[#FF5252]"
                            }`}>
                              {item.status === "modified" && (
                                <span className="text-[#555] line-through mr-2 text-[10px]">
                                  {eur.format(item.existing?.amount ?? 0)}
                                </span>
                              )}
                              {eur.format(item.draft.amount)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {currentResult.diff.items.length > 100 && (
                      <p className="px-4 py-2 text-xs text-[#666] text-center border-t border-[#1a1a1a]">
                        … et {currentResult.diff.items.length - 100} autres lignes
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* Commit button */}
              {currentResult && !currentResult.error && (currentResult.diff.stats.new > 0 || currentResult.diff.stats.modified > 0) && (
                <div className="flex items-center justify-between bg-[#111] border border-[#222] rounded-xl p-4">
                  <div className="text-sm">
                    <p className="text-white font-medium">
                      Appliquer : {currentResult.diff.stats.new} nouvelles + {currentResult.diff.stats.modified} modifiées
                    </p>
                    <p className="text-[#666] text-xs mt-0.5">
                      Les {currentResult.diff.stats.unchanged} transactions inchangées seront ignorées.
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={handleCancel}
                      className="px-4 py-2 border border-[#333] text-[#666] rounded-lg hover:text-white hover:border-[#444] transition-colors text-sm"
                    >
                      Annuler
                    </button>
                    <button
                      onClick={handleCommit}
                      disabled={committing}
                      className="px-5 py-2 bg-[#F2C48D] text-black font-medium rounded-lg hover:bg-[#e5b87e] disabled:opacity-50 transition-colors text-sm flex items-center gap-2"
                    >
                      <FileUp size={14} />
                      {committing ? "Import en cours..." : "Confirmer l'import"}
                    </button>
                  </div>
                </div>
              )}

              {currentResult && (currentResult.diff.stats.new === 0 && currentResult.diff.stats.modified === 0) && !currentResult.error && (
                <div className="bg-[#111] border border-[#222] rounded-xl p-4 text-center">
                  <Check className="text-[#00C853] mx-auto mb-2" size={24} />
                  <p className="text-white text-sm">Tout est déjà à jour</p>
                  <p className="text-[#666] text-xs mt-1">Aucune nouvelle transaction ni modification détectée.</p>
                  <button
                    onClick={handleCancel}
                    className="mt-3 text-xs text-[#666] hover:text-white underline"
                  >
                    Fermer
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
