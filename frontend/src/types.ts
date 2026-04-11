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

export interface AppConfig {
  entity_name: string;
  currency: string;
  reference_date?: string;
  reference_amount?: number;
  modules: ModuleManifest[];
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
