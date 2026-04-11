export interface Transaction {
  id: number;
  date: string;
  label: string;
  amount: number;
  description?: string;
  category_id?: number;
  category?: Category;
}

export interface Category {
  id: number;
  name: string;
  parent_id?: number;
  children?: Category[];
}

export interface EntityConfig {
  name: string;
  type: string;
  currency: string;
  logo?: string;
  address?: string;
  siret?: string;
  rna?: string;
}

export interface BalanceConfig {
  date?: string;
  amount?: number;
}

export interface AppConfig {
  entity: EntityConfig;
  balance: BalanceConfig;
  modules: Record<string, boolean>;
}

export interface DashboardSummary {
  balance: number;
  total_income: number;
  total_expenses: number;
  transaction_count: number;
  reference_date?: string;
  reference_amount?: number;
}

export interface ModuleManifest {
  id: string;
  name: string;
  description?: string;
  active: boolean;
  core: boolean;
  icon?: string;
  route?: string;
}
