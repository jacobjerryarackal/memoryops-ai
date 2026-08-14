/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useCallback } from "react";
import { evidenceApi } from "../lib/api/evidence";
import { MemoryRecord } from "../lib/types/memory";

export function useEvidence(tenantId: string, userId: string) {
  const [evidenceMemory, setEvidenceMemory] = useState<MemoryRecord | null>(null);
  const [evidenceData, setEvidenceData] = useState<any | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);

  const handleShowEvidence = useCallback(async (m: MemoryRecord) => {
    setEvidenceMemory(m);
    setEvidenceLoading(true);
    setEvidenceData(null);
    try {
      const data = await evidenceApi.getEvidence(m.id, tenantId, userId);
      setEvidenceData(data);
    } catch (err: any) {
      console.error("Failed to load memory evidence:", err);
    } finally {
      setEvidenceLoading(false);
    }
  }, [tenantId, userId]);

  const handleCloseEvidence = useCallback(() => {
    setEvidenceMemory(null);
    setEvidenceData(null);
  }, []);

  return {
    evidenceMemory,
    evidenceData,
    evidenceLoading,
    handleShowEvidence,
    handleCloseEvidence
  };
}
