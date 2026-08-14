import { UsedMemory } from "./memory";

export interface CandidateMemory {
  content: string;
  memory_type: string;
  confidence: number;
  importance: number;
  sensitivity: string;
  decision: string;
  reason: string;
  memory_id?: string;
}

export interface ChatResponse {
  assistant_message: string;
  used_memories: UsedMemory[];
  candidate_memories: CandidateMemory[];
  audit_event_ids: string[];
  temporary_chat: boolean;
  retrieval_mode: string;
  trace_id: string;
}
