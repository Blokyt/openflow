export const eur = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

export function budgetColor(pct: number): string {
  if (pct < 70) return "#00C853";
  if (pct < 95) return "#F2C48D";
  return "#FF5252";
}
