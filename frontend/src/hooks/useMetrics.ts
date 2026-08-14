import { useState, useCallback } from "react";
import { governanceApi } from "../lib/api/governance";
import { AuditEvent, TenantMetrics } from "../lib/types/governance";

export function useMetrics(tenantId: string) {
  const [metrics, setMetrics] = useState<TenantMetrics | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditEvent[]>([]);
  const [metricsLoading, setMetricsLoading] = useState(false);

  const loadMetricsAndAudits = useCallback(async (tId = tenantId) => {
    setMetricsLoading(true);
    try {
      const fetchedMetrics = await governanceApi.getMetrics(tId);
      setMetrics(fetchedMetrics);

      const fetchedAudits = await governanceApi.listAudit(tId, undefined, undefined, 50);
      setAuditLogs(fetchedAudits);
    } catch (err) {
      console.error("Failed to load metrics/audits:", err);
      throw err;
    } finally {
      setMetricsLoading(false);
    }
  }, [tenantId]);

  return {
    metrics,
    auditLogs,
    metricsLoading,
    loadMetricsAndAudits
  };
}
