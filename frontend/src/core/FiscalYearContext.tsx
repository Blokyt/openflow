import { createContext, useContext, useEffect, useState, ReactNode, useCallback } from "react";
import { api } from "../api";

export interface FiscalYear {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
  is_current: number;
  notes: string;
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

  const reload = useCallback(async () => {
    try {
      const data = await api.listFiscalYears();
      setYears(data as FiscalYear[]);
    } catch {
      setYears([]);
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

  const currentYear = years.find((y) => y.is_current === 1) ?? null;
  const selectedYear =
    (selectedYearId ? years.find((y) => y.id === selectedYearId) : null) ?? currentYear;

  return (
    <FiscalYearContext.Provider
      value={{ years, currentYear, selectedYear, setSelectedYearId, reload }}
    >
      {children}
    </FiscalYearContext.Provider>
  );
}
