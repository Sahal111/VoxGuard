import { useEffect, useState } from "react";
import { checkGatewayHealth, type HealthResponse } from "../api/client";

type ConnectionStatus = "checking" | "connected" | "disconnected";

export function useHealthCheck(intervalMs = 30000) {
  const [status, setStatus] = useState<ConnectionStatus>("checking");
  const [data, setData] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let active = true;

    async function check() {
      try {
        const result = await checkGatewayHealth();
        if (active) {
          setData(result);
          setStatus("connected");
        }
      } catch {
        if (active) {
          setData(null);
          setStatus("disconnected");
        }
      }
    }

    check();
    const id = setInterval(check, intervalMs);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [intervalMs]);

  return { status, data };
}
