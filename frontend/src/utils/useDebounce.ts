import { useEffect, useState } from "react";

/** Retourne `value`, mais mis à jour seulement `delay` ms après la dernière
 * modification. Sert à temporiser les recherches côté serveur (évite un appel
 * API à chaque frappe).
 */
export default function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}
