import { createContext, useContext, useEffect, useState, ReactNode, useCallback } from "react";
import { api } from "../api";
import Spinner from "./Spinner";

export interface FiscalYear {
  id: number;
  name: string;
  start_date: string;
  end_date: string | null;
  notes: string;
  president_name?: string;
  tresorier_name?: string;
}

interface FiscalYearContextType {
  years: FiscalYear[];
  currentYear: FiscalYear | null;
  selectedYear: FiscalYear | null;
  setSelectedYearId: (id: number | null) => void;
  reload: () => Promise<void>;
}

const FiscalYearContext = createContext<FiscalYearContextType>({
  years: [],
  currentYear: null,
  selectedYear: null,
  setSelectedYearId: () => {},
  reload: async () => {},
});

export function useFiscalYear() {
  return useContext(FiscalYearContext);
}

export function FiscalYearProvider({ children }: { children: ReactNode }) {
  const [years, setYears] = useState<FiscalYear[]>([]);
  const [selectedYearId, setSelectedYearIdState] = useState<number | null>(() => {
    const stored = localStorage.getItem("openflow_fiscal_year_id");
    return stored ? parseInt(stored, 10) : null;
  });
  // Passe à true dès que la liste des exercices a été résolue une première
  // fois (voir la garde de rendu plus bas).
  const [ready, setReady] = useState(false);

  const reload = useCallback(async () => {
    try {
      const data = await api.listFiscalYears();
      setYears(data as FiscalYear[]);
    } catch {
      setYears([]);
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const setSelectedYearId = useCallback((id: number | null) => {
    setSelectedYearIdState(id);
    if (id === null) localStorage.removeItem("openflow_fiscal_year_id");
    else localStorage.setItem("openflow_fiscal_year_id", String(id));
  }, []);

  const currentYear = years.find((y) => y.end_date === null) ?? null;
  const selectedYear =
    (selectedYearId ? years.find((y) => y.id === selectedYearId) : null) ?? currentYear;

  // Tant que la liste des exercices n'a pas été résolue une première fois, on
  // n'expose pas les enfants : cela évite au Dashboard d'afficher un flash de
  // totaux toute-période (sans filtre d'exercice) avant de se recorriger.
  if (!ready) {
    return <Spinner />;
  }

  return (
    <FiscalYearContext.Provider
      value={{ years, currentYear, selectedYear, setSelectedYearId, reload }}
    >
      {children}
    </FiscalYearContext.Provider>
  );
}
