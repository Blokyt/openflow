/** Export CSV des transactions (format Excel-FR : séparateur ; et BOM UTF-8 pour les accents). */

function escapeCell(value: unknown): string {
  const s = value == null ? "" : String(value);
  return /[";\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** Génère le contenu CSV d'une liste de transactions (montants convertis des centimes vers euros). */
export function transactionsToCsv(rows: any[]): string {
  const header = [
    "#", "Date", "Libellé", "Source", "Destination",
    "Catégorie", "Payeur", "Montant (€)", "Description",
  ];
  const lines = rows.map((t) =>
    [
      t.id,
      t.date,
      t.label,
      t.from_entity_name ?? "",
      t.to_entity_name ?? "",
      t.category_name ?? "",
      t.reimb_person_name ?? "",
      ((t.amount ?? 0) / 100).toFixed(2).replace(".", ","),
      t.description ?? "",
    ]
      .map(escapeCell)
      .join(";")
  );
  // BOM (﻿) : Excel ouvre alors le fichier en UTF-8 et conserve les accents.
  return "﻿" + [header.join(";"), ...lines].join("\r\n");
}

/** Déclenche le téléchargement d'un contenu CSV côté navigateur. */
export function downloadCsv(content: string, filename: string): void {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
