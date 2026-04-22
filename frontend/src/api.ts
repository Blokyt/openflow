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
  // Budget & Exercices
  listFiscalYears: () => request<any[]>("/budget/fiscal-years"),
  getCurrentFiscalYear: () => request<any>("/budget/fiscal-years/current"),
  createFiscalYear: (fy: any) =>
    request<any>("/budget/fiscal-years", { method: "POST", body: JSON.stringify(fy) }),
  updateFiscalYear: (id: number, fy: any) =>
    request<any>(`/budget/fiscal-years/${id}`, { method: "PUT", body: JSON.stringify(fy) }),
  deleteFiscalYear: (id: number) =>
    request<any>(`/budget/fiscal-years/${id}`, { method: "DELETE" }),
  listOpeningBalances: (id: number) =>
    request<any[]>(`/budget/fiscal-years/${id}/opening-balances`),
  upsertOpeningBalances: (id: number, entries: any[]) =>
    request<any[]>(`/budget/fiscal-years/${id}/opening-balances`, {
      method: "PUT",
      body: JSON.stringify(entries),
    }),
  getSuggestedOpening: (id: number) =>
    request<any[]>(`/budget/fiscal-years/${id}/suggested-opening`),
  listAllocations: (fyId: number) =>
    request<any[]>(`/budget/fiscal-years/${fyId}/allocations`),
  createAllocation: (fyId: number, a: any) =>
    request<any>(`/budget/fiscal-years/${fyId}/allocations`, {
      method: "POST",
      body: JSON.stringify(a),
    }),
  updateAllocation: (id: number, a: any) =>
    request<any>(`/budget/allocations/${id}`, {
      method: "PUT",
      body: JSON.stringify(a),
    }),
  deleteAllocation: (id: number) =>
    request<any>(`/budget/allocations/${id}`, { method: "DELETE" }),
  getBudgetView: (fyId: number) =>
    request<any>(`/budget/view?fiscal_year_id=${fyId}`),
  getTimeseries: (entityId?: number, months = 12) => {
    const q = new URLSearchParams();
    q.set("months", String(months));
    if (entityId) q.set("entity_id", String(entityId));
    return request<any[]>(`/dashboard/timeseries?${q.toString()}`);
  },
  getTopCategories: (entityId?: number, limit = 5) => {
    const q = new URLSearchParams();
    q.set("limit", String(limit));
    if (entityId) q.set("entity_id", String(entityId));
    return request<any[]>(`/dashboard/top-categories?${q.toString()}`);
  },
  getRecentTransactions: (entityId?: number, limit = 5) => {
    const q = new URLSearchParams();
    q.set("limit", String(limit));
    if (entityId) q.set("entity_id", String(entityId));
    return request<any[]>(`/dashboard/recent?${q.toString()}`);
  },
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
  updateEntityNode: (id: number, e: any) => request<any>(`/entities/${id}`, { method: "PUT", body: JSON.stringify(e) }),
  deleteEntity: (id: number) => request<any>(`/entities/${id}`, { method: "DELETE" }),
  getEntityBalance: (id: number) => request<any>(`/entities/${id}/balance`),
  getConsolidatedBalance: (id: number) => request<any>(`/entities/${id}/consolidated`),
  getBalanceRef: (id: number) => request<any>(`/entities/${id}/balance-ref`),
  updateBalanceRef: (id: number, ref: any) => request<any>(`/entities/${id}/balance-ref`, { method: "PUT", body: JSON.stringify(ref) }),
  getWidgets: () => request<any[]>("/dashboard/widgets"),
  getLayout: () => request<any[]>("/dashboard/layout"),
  saveLayout: (layout: any[]) => request<any>("/dashboard/layout", { method: "PUT", body: JSON.stringify(layout) }),
  // Auth
  login: (username: string, password: string) =>
    request<any>("/multi_users/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  logout: () => request<any>("/multi_users/logout", { method: "POST" }),
  getMe: () => request<any>("/multi_users/me"),
  changePassword: (old_password: string, new_password: string) =>
    request<any>("/multi_users/me/password", { method: "PUT", body: JSON.stringify({ old_password, new_password }) }),
  // User management (admin)
  getUsers: () => request<any[]>("/multi_users/"),
  createUser: (user: any) => request<any>("/multi_users/", { method: "POST", body: JSON.stringify(user) }),
  deleteUser: (id: number) => request<any>(`/multi_users/${id}`, { method: "DELETE" }),
  getUserEntities: (userId: number) => request<any[]>(`/multi_users/${userId}/entities`),
  assignUserEntity: (userId: number, data: any) =>
    request<any>(`/multi_users/${userId}/entities`, { method: "POST", body: JSON.stringify(data) }),
  removeUserEntity: (userId: number, entityId: number) =>
    request<any>(`/multi_users/${userId}/entities/${entityId}`, { method: "DELETE" }),
  // Tiers / Contacts
  getTiers: () => request<any[]>("/tiers/"),
  getContacts: () => request<any[]>("/tiers/"),
  // Backup
  getBackupPreview: () => request<any>("/backup/preview"),
  exportBackup: async () => {
    const response = await fetch(`${BASE_URL}/backup/export`);
    if (!response.ok) throw new Error("Erreur lors de l'export");
    const blob = await response.blob();
    const filename = response.headers.get("Content-Disposition")?.split("filename=")[1] || "openflow-backup.zip";
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },
  importBackup: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(`${BASE_URL}/backup/import`, { method: "POST", body: formData });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || response.statusText);
    }
    return response.json();
  },
};
