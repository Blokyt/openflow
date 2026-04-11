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
  getSummary: () => request<any>("/dashboard/summary"),
  getWidgets: () => request<any[]>("/dashboard/widgets"),
  getLayout: () => request<any[]>("/dashboard/layout"),
  saveLayout: (layout: any[]) => request<any>("/dashboard/layout", { method: "PUT", body: JSON.stringify(layout) }),
};
