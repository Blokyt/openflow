const BASE_URL = "/api";
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, { headers: { "Content-Type": "application/json" }, ...options });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || response.statusText);
  }
  return response.json();
}
export const api = {
  getModules: () => request<any[]>("/modules"),
  getAllModules: () => request<any[]>("/modules/all"),
  getConfig: () => request<any>("/config"),
  updateEntity: (entity: any) => request<any>("/config/entity", { method: "PUT", body: JSON.stringify(entity) }),
  updateBalance: (balance: any) => request<any>("/config/balance", { method: "PUT", body: JSON.stringify(balance) }),
  toggleModule: (id: string, active: boolean) => request<any>(`/config/modules/${id}?active=${active}`, { method: "PUT" }),
  getTransactions: (params?: Record<string, string>) => {
    const query = params ? "?" + new URLSearchParams(params).toString() : "";
    return request<any[]>(`/transactions/${query}`);
  },
  createTransaction: (tx: any) => request<any>("/transactions/", { method: "POST", body: JSON.stringify(tx) }),
  updateTransaction: (id: number, tx: any) => request<any>(`/transactions/${id}`, { method: "PUT", body: JSON.stringify(tx) }),
  deleteTransaction: (id: number) => request<any>(`/transactions/${id}`, { method: "DELETE" }),
  getCategories: () => request<any[]>("/categories/"),
  getCategoryTree: () => request<any[]>("/categories/tree"),
  createCategory: (cat: any) => request<any>("/categories/", { method: "POST", body: JSON.stringify(cat) }),
  updateCategory: (id: number, cat: any) => request<any>(`/categories/${id}`, { method: "PUT", body: JSON.stringify(cat) }),
  deleteCategory: (id: number) => request<any>(`/categories/${id}`, { method: "DELETE" }),
  getBudgets: (period?: string) => {
    const query = period ? `?period=${encodeURIComponent(period)}` : "";
    return request<any[]>(`/budget/${query}`);
  },
  createBudget: (b: any) => request<any>("/budget/", { method: "POST", body: JSON.stringify(b) }),
  getBudgetStatus: () => request<any[]>("/budget/status"),
  getBudget: (id: number) => request<any>(`/budget/${id}`),
  updateBudget: (id: number, b: any) => request<any>(`/budget/${id}`, { method: "PUT", body: JSON.stringify(b) }),
  deleteBudget: (id: number) => request<any>(`/budget/${id}`, { method: "DELETE" }),
  getBankStatements: (status?: string) => {
    const query = status ? `?status=${encodeURIComponent(status)}` : "";
    return request<any[]>(`/bank_reconciliation/${query}`);
  },
  importBankStatements: (entries: { date: string; label: string; amount: number }[]) =>
    request<any[]>("/bank_reconciliation/import", { method: "POST", body: JSON.stringify({ entries }) }),
  getBankSuggestions: (id: number) => request<any[]>(`/bank_reconciliation/suggestions/${id}`),
  matchBankStatement: (statement_id: number, transaction_id: number) =>
    request<any>("/bank_reconciliation/match", { method: "POST", body: JSON.stringify({ statement_id, transaction_id }) }),
  unmatchBankStatement: (id: number) =>
    request<any>(`/bank_reconciliation/unmatch/${id}`, { method: "POST" }),
  deleteBankStatement: (id: number) =>
    request<any>(`/bank_reconciliation/${id}`, { method: "DELETE" }),
  getSummary: (entityId?: number) => {
    const query = entityId ? `?entity_id=${entityId}` : "";
    return request<any>(`/dashboard/summary${query}`);
  },
  // Entities
  getEntities: (type?: string) => {
    const query = type ? `?type=${type}` : "";
    return request<any[]>(`/entities/${query}`);
  },
  getEntityTree: () => request<any[]>("/entities/tree"),
  createEntity: (e: any) => request<any>("/entities/", { method: "POST", body: JSON.stringify(e) }),
  updateEntity_: (id: number, e: any) => request<any>(`/entities/${id}`, { method: "PUT", body: JSON.stringify(e) }),
  deleteEntity: (id: number) => request<any>(`/entities/${id}`, { method: "DELETE" }),
  getEntityBalance: (id: number) => request<any>(`/entities/${id}/balance`),
  getConsolidatedBalance: (id: number) => request<any>(`/entities/${id}/consolidated`),
  getBalanceRef: (id: number) => request<any>(`/entities/${id}/balance-ref`),
  updateBalanceRef: (id: number, ref: any) => request<any>(`/entities/${id}/balance-ref`, { method: "PUT", body: JSON.stringify(ref) }),
  getWidgets: () => request<any[]>("/dashboard/widgets"),
  getLayout: () => request<any[]>("/dashboard/layout"),
  saveLayout: (layout: any[]) => request<any>("/dashboard/layout", { method: "PUT", body: JSON.stringify(layout) }),
};
