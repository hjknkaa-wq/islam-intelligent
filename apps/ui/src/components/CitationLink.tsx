'use client';

import { useState } from 'react';
import { Citation } from '@/types/api';
import { EvidencePanel } from './EvidencePanel';

interface CitationLinkProps {
  citation: Citation;
  index: number;
}

export function CitationLink({ citation, index }: CitationLinkProps) {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <span className="inline-block">
      <sup
        className="cursor-pointer text-blue-600 hover:underline font-medium"
        onClick={() => setShowDetails(!showDetails)}
        title={`${citation.canonical_id}: ${citation.snippet.substring(0, 50)}...`}
      >
        [{index + 1}]
      </sup>
      
      {showDetails && (
        <div className="mt-3">
          <EvidencePanel
            evidenceSpanId={citation.evidence_span_id}
            textUnitId=""
            canonicalId={citation.canonical_id}
            snippetText={citation.snippet}
            snippetHash=""
            startByte={0}
            endByte={0}
          />
        </div>
      )}
    </span>
  );
}
