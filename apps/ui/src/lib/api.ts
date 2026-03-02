/** API client for Islam Intelligent */

import { AnswerContract } from '@/types/api';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export async function queryRAG(query: string): Promise<AnswerContract> {
  const response = await fetch(`${API_BASE_URL}/rag/query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query }),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}
