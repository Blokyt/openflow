const BASE_URL = "/api";
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { headers: { "Content-Type": "application/json" }, ...options });
  } catch {
    throw new Error("Erreur de connexion au serveur. Vérifie ta connexion et réessaie.");
  }
  if (!response.ok) {
    // Session expirée en cours d'usage : retour forcé à l'écran de connexion.
    // On exclut les endpoints d'authentification eux-mêmes : /users/login (un
    // 401 y signifie "mauvais identifiants") et /users/me (401 = simplement
    // "pas connecté", déjà géré par AuthContext qui met user=null ; recharger
    // ici bouclerait à l'infini sur l'écran de connexion).
    if (
      response.status === 401 &&
      path !== "/users/login" &&
      path !== "/users/me"
    ) {
      window.location.reload();
    }
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Erreur ${response.status} : réponse inattendue du serveur.`);
  }
  return response.json();
}

// Variante de request() pour les réponses non-JSON (blobs de téléchargement,
// uploads multipart) : renvoie la Response brute mais applique la MÊME détection
// de session expirée (401 -> retour à l'écran de connexion) que request(), afin
// qu'aucun appel ne laisse une bannière technique sur une page qui a l'air
// encore connectée.
export async function rawFetch(path: string, options?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, options);
  } catch {
    throw new Error("Erreur de connexion au serveur. Vérifie ta connexion et réessaie.");
  }
  if (response.status === 401 && path !== "/users/login" && path !== "/users/me") {
    window.location.reload();
  }
  return response;
}

function reportQuery(params: { fiscal_year_id?: number; start_date?: string; end_date?: string; entity_id?: number }): string {
  const q = new URLSearchParams();
  if (params.fiscal_year_id != null) q.set("fiscal_year_id", String(params.fiscal_year_id));
  if (params.start_date) q.set("start_date", params.start_date);
  if (params.end_date) q.set("end_date", params.end_date);
  if (params.entity_id != null) q.set("entity_id", String(params.entity_id));
  return q.toString();
}

function filenameFromDisposition(header: string | null, fallback: string): string {
  return header?.split("filename=")[1]?.replace(/"/g, "") || fallback;
}

function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export const api = {
  // Auth & utilisateurs
  login: (email: string, password: string) =>
    request<any>("/users/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request<any>("/users/logout", { method: "POST" }),
  getMe: () => request<any>("/users/me"),
  changeMyPassword: (current_password: string, new_password: string) =>
    request<any>("/users/me/password", { method: "PUT", body: JSON.stringify({ current_password, new_password }) }),
  listUsers: () => request<any[]>("/users/"),
  updateUser: (id: number, data: any) =>
    request<any>(`/users/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  setUserRoles: (id: number, roles: { entity_id: number; role: string }[]) =>
    request<any>(`/users/${id}/roles`, { method: "PUT", body: JSON.stringify({ roles }) }),
  revokeUserSessions: (id: number) =>
    request<any>(`/users/${id}/sessions`, { method: "DELETE" }),
  listLoginEvents: (limit = 100) => request<any[]>(`/users/login-events?limit=${limit}`),
  createInvitation: (data: { email: string; is_admin?: boolean; roles?: { entity_id: number; role: string }[] }) =>
    request<any>("/users/invitations", { method: "POST", body: JSON.stringify(data) }),
  listInvitations: () => request<any[]>("/users/invitations"),
  deleteInvitation: (id: number) => request<any>(`/users/invitations/${id}`, { method: "DELETE" }),
  previewInvitation: (token: string) =>
    request<any>(`/users/invitations/preview?token=${encodeURIComponent(token)}`),
  acceptInvitation: (data: { token: string; display_name: string; password: string }) =>
    request<any>("/users/invitations/accept", { method: "POST", body: JSON.stringify(data) }),
  getModules: () => request<any[]>("/modules"),
  getAllModules: () => request<any[]>("/modules/all"),
  getConfig: () => request<any>("/config"),
  updateEntity: (entity: any) => request<any>("/config/entity", { method: "PUT", body: JSON.stringify(entity) }),
  updateBalance: (balance: any) => request<any>("/config/balance", { method: "PUT", body: JSON.stringify(balance) }),
  toggleModule: (id: string, active: boolean) => request<any>(`/config/modules/${id}?active=${active}`, { method: "PUT" }),
  getTransactions: (params?: Record<string, string>) => {
    const query = params ? "?" + new URLSearchParams(params).toString() : "";
    return request<{ total: number; items: any[] }>(`/transactions/${query}`);
  },
  createTransaction: (tx: any, force = false) =>
    request<any>(`/transactions/${force ? "?force=true" : ""}`, { method: "POST", body: JSON.stringify(tx) }),
  updateTransaction: (id: number, tx: any, force = false) =>
    request<any>(`/transactions/${id}${force ? "?force=true" : ""}`, { method: "PUT", body: JSON.stringify(tx) }),
  deleteTransaction: (id: number, force = false) =>
    request<any>(`/transactions/${id}${force ? "?force=true" : ""}`, { method: "DELETE" }),
  getCategories: () => request<any[]>("/categories/"),
  // Les stats de l'arbre suivent le focus global (entité + sous-entités, exercice).
  getCategoryTree: (entityId?: number, dateFrom?: string, dateTo?: string) => {
    const q = new URLSearchParams();
    if (entityId) { q.set("entity_id", String(entityId)); q.set("include_children", "true"); }
    if (dateFrom) q.set("date_from", dateFrom);
    if (dateTo) q.set("date_to", dateTo);
    const qs = q.toString();
    return request<any[]>(`/categories/tree${qs ? "?" + qs : ""}`);
  },
  createCategory: (cat: any) => request<any>("/categories/", { method: "POST", body: JSON.stringify(cat) }),
  updateCategory: (id: number, cat: any) => request<any>(`/categories/${id}`, { method: "PUT", body: JSON.stringify(cat) }),
  deleteCategory: (id: number) => request<any>(`/categories/${id}`, { method: "DELETE" }),
  getCategoryUsage: (id: number) =>
    request<{ transactions: number; allocations: number; children: number; accruals: number }>(
      `/categories/${id}/usage`
    ),
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
  createFiscalYear: (fy: { name: string; start_date: string; notes?: string; president_name?: string; tresorier_name?: string }) =>
    request<any>("/budget/fiscal-years", { method: "POST", body: JSON.stringify(fy) }),
  closeFiscalYear: (id: number, end_date?: string) =>
    request<any>(`/budget/fiscal-years/${id}/close`, { method: "POST", body: JSON.stringify({ end_date: end_date ?? null }) }),
  updateFiscalYear: (id: number, fy: any) =>
    request<any>(`/budget/fiscal-years/${id}`, { method: "PUT", body: JSON.stringify(fy) }),
  deleteFiscalYear: (id: number) =>
    request<any>(`/budget/fiscal-years/${id}`, { method: "DELETE" }),
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
  seedBudgetFromRealized: (fyId: number) =>
    request<{ created: number; source_fiscal_year_id: number; source_name: string }>(
      `/budget/fiscal-years/${fyId}/seed-from-realized`,
      { method: "POST" },
    ),
  getBudgetView: (fyId: number) =>
    request<any>(`/budget/view?fiscal_year_id=${fyId}`),
  getBudgetCategoryView: (fyId: number, entityId?: number) =>
    request<any>(`/budget/view/categories?fiscal_year_id=${fyId}${entityId ? `&entity_id=${entityId}` : ""}`),
  // Focus entité : le dashboard couvre toujours l'entité ET ses sous-entités
  // (include_children), comme la page Transactions — cohérence de périmètre.
  getTimeseries: (entityId?: number, months = 12, dateFrom?: string, dateTo?: string) => {
    const q = new URLSearchParams();
    q.set("months", String(months));
    if (entityId) { q.set("entity_id", String(entityId)); q.set("include_children", "true"); }
    if (dateFrom) q.set("date_from", dateFrom);
    if (dateTo) q.set("date_to", dateTo);
    return request<any[]>(`/dashboard/timeseries?${q.toString()}`);
  },
  getTopCategories: (entityId?: number, limit = 5, dateFrom?: string, dateTo?: string) => {
    const q = new URLSearchParams();
    q.set("limit", String(limit));
    if (entityId) { q.set("entity_id", String(entityId)); q.set("include_children", "true"); }
    if (dateFrom) q.set("date_from", dateFrom);
    if (dateTo) q.set("date_to", dateTo);
    return request<any[]>(`/dashboard/top-categories?${q.toString()}`);
  },
  getRecentTransactions: (entityId?: number, limit = 5, dateFrom?: string, dateTo?: string) => {
    const q = new URLSearchParams();
    q.set("limit", String(limit));
    if (entityId) { q.set("entity_id", String(entityId)); q.set("include_children", "true"); }
    if (dateFrom) q.set("date_from", dateFrom);
    if (dateTo) q.set("date_to", dateTo);
    return request<any[]>(`/dashboard/recent?${q.toString()}`);
  },
  getSummary: (entityId?: number, dateFrom?: string, dateTo?: string) => {
    const q = new URLSearchParams();
    if (entityId) { q.set("entity_id", String(entityId)); q.set("include_children", "true"); }
    if (dateFrom) q.set("date_from", dateFrom);
    if (dateTo) q.set("date_to", dateTo);
    const qs = q.toString();
    return request<any>(`/dashboard/summary${qs ? "?" + qs : ""}`);
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
  // Tiers / Contacts
  getTiers: (params?: Record<string, string | number>) => {
    const q = params ? "?" + new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString() : "";
    return request<{ total: number; items: any[] }>(`/tiers/${q}`);
  },
  getContacts: () =>
    request<{ total: number; items: any[] }>("/tiers/?limit=10000").then((r) => r.items),
  // Recherche paginée côté serveur (combobox) : évite de charger tout le carnet.
  searchContacts: (search: string, limit = 30) => {
    const q = new URLSearchParams();
    if (search) q.set("search", search);
    q.set("limit", String(limit));
    return request<{ total: number; items: any[] }>(`/tiers/?${q.toString()}`).then((r) => r.items);
  },
  getContact: (id: number) => request<any>(`/tiers/${id}`),
  createContact: (data: { name: string; type: string; email?: string; phone?: string }) =>
    request<any>("/tiers/", { method: "POST", body: JSON.stringify(data) }),
  // Soumissions (module submissions)
  createSubmission: (s: any) =>
    request<any>("/submissions/", { method: "POST", body: JSON.stringify(s) }),
  getMySubmissions: () => request<any[]>("/submissions/mine"),
  getSubmissions: (status?: string) =>
    request<any[]>(`/submissions/${status ? `?status=${encodeURIComponent(status)}` : ""}`),
  cancelSubmission: (id: number) =>
    request<any>(`/submissions/${id}/cancel`, { method: "POST" }),
  approveSubmission: (id: number, force = false) =>
    request<any>(`/submissions/${id}/approve${force ? "?force=true" : ""}`, { method: "POST" }),
  rejectSubmission: (id: number, comment: string) =>
    request<any>(`/submissions/${id}/reject`, { method: "POST", body: JSON.stringify({ comment }) }),
  listSubmissionAttachments: (id: number) => request<any[]>(`/attachments/submission/${id}`),
  uploadSubmissionAttachment: async (id: number, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await rawFetch(`/attachments/submission/${id}`, { method: "POST", body: formData });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Erreur ${response.status} : réponse inattendue du serveur.`);
    }
    return response.json();
  },
  deleteAttachment: (id: number) => request<any>(`/attachments/${id}`, { method: "DELETE" }),
  // Backup
  getBackupPreview: () => request<any>("/backup/preview"),
  exportBackup: async () => {
    const response = await rawFetch(`/backup/export`);
    if (!response.ok) throw new Error("Erreur lors de l'export");
    const blob = await response.blob();
    triggerBlobDownload(blob, filenameFromDisposition(response.headers.get("Content-Disposition"), "openflow-backup.zip"));
  },
  importBackup: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await rawFetch(`/backup/import`, { method: "POST", body: formData });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Erreur ${response.status} : réponse inattendue du serveur.`);
    }
    return response.json();
  },
  // Rapports comptables (compte de résultat, bilan, plan comptable)
  getCompteResultat: (params: { fiscal_year_id?: number; start_date?: string; end_date?: string; entity_id?: number }) =>
    request<any>(`/reports/compte-resultat?${reportQuery(params)}`),
  getBilan: (params: { fiscal_year_id?: number; entity_id?: number }) =>
    request<any>(`/reports/bilan?${reportQuery(params)}`),
  getReportAccounts: () => request<{ accounts: any[] }>("/reports/accounts"),
  getReportMapping: () => request<{ mapping: any[]; unmapped: any[] }>("/reports/mapping"),
  setReportMapping: (category_id: number, account_id: number | null) =>
    request<any>("/reports/mapping", { method: "PUT", body: JSON.stringify({ category_id, account_id }) }),
  getReportMappingSuggestions: () =>
    request<{ suggestions: any[] }>("/reports/mapping/suggestions"),
  applyReportMappingSuggestions: (entries: { category_id: number; account_id: number }[]) =>
    request<{ applied: number }>("/reports/mapping/apply-suggestions", {
      method: "POST",
      body: JSON.stringify({ entries }),
    }),
  downloadReportPdf: async (
    kind: "compte-resultat" | "bilan",
    params: { fiscal_year_id?: number; start_date?: string; end_date?: string; entity_id?: number },
  ) => {
    const response = await rawFetch(`/reports/${kind}/pdf?${reportQuery(params)}`);
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Erreur ${response.status} : réponse inattendue du serveur.`);
    }
    const blob = await response.blob();
    triggerBlobDownload(blob, filenameFromDisposition(response.headers.get("Content-Disposition"), `${kind}.pdf`));
  },
  // Régularisations d'engagement (créances / dettes de clôture)
  getAccruals: (fiscalYearId: number) =>
    request<any[]>(`/reports/accruals?fiscal_year_id=${fiscalYearId}`),
  createAccrual: (body: {
    fiscal_year_id: number; kind: string; amount: number; label: string;
    category_id?: number | null; entity_id?: number | null; description?: string;
  }) => request<any>("/reports/accruals", { method: "POST", body: JSON.stringify(body) }),
  updateAccrual: (id: number, body: any) =>
    request<any>(`/reports/accruals/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteAccrual: (id: number) =>
    request<any>(`/reports/accruals/${id}`, { method: "DELETE" }),
  // HelloAsso
  getHelloAssoConfig: () =>
    request<{ configured: boolean; organization_slug: string; has_secret: boolean }>("/helloasso/config"),
  putHelloAssoConfig: (cfg: { client_id: string; client_secret: string; organization_slug: string }) =>
    request<{ configured: boolean }>("/helloasso/config", { method: "PUT", body: JSON.stringify(cfg) }),
  syncHelloAsso: (fiscalYearId: number) =>
    request<any[]>(`/helloasso/sync?fiscal_year_id=${fiscalYearId}`, { method: "POST" }),
  getHelloAssoCampaigns: (fiscalYearId: number) =>
    request<any[]>(`/helloasso/campaigns?fiscal_year_id=${fiscalYearId}`),
  getHelloAssoLinks: (campaignId: number) =>
    request<any>(`/helloasso/campaigns/${campaignId}/links`),
  addHelloAssoLink: (campaignId: number, transactionId: number) =>
    request<any>(`/helloasso/campaigns/${campaignId}/links`, {
      method: "POST",
      body: JSON.stringify({ transaction_id: transactionId }),
    }),
  removeHelloAssoLink: (campaignId: number, transactionId: number) =>
    request<any>(`/helloasso/campaigns/${campaignId}/links/${transactionId}`, { method: "DELETE" }),
  getHelloAssoSuggestions: (campaignId: number) =>
    request<any>(`/helloasso/campaigns/${campaignId}/suggestions`),
  // DirENS — export Excel officiel (lignes = catégories, aucun mapping)
  downloadDirens: async (params: {
    bilan_fiscal_year_id: number;
    budget_fiscal_year_id?: number;
    assoc_name?: string;
  }) => {
    const q = new URLSearchParams();
    q.set("bilan_fiscal_year_id", String(params.bilan_fiscal_year_id));
    if (params.budget_fiscal_year_id != null) q.set("budget_fiscal_year_id", String(params.budget_fiscal_year_id));
    if (params.assoc_name) q.set("assoc_name", params.assoc_name);
    const response = await rawFetch(`/direns/export?${q.toString()}`);
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Erreur ${response.status} : réponse inattendue du serveur.`);
    }
    const blob = await response.blob();
    triggerBlobDownload(blob, filenameFromDisposition(response.headers.get("Content-Disposition"), "DirENS.xlsx"));
  },
};
