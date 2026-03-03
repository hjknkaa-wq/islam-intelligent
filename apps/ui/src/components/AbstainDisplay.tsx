'use client';

import { AnswerContract } from '@/types/api';

interface AbstainDisplayProps {
  answer: AnswerContract;
}

export function AbstainDisplay({ answer }: AbstainDisplayProps) {
  const abstainReason =
    answer.abstain_reason === 'insufficient_evidence'
      ? 'Not enough relevant evidence found'
      : answer.abstain_reason;

  return (
    <div className="p-6 bg-amber-50 border-2 border-amber-200 rounded-lg">
      <div className="flex items-center gap-2 mb-4">
        <span className="px-3 py-1 bg-amber-100 text-amber-800 rounded-full text-sm font-medium">
          Abstain
        </span>
        <span className="text-sm text-gray-500">
          Insufficient evidence
        </span>
      </div>

      <p className="text-gray-700 mb-4">
        The system cannot provide a confident answer based on the available evidence.
      </p>

      <div className="bg-white p-4 rounded border">
        <h4 className="font-semibold text-gray-800 mb-2">Details:</h4>
        <ul className="space-y-2 text-sm text-gray-600">
          <li>
            <strong>Abstain reason:</strong> {abstainReason ?? 'N/A'}
          </li>
          <li>
            <strong>Fail reason:</strong> {answer.fail_reason ?? 'N/A'}
          </li>
          <li>
            <strong>Evidence retrieved:</strong> {answer.retrieved_count}
          </li>
          <li>
            <strong>Sufficiency score:</strong> {' '}
            {(answer.sufficiency_score * 100).toFixed(1)}%
          </li>
        </ul>
      </div>

      <div className="bg-white p-4 rounded border mt-4">
        <h4 className="font-semibold text-gray-800 mb-2">Retrieved evidence</h4>
        <ul className="space-y-2 text-sm text-gray-600">
          <li>
            <strong>Count:</strong> {answer.retrieved_count}
          </li>
          <li>
            <strong>Note:</strong> Evidence spans are not included in the abstain response yet; only counts and sufficiency signals are shown.
          </li>
        </ul>
      </div>

      <div className="bg-white p-4 rounded border mt-4">
        <h4 className="font-semibold text-gray-800 mb-2">Missing requirements</h4>
        <ul className="space-y-2 text-sm text-gray-600">
          <li>
            <strong>Trusted evidence:</strong> At least 2 trusted evidence spans relevant to the query
          </li>
          <li>
            <strong>High confidence:</strong> At least 1 high-confidence match (score &gt; 0.5)
          </li>
          <li>
            <strong>Citation policy:</strong> Every answer statement must include 1+ resolving citations
          </li>
        </ul>
      </div>

      {answer.retrieved_count > 0 && (
        <div className="mt-4">
          <p className="text-sm text-gray-600">
            💡 Try rephrasing your question or ask about a different topic 
            with more available sources.
          </p>
        </div>
      )}
    </div>
  );
}
