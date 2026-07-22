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
  /** Montant en centimes entiers (toujours positif). Le sens est déterminé par from_entity_type / to_entity_type. */
  amount: number;
  description?: string;
  category_id?: number;
  division_id?: number;
  contact_id?: number;
  from_entity_id: number;
  to_entity_id: number;
  /** Type de l'entité source, renvoyé par l'API dans les listes : "internal" | "external" */
  from_entity_type?: string;
  /** Type de l'entité destination, renvoyé par l'API dans les listes : "internal" | "external" */
  to_entity_type?: string;
  category?: Category;
  reimb_contact_id?: number;
  reimb_person_name?: string;
  reimb_status?: string;
  /** Id de la fiche de remboursement liée (module reimbursements), si avance. */
  reimb_id?: number;
  /** Suivi trésorier : 1 si la transaction a été marquée justifiée. */
  justified?: number;
  justified_at?: string | null;
  /** 1 si rapprochée automatiquement (liée à une ligne bancaire couverte). */
  reconciled?: number;
  /** 1 si rapprochée forcée à la main (indépendant du lien bancaire). */
  reconciled_manual?: number;
  /** Nombre de pièces jointes liées (module attachments). */
  attachment_count?: number;
}

export interface Category {
  id: number;
  name: string;
  parent_id?: number;
  color?: string;
  icon?: string;
  children?: Category[];
  tx_count?: number;
  /** Total des transactions de la catégorie, en centimes entiers */
  tx_total?: number;
  descendant_tx_count?: number;
  /** Total des transactions de la catégorie et de ses descendants, en centimes entiers */
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
  /** Solde en centimes entiers */
  balance: number;
  /** Total des recettes en centimes entiers */
  total_income: number;
  /** Total des dépenses en centimes entiers */
  total_expenses: number;
  transaction_count: number;
  reference_date?: string;
  /** Montant de référence en centimes entiers */
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
  /** Solde en centimes entiers */
  balance: number;
  /** Montant de référence en centimes entiers */
  reference_amount: number;
  reference_date: string | null;
  transactions_sum: number;
}

export interface ConsolidatedBalance {
  entity_id: number;
  /** Solde propre en centimes entiers */
  own_balance: number;
  /** Solde consolidé (propre + enfants) en centimes entiers */
  consolidated_balance: number;
  children: EntityBalance[];
}
