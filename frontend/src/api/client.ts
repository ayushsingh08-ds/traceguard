const API_BASE = "http://localhost:8000/api/v1";

export interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | undefined>;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public message: string,
    public details?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

class ApiClient {
  private token: string | null = null;

  constructor() {
    this.token = localStorage.getItem("tg_auth_token");
  }

  setToken(token: string | null): void {
    this.token = token;
    if (token) {
      localStorage.setItem("tg_auth_token", token);
    } else {
      localStorage.removeItem("tg_auth_token");
    }
  }

  getToken(): string | null {
    return this.token;
  }

  async request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const { params, headers, ...customConfig } = options;

    let url = `${API_BASE}${endpoint}`;
    if (params) {
      const searchParams = new URLSearchParams();
      Object.entries(params).forEach(([key, val]) => {
        if (val !== undefined) {
          searchParams.append(key, String(val));
        }
      });
      const queryString = searchParams.toString();
      if (queryString) {
        url += `?${queryString}`;
      }
    }

    const requestHeaders: Record<string, string> = {
      "Content-Type": "application/json",
      ...(headers as Record<string, string>),
    };

    if (this.token) {
      requestHeaders["Authorization"] = `Bearer ${this.token}`;
    }

    const response = await fetch(url, {
      ...customConfig,
      headers: requestHeaders,
    });

    if (response.status === 401) {
      this.setToken(null);
      // Cleanly surface session expiration to client components
      throw new ApiError(401, "Session expired. Please re-authenticate.");
    }

    if (!response.ok) {
      let errorMessage = `HTTP error ${response.status}`;
      let errorDetails: unknown = null;
      try {
        const errorJson = await response.json();
        errorMessage = errorJson.detail || errorMessage;
        errorDetails = errorJson;
      } catch {
        // Response was not JSON
      }
      throw new ApiError(response.status, errorMessage, errorDetails);
    }

    if (response.status === 204) {
      return {} as T;
    }

    return response.json();
  }

  get<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: "GET" });
  }

  post<T>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  patch<T>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
    });
  }
}

export const apiClient = new ApiClient();

