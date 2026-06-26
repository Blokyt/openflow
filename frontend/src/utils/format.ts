export const eur = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

/** Formate un montant en centimes entiers vers une chaîne €. Ex : 1500 -> "15,00 €" */
export function formatEuros(cents: number | null | undefined): string {
  return eur.format((cents ?? 0) / 100);
}

/** Convertit une saisie utilisateur en euros (string) vers des centimes entiers. */
export function eurosToCents(input: string): number {
  const n = parseFloat(String(input).replace(",", "."));
  return Number.isFinite(n) ? Math.round(n * 100) : 0;
}

/** Convertit un montant en centimes entiers vers un nombre en euros (pour pré-remplir un champ). */
export function centsToEuros(cents: number | null | undefined): number {
  return (cents ?? 0) / 100;
}

/** Couleurs sémantiques centralisées pour les montants. */
export const COLOR_EXPENSE = "#FF5252";
export const COLOR_INCOME = "#00C853";

/** Couleurs du budget prévisionnel : gris tant qu'il est un placeholder hérité du mandat
 *  précédent, doré dès qu'il a été saisi/modifié ce mandat. Seul le réel reste rouge/vert. */
export const COLOR_BUDGET_SEEDED = "#777";
export const COLOR_BUDGET_MODIFIED = "#F2C48D";

/** Formate une date ISO (YYYY-MM-DD) au format français DD/MM/YYYY. Renvoie "—" si absente. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
}

export function budgetColor(pct: number): string {
  if (pct < 70) return "#00C853";
  if (pct < 95) return "#F2C48D";
  return "#FF5252";
}

/** Détermine la couleur et le préfixe signe d'une transaction selon le type des entités. */
export function txTone(tx: {
  from_entity_type?: string;
  to_entity_type?: string;
}): { color: string; sign: string } {
  if (tx.to_entity_type === "internal" && tx.from_entity_type === "external") {
    return { color: COLOR_INCOME, sign: "+" };
  }
  if (tx.from_entity_type === "internal" && tx.to_entity_type === "external") {
    return { color: COLOR_EXPENSE, sign: "-" };
  }
  // virement interne ou type inconnu
  return { color: "#B0B0B0", sign: "" };
}
