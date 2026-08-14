/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useCallback } from "react";
import { memoriesApi } from "../lib/api/memories";
import { MemoryRecord } from "../lib/types/memory";

export function useMemories(
  tenantId: string,
  userId: string,
  onMutation?: () => Promise<void>
) {
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [memoriesLoading, setMemoriesLoading] = useState(false);
  
  // Filters & Search
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Edit State
  const [editMemory, setEditMemory] = useState<MemoryRecord | null>(null);
  const [editContent, setEditContent] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const loadMemories = useCallback(async (tId = tenantId, uId = userId) => {
    setMemoriesLoading(true);
    setActionError(null);
    try {
      const fetchedMems = await memoriesApi.listMemories(
        tId,
        uId,
        statusFilter || undefined,
        typeFilter || undefined
      );
      setMemories(fetchedMems);
    } catch (err: any) {
      console.error(err);
      setActionError(err.message || "Failed to fetch memories.");
      throw err;
    } finally {
      setMemoriesLoading(false);
    }
  }, [tenantId, userId, statusFilter, typeFilter]);

  const handleTransitionStatus = useCallback(async (memoryId: string, nextStatus: string) => {
    setActionError(null);
    try {
      await memoriesApi.patchMemory(memoryId, {
        tenant_id: tenantId,
        user_id: userId,
        status: nextStatus,
      });
      if (onMutation) {
        await onMutation();
      }
      await loadMemories();
    } catch (err: any) {
      setActionError(err.message);
    }
  }, [tenantId, userId, loadMemories, onMutation]);

  const handleEditContentSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editMemory) return;
    setActionError(null);
    try {
      await memoriesApi.patchMemory(editMemory.id, {
        tenant_id: tenantId,
        user_id: userId,
        content: editContent,
      });
      setEditMemory(null);
      setEditContent("");
      if (onMutation) {
        await onMutation();
      }
      await loadMemories();
    } catch (err: any) {
      setActionError(err.message);
    }
  }, [tenantId, userId, editMemory, editContent, loadMemories, onMutation]);

  const handleDeleteMemory = useCallback(async (memoryId: string) => {
    if (!confirm("Are you sure you want to logically delete this memory record?")) return;
    setActionError(null);
    try {
      await memoriesApi.deleteMemory(memoryId, tenantId, userId);
      if (onMutation) {
        await onMutation();
      }
      await loadMemories();
    } catch (err: any) {
      setActionError(err.message);
    }
  }, [tenantId, userId, loadMemories, onMutation]);

  const filteredMemories = memories.filter((m) =>
    m.content.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (m.identity_slot && m.identity_slot.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return {
    memories,
    memoriesLoading,
    statusFilter,
    setStatusFilter,
    typeFilter,
    setTypeFilter,
    searchQuery,
    setSearchQuery,
    editMemory,
    setEditMemory,
    editContent,
    setEditContent,
    actionError,
    setActionError,
    loadMemories,
    handleTransitionStatus,
    handleEditContentSubmit,
    handleDeleteMemory,
    filteredMemories,
  };
}
