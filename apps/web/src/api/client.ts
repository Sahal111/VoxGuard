/** API base URL from environment */
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

export interface HealthResponse {
  status: string;
  service: string;
  checks?: Record<string, { status: string; error?: string }>;
}

/** Check the API Gateway health. */
export async function checkGatewayHealth(): Promise<HealthResponse> {
  const gatewayBase = API_BASE_URL.replace(/\/api\/v1$/, "");
  const resp = await fetch(`${gatewayBase}/health/live`, {
    signal: AbortSignal.timeout(5000),
  });
  if (!resp.ok) {
    throw new Error(`Health check failed: ${resp.status}`);
  }
  return resp.json();
}
