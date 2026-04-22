export interface Contact {
  id: number;
  name: string;
  type: string;
  email?: string;
  phone?: string;
  address?: string;
  notes?: string;
}

export interface Transaction {
  id: number;
  date: string;
  label: string;
  amount: number;
  description?: string;
  category_id?: number;
  division_id?: number;
  contact_id?: number;
  from_entity_id: number;
  to_entity_id: number;
  category?: Category;
  reimb_contact_id?: number;
  reimb_person_name?: string;
  reimb_status?: string;
}

export interface Category {
  id: number;
  name: string;
  parent_id?: number;
  color?: string;
  icon?: string;
  children?: Category[];
  tx_count?: number;
  tx_total?: number;
  descendant_tx_count?: number;
  descendant_tx_total?: number;
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
  help?: string;
  active: boolean;
  core: boolean;
  icon?: string;
  route?: string;
}

export interface Entity {
  id: number;
  name: string;
  description: string;
  type: "internal" | "external";
  parent_id: number | null;
  is_default: number;
  is_divers: number;
  color: string;
  position: number;
  balance_mode?: "own" | "aggregate";
  created_at?: string;
  updated_at?: string;
  children?: Entity[];
}

export interface EntityBalance {
  entity_id: number;
  balance: number;
  reference_amount: number;
  reference_date: string | null;
  transactions_sum: number;
}

export interface ConsolidatedBalance {
  entity_id: number;
  own_balance: number;
  consolidated_balance: number;
  children: EntityBalance[];
}
