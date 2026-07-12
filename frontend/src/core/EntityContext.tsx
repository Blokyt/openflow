import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { api } from "../api";
import { Entity } from "../types";

interface EntityContextType {
  entities: Entity[];
  selectedEntityId: number | null;
  selectedEntity: Entity | null;
  setSelectedEntityId: (id: number | null) => void;
  reload: () => Promise<void>;
}

const EntityContext = createContext<EntityContextType>({
  entities: [],
  selectedEntityId: null,
  selectedEntity: null,
  setSelectedEntityId: () => {},
  reload: async () => {},
});

export function useEntity() {
  return useContext(EntityContext);
}

export function EntityProvider({ children }: { children: ReactNode }) {
  const [entities, setEntities] = useState<Entity[]>([]);
  const [selectedEntityId, setSelectedEntityId] = useState<number | null>(() => {
    const stored = localStorage.getItem("openflow_entity_id");
    return stored ? parseInt(stored, 10) : null;
  });
  // Passe à true dès que l'arbre a été résolu une première fois pour l'utilisateur
  // courant (voir la garde de rendu plus bas).
  const [ready, setReady] = useState(false);

  async function reload() {
    try {
      const tree = await api.getEntityTree();
      setEntities(tree);
      // Si le focus stocké (localStorage) ne correspond plus à une entité de
      // l'arbre reçu (ex : périmètre réduit d'un treasurer, focus fantôme laissé
      // par une session admin précédente), on retombe sur la première entité
      // interne racine, ou null si l'arbre est vide.
      setSelectedEntityId((current) => {
        if (current !== null && findEntity(tree, current)) return current;
        const firstRoot = tree.find((e) => e.type === "internal") || tree[0];
        return firstRoot ? firstRoot.id : null;
      });
    } catch {
      setEntities([]);
    } finally {
      setReady(true);
    }
  }

  useEffect(() => { reload(); }, []);

  useEffect(() => {
    if (selectedEntityId !== null) {
      localStorage.setItem("openflow_entity_id", String(selectedEntityId));
    } else {
      localStorage.removeItem("openflow_entity_id");
    }
  }, [selectedEntityId]);

  // Tant que l'arbre n'a pas été résolu une première fois, on n'expose pas les
  // enfants : cela évite qu'une page interroge le backend sans entité (400 "Une
  // entité est requise pour ce rôle") ou avec une entité périmée d'une session
  // précédente hors du périmètre courant (403 "Accès refusé à cette entité").
  // reload() pose une entité légitime avant de libérer le rendu.
  if (!ready) {
    return (
      <div className="flex items-center justify-center h-screen bg-black">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#F2C48D]" />
      </div>
    );
  }

  const selectedEntity = selectedEntityId
    ? findEntity(entities, selectedEntityId)
    : null;

  return (
    <EntityContext.Provider value={{ entities, selectedEntityId, selectedEntity, setSelectedEntityId, reload }}>
      {children}
    </EntityContext.Provider>
  );
}

function findEntity(tree: Entity[], id: number): Entity | null {
  for (const e of tree) {
    if (e.id === id) return e;
    if (e.children) {
      const found = findEntity(e.children, id);
      if (found) return found;
    }
  }
  return null;
}
