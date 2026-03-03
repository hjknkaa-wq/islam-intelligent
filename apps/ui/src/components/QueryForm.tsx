'use client';

import { useEffect, useState } from 'react';
import { queryRAG } from '@/lib/api';
import { AnswerContract } from '@/types/api';
import { AnswerDisplay } from './AnswerDisplay';
import { AbstainDisplay } from './AbstainDisplay';

export function QueryForm() {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnswerContract | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isHydrated, setIsHydrated] = useState(false);

  useEffect(() => {
    setIsHydrated(true);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await queryRAG(query);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-4xl mx-auto">
      <form onSubmit={handleSubmit} className="mb-8">
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask about Islam..."
            className="flex-1 p-4 border rounded-lg text-lg"
            dir="auto"
            disabled={!isHydrated || loading}
          />
          <button
            type="submit"
            disabled={!isHydrated || loading || !query.trim()}
            className="px-6 py-4 bg-blue-600 text-white rounded-lg disabled:bg-gray-400"
          >
            {loading ? 'Loading...' : 'Ask'}
          </button>
        </div>
      </form>

      {error && (
        <div className="p-4 bg-red-100 text-red-800 rounded-lg mb-4">
          Error: {error}
        </div>
      )}

      {result && result.verdict === 'answer' && (
        <AnswerDisplay answer={result} />
      )}

      {result && result.verdict === 'abstain' && (
        <AbstainDisplay answer={result} />
      )}
    </div>
  );
}
