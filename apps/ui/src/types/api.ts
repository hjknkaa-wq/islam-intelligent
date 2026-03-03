/** Type definitions for API responses */

export interface Citation {
  evidence_span_id: string;
  canonical_id: string;
  snippet: string;
}

export interface Statement {
  text: string;
  citations: Citation[];
}

export interface AnswerContract {
  verdict: 'answer' | 'abstain';
  statements: Statement[];
  abstain_reason: string | null;
  fail_reason: string | null;
  retrieved_count: number;
  sufficiency_score: number;
}
