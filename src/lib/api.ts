const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export interface StoreSummary {
  id: string;
  store_code: string;
  name: string;
  address: string;
  city: string;
  state: string;
  pincode: string;
  latitude: number;
  longitude: number;
  is_verified: boolean;
  default_min_margin_bps: number;
  clearance_below_margin_allowed: boolean;
  is_synthetic: boolean;
  owner_name?: string;
  owner_email?: string;
}

export interface AuthSession {
  access_token: string;
  user: {
    id: string;
    email: string;
    full_name: string;
    role: string;
    preferred_language: string;
    is_synthetic: boolean;
  };
  stores: StoreSummary[];
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem('rc_token');
  const headers = new Headers(init?.headers || {});
  const isFormData = typeof FormData !== 'undefined' && init?.body instanceof FormData;
  if (!headers.has('Content-Type') && init?.body && !isFormData) {
    headers.set('Content-Type', 'application/json');
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(json.error || json.detail || `Request failed with status ${res.status}`);
  }
  return json as T;
}
