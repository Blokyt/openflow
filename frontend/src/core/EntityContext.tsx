import { createContext, useContext, useState, useEffect, useRef, ReactNode } from "react";
import { api } from "../api";
import { Entity } from "../types";
import Spinner from "./Spinner";

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
  // "global" = l'utilisateur a explicitement choisi la vue Global (null) ;
  // un nombre = une entité ; absent = aucun choix (reload posera une racine).
  const [selectedEntityId, setSelectedEntityId] = useState<number | null>(() => {
    const stored = localStorage.getItem("openflow_entity_id");
    return stored && stored !== "global" ? parseInt(stored, 10) : null;
  });
  const initialised = useRef(false);
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
        // Vue Global choisie explicitement : on la respecte (ne pas retomber sur
        // une entité). Sinon on garde le focus stocké s'il est encore valide,
        // à défaut la première racine interne (nécessaire pour un non-admin).
        if (localStorage.getItem("openflow_entity_id") === "global") return null;
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
    // On ne persiste pas au tout premier rendu (avant que reload() ait posé un
    // focus légitime) : sinon un « global » parasite s'écrirait pour un nouvel
    // utilisateur qui n'a rien choisi.
    if (!initialised.current) { initialised.current = true; return; }
    if (selectedEntityId !== null) {
      localStorage.setItem("openflow_entity_id", String(selectedEntityId));
    } else {
      // null après un vrai choix = vue Global explicite → sentinel persistant.
      localStorage.setItem("openflow_entity_id", "global");
    }
  }, [selectedEntityId]);

  // Tant que l'arbre n'a pas été résolu une première fois, on n'expose pas les
  // enfants : cela évite qu'une page interroge le backend sans entité (400 "Une
  // entité est requise pour ce rôle") ou avec une entité périmée d'une session
  // précédente hors du périmètre courant (403 "Accès refusé à cette entité").
  // reload() pose une entité légitime avant de libérer le rendu.
  if (!ready) {
    return <Spinner />;
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
