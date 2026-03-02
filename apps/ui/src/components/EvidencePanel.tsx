'use client';

import { useEffect, useState } from 'react';
import { splitTextForHighlight, verifyHash } from '@/lib/byteOffsets';

interface EvidencePanelProps {
  evidenceSpanId: string;
  textUnitId: string;
  canonicalId: string;
  snippetText: string;
  snippetHash: string;
  startByte: number;
  endByte: number;
  fullText?: string;
}

export function EvidencePanel({
  evidenceSpanId,
  canonicalId,
  snippetText,
  snippetHash,
  startByte,
  endByte,
  fullText,
}: EvidencePanelProps) {
  const [verificationStatus, setVerificationStatus] = useState<'verifying' | 'verified' | 'failed'>('verifying');
  const [highlightedSegments, setHighlightedSegments] = useState<{
    before: string;
    highlighted: string;
    after: string;
  } | null>(null);

  useEffect(() => {
    async function verifyAndHighlight() {
      // Verify the snippet hash
      const isValid = await verifyHash(snippetText, snippetHash);
      setVerificationStatus(isValid ? 'verified' : 'failed');

      // If we have full text, compute highlight segments
      if (fullText) {
        try {
          const segments = splitTextForHighlight(fullText, startByte, endByte);
          setHighlightedSegments(segments);
        } catch (e) {
          console.error('Failed to compute highlight:', e);
        }
      }
    }

    verifyAndHighlight();
  }, [snippetText, snippetHash, fullText, startByte, endByte]);

  const getStatusBadge = () => {
    switch (verificationStatus) {
      case 'verified':
        return (
          <span className="px-2 py-1 bg-green-100 text-green-800 text-xs rounded-full">
            ✓ Verified
          </span>
        );
      case 'failed':
        return (
          <span className="px-2 py-1 bg-red-100 text-red-800 text-xs rounded-full">
            ✗ Hash Mismatch
          </span>
        );
      default:
        return (
          <span className="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded-full">
            Verifying...
          </span>
        );
    }
  };

  return (
    <div className="p-4 bg-white border rounded-lg shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="font-medium text-gray-700">{canonicalId}</span>
          {getStatusBadge()}
        </div>
        <span className="text-xs text-gray-400">ID: {evidenceSpanId.slice(0, 8)}...</span>
      </div>

      {verificationStatus === 'failed' && (
        <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded">
          <p className="text-sm text-red-700">
            ⚠️ Span verification failed. The text may have been modified.
          </p>
        </div>
      )}

      <div className="relative" dir="auto">
        {highlightedSegments ? (
          <div className="text-lg leading-loose font-arabic">
            <span className="text-gray-500">{highlightedSegments.before}</span>
            <mark className="bg-yellow-200 text-inherit px-1 rounded">
              {highlightedSegments.highlighted}
            </mark>
            <span className="text-gray-500">{highlightedSegments.after}</span>
          </div>
        ) : (
          <blockquote className="text-lg leading-loose font-arabic border-r-4 border-blue-400 pr-4 italic">
            {snippetText}
          </blockquote>
        )}
      </div>

      <div className="mt-4 pt-3 border-t text-xs text-gray-500">
        <details>
          <summary className="cursor-pointer hover:text-gray-700">Technical Details</summary>
          <div className="mt-2 space-y-1 font-mono">
            <p>Start byte: {startByte}</p>
            <p>End byte: {endByte}</p>
            <p>SHA-256: {snippetHash.slice(0, 16)}...</p>
          </div>
        </details>
      </div>
    </div>
  );
}
