export interface MemoryRecord {
  id: string;
  tenant_id: string;
  user_id: string;
  content: string;
  memory_type: string;
  status: string;
  sensitivity: string;
  importance: number;
  confidence: number;
  reinforcement_count: number;
  source_kind: string;
  source_conversation_id?: string;
  source_excerpt?: string;
  initial_policy_decision: string;
  initial_policy_reason: string;
  created_at: string;
  updated_at: string;
  archived_at?: string;
  deleted_at?: string;
  identity_slot?: string;
}

export interface UsedMemory {
  memory_id: string;
  content: string;
  memory_type: string;
  score: number;
  reason: string;
  score_breakdown: {
    semantic_score: number;
    keyword_score: number;
    importance_score: number;
    recency_score: number;
    confidence_score: number;
    reinforcement_score: number;
  };
  source?: {
    kind: string;
    excerpt?: string;
  };
}
