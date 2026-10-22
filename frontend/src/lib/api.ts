import type { Guide, IngestionStatus } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  listGuides: (role?: "reference" | "candidate") =>
    request<Guide[]>(`/guides${role ? `?role=${role}` : ""}`),
  getGuide: (id: string) => request<Guide>(`/guides/${id}`),
  deleteGuide: (id: string) => request<void>(`/guides/${id}`, { method: "DELETE" }),
  reingest: (id: string) => request<Guide>(`/guides/${id}/reingest`, { method: "POST" }),
  ingestionStatus: (id: string) => request<IngestionStatus>(`/guides/${id}/ingestion-status`),
  uploadGuide: (file: File, role: "reference" | "candidate", name?: string) => {
    const body = new FormData();
    body.append("file", file);
    body.append("role", role);
    if (name) body.append("name", name);
    return request<Guide>("/guides", { method: "POST", body });
  },
  fileUrl: (id: string) => `${API_BASE}/guides/${id}/file`,
  assetUrl: (path: string) => `${API_BASE}${path}`,
};

export const profileApi = {
  profile: (id: string) => request<import("./types").StyleProfile>(`/guides/${id}/profile`),
  pages: (id: string, versionId?: string) =>
    request<import("./types").PageInfo[]>(`/guides/${id}/pages${versionId ? `?version_id=${versionId}` : ""}`),
  elements: (id: string, versionId?: string) =>
    request<import("./types").ElementInfo[]>(`/guides/${id}/elements${versionId ? `?version_id=${versionId}` : ""}`),
};
