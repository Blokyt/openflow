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

  async function reload() {
    try {
      const tree = await api.getEntityTree();
      setEntities(tree);
    } catch {
      setEntities([]);
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
