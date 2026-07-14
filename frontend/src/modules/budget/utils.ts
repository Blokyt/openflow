/** Cherche le nœud d'entité `id` dans l'arbre budgétaire renvoyé par /budget/view. */
export function findGroupNode(nodes: any[], id: number): any | null {
  for (const n of nodes) {
    if (n.entity_id === id) return n;
    const found = findGroupNode(n.children ?? [], id);
    if (found) return found;
  }
  return null;
}
