import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { Download, Upload, Archive, AlertTriangle, CheckCircle } from "lucide-react";

interface BackupPreview {
  tables: Record<string, number>;
  total_records: number;
}

interface ImportResult {
  success: boolean;
  message: string;
  backup_created: string;
  imported: Record<string, number>;
  total_records: number;
}

const TABLE_LABELS: Record<string, string> = {
  entities: "Entités",
  entity_balance_refs: "Références de solde",
  categories: "Catégories",
  contacts: "Contacts",
  transactions: "Transactions",
  budgets: "Budgets",
  reimbursements: "Remboursements",
  invoices: "Factures",
  invoice_lines: "Lignes factures",
  attachments: "Pièces jointes",
  transfers: "Virements",
  audit_log: "Journal audit",
  annotations: "Annotations",
  users: "Utilisateurs",
  sessions: "Sessions",
  user_entities: "Accès utilisateurs",
};

export default function BackupManager() {
  const [preview, setPreview] = useState<BackupPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState("");
  const [confirmImport, setConfirmImport] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadPreview = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getBackupPreview();
      setPreview(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPreview();
  }, [loadPreview]);

  const handleExport = async () => {
    setExporting(true);
    setError("");
    try {
      await api.exportBackup();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setExporting(false);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (!file.name.endsWith(".zip")) {
        setError("Le fichier doit être un .zip");
        return;
      }
      setSelectedFile(file);
      setConfirmImport(true);
      setError("");
      setImportResult(null);
    }
  };

  const handleImport = async () => {
    if (!selectedFile) return;
    setImporting(true);
    setError("");
    setConfirmImport(false);
    try {
      const result = await api.importBackup(selectedFile);
      setImportResult(result);
      loadPreview();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setImporting(false);
      setSelectedFile(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const cancelImport = () => {
    setConfirmImport(false);
    setSelectedFile(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <div className="max-w-3xl mx-auto p-6">
      <div className="flex items-center gap-3 mb-3">
        <Archive className="w-7 h-7 text-[#F2C48D]" />
        <h1 className="text-2xl font-bold text-white">Sauvegarde &amp; Restauration</h1>
      </div>
      <p className="text-sm text-[#B0B0B0] mb-8 leading-relaxed">
        Exporte ou restaure <strong>l'intégralité</strong> de la base (toutes les entités,
        catégories, transactions, contacts, etc.) dans un fichier ZIP. Pour ajouter de
        nouvelles transactions à partir d'un fichier Excel ou CSV,
        utilise plutôt <a href="/smart-import" className="text-[#F2C48D] hover:underline">Import intelligent</a>.
      </p>

      {/* Error */}
      {error && (
        <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Import success */}
      {importResult?.success && (
        <div className="mb-6 p-4 bg-green-500/10 border border-green-500/30 rounded-xl text-green-400 flex items-start gap-3">
          <CheckCircle className="w-5 h-5 mt-0.5 shrink-0" />
          <div>
            <p className="font-medium">{importResult.message}</p>
            <p className="text-sm text-green-400/70 mt-1">
              {importResult.total_records} enregistrements importés
            </p>
          </div>
        </div>
      )}

      {/* Export section */}
      <section className="bg-[#1a1a1a] border border-[#333] rounded-xl p-6 mb-6">
        <h2 className="text-lg font-semibold text-white mb-2">Exporter</h2>
        <p className="text-[#999] text-sm mb-4">
          Téléchargez un fichier ZIP contenant toutes vos données : entités,
          catégories, transactions, contacts et configuration.
        </p>

        {/* Preview of what will be exported */}
        {preview && (
          <div className="bg-[#111] rounded-lg p-4 mb-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm text-[#999]">Contenu de la sauvegarde</span>
              <span className="text-sm font-mono text-[#F2C48D]">
                {preview.total_records} enregistrements
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(preview.tables).map(([table, count]) => (
                <div
                  key={table}
                  className="flex items-center justify-between text-sm px-3 py-1.5 bg-[#1a1a1a] rounded"
                >
                  <span className="text-[#ccc]">{TABLE_LABELS[table] || table}</span>
                  <span className="text-[#999] font-mono">{count}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <button
          onClick={handleExport}
          disabled={exporting || loading}
          className="flex items-center gap-2 px-5 py-2.5 bg-[#F2C48D] text-black font-medium rounded-lg hover:bg-[#e5b57a] disabled:opacity-50 transition-colors"
        >
          <Download className="w-4 h-4" />
          {exporting ? "Export en cours..." : "Exporter (.zip)"}
        </button>
      </section>

      {/* Import section */}
      <section className="bg-[#1a1a1a] border border-[#333] rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-2">Importer</h2>
        <p className="text-[#999] text-sm mb-4">
          Restaurez une sauvegarde précédemment exportée. Toutes les données
          actuelles seront remplacées. Un backup automatique est créé avant
          l'import.
        </p>

        {/* Confirm dialog */}
        {confirmImport && selectedFile && (
          <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4 mb-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-yellow-500 mt-0.5 shrink-0" />
              <div className="flex-1">
                <p className="text-yellow-400 font-medium">Confirmer l'import ?</p>
                <p className="text-yellow-400/70 text-sm mt-1">
                  Le fichier <code className="bg-[#333] px-1 rounded">{selectedFile.name}</code>{" "}
                  va remplacer toutes les données actuelles. Un backup automatique
                  sera créé avant l'opération.
                </p>
                <div className="flex gap-3 mt-3">
                  <button
                    onClick={handleImport}
                    className="px-4 py-2 bg-yellow-500 text-black font-medium rounded-lg hover:bg-yellow-400 transition-colors text-sm"
                  >
                    Confirmer l'import
                  </button>
                  <button
                    onClick={cancelImport}
                    className="px-4 py-2 bg-[#333] text-[#ccc] rounded-lg hover:bg-[#444] transition-colors text-sm"
                  >
                    Annuler
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Drop zone */}
        <label
          className={`flex flex-col items-center justify-center gap-3 p-8 border-2 border-dashed rounded-xl cursor-pointer transition-colors ${
            importing
              ? "border-[#555] bg-[#111] cursor-not-allowed"
              : "border-[#444] hover:border-[#F2C48D] hover:bg-[#111]"
          }`}
        >
          <Upload className="w-8 h-8 text-[#666]" />
          <span className="text-[#999] text-sm">
            {importing
              ? "Import en cours..."
              : "Cliquez ou déposez un fichier .zip"}
          </span>
          <input
            ref={fileRef}
            type="file"
            accept=".zip"
            onChange={handleFileSelect}
            disabled={importing}
            className="hidden"
          />
        </label>
      </section>
    </div>
  );
}
