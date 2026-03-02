'use client';

import { useState } from 'react';
import { AnswerContract, Citation } from '@/types/api';

interface AnswerDisplayProps {
  answer: AnswerContract;
}

function CitationLink({ citation, index }: { citation: Citation; index: number }) {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <span className="inline-block">
      <sup
        className="cursor-pointer text-blue-600 hover:underline"
        onClick={() => setShowDetails(!showDetails)}
        title={`${citation.canonical_id}: ${citation.snippet.substring(0, 50)}...`}
      >
        [{index + 1}]
      </sup>
      {showDetails && (
        <div className="mt-2 p-3 bg-gray-50 border rounded text-sm">
          <p><strong>Source:</strong> {citation.canonical_id}</p>
          <p><strong>Evidence ID:</strong> {citation.evidence_span_id}</p>
          <blockquote className="mt-2 italic border-l-4 border-blue-400 pl-3">
            {citation.snippet}
          </blockquote>
        </div>
      )}
    </span>
  );
}

function StatementView({ text, citations, index }: { 
  text: string; 
  citations: Citation[];
  index: number;
}) {
  // STRICT GUARD: Do not render if citations are missing
  if (!citations || citations.length === 0) {
    return (
      <div className="p-4 bg-red-50 border-2 border-red-300 rounded-lg mb-4">
        <p className="text-red-700 font-semibold">⚠️ Rendering Error</p>
        <p className="text-red-600">
          This statement cannot be displayed because it lacks proper citations.
          This is a violation of the evidence-first policy.
        </p>
      </div>
    );
  }

  return (
    <div className="mb-6 p-4 bg-white border rounded-lg shadow-sm">
      <div className="flex items-start gap-2">
        <span className="font-bold text-gray-500">{index + 1}.</span>
        <p className="flex-1 text-lg leading-relaxed" dir="auto">
          {text}
        </p>
      </div>
      
      <div className="mt-3 flex flex-wrap gap-2">
        {citations.map((citation, idx) => (
          <CitationLink key={citation.evidence_span_id} citation={citation} index={idx} />
        ))}
      </div>
    </div>
  );
}

export function AnswerDisplay({ answer }: AnswerDisplayProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-4">
        <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm font-medium">
          Answer
        </span>
        <span className="text-sm text-gray-500">
          Based on {answer.retrieved_count} evidence{answer.retrieved_count !== 1 ? 's' : ''}
        </span>
      </div>

      <div className="space-y-4">
        {answer.statements.map((statement, idx) => (
          <StatementView
            key={idx}
            index={idx}
            text={statement.text}
            citations={statement.citations}
          />
        ))}
      </div>
    </div>
  );
}
