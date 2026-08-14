import { useState, useCallback } from "react";
import { healthApi } from "../lib/api/health";

export function useHealth() {
  const [connectionStatus, setConnectionStatus] = useState<"checking" | "connected" | "disconnected">("checking");
  const [systemVersion, setSystemVersion] = useState("1.0.0");

  const checkSystemHealth = useCallback(async () => {
    try {
      const health = await healthApi.checkHealth();
      setConnectionStatus("connected");
      if (health && health.version) {
        setSystemVersion(health.version);
      }
      return health;
    } catch (err) {
      setConnectionStatus("disconnected");
      throw err;
    }
  }, []);

  return { connectionStatus, systemVersion, setConnectionStatus, checkSystemHealth };
}
