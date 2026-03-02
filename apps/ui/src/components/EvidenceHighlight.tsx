'use client';

import { useEffect, useMemo, useState } from 'react';
import { byteOffsetsToStringRange } from '../lib/spanHighlighter';

export interface EvidenceHighlightProps {
  text: string;
  startByte: number;
  endByte: number;
  snippetText: string;
  snippetHash: string;
}

type VerificationStatus = 'verifying' | 'verified' | 'failed';

function normalizeSha256Hex(value: string): string | null {
  const v = value.trim().toLowerCase().replace(/^0x/, '');
  if (!/^[0-9a-f]{64}$/.test(v)) return null;
  return v;
}

async function sha256Utf8Hex(text: string): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    throw new Error('crypto.subtle is unavailable');
  }
  const bytes = new TextEncoder().encode(text);
  const hashBuffer = await globalThis.crypto.subtle.digest(
    'SHA-256',
    bytes as unknown as BufferSource
  );
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
}

function isProbablyArabic(text: string): boolean {
  // Arabic + Arabic Supplement + Arabic Extended + Arabic Presentation Forms
  return /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/.test(text);
}

export function EvidenceHighlight({
  text,
  startByte,
  endByte,
  snippetText,
  snippetHash,
}: EvidenceHighlightProps) {
  const [status, setStatus] = useState<VerificationStatus>('verifying');
  const [segments, setSegments] = useState<{
    before: string;
    highlighted: string;
    after: string;
  } | null>(null);

  const dir = useMemo<'rtl' | 'auto'>(() => {
    return isProbablyArabic(text) ? 'rtl' : 'auto';
  }, [text]);

  useEffect(() => {
    let cancelled = false;

    async function verifyAndComputeSegments() {
      setStatus('verifying');
      setSegments(null);

      const expectedHash = normalizeSha256Hex(snippetHash);
      if (!expectedHash) {
        setStatus('failed');
        return;
      }

      try {
        const range = byteOffsetsToStringRange(text, startByte, endByte);
        const extracted = range.snippet;
        if (extracted !== snippetText) {
          setStatus('failed');
          return;
        }

        const actualHash = await sha256Utf8Hex(extracted);
        if (actualHash !== expectedHash) {
          setStatus('failed');
          return;
        }

        if (cancelled) return;
        setSegments({
          before: text.slice(0, range.startChar),
          highlighted: extracted,
          after: text.slice(range.endChar),
        });
        setStatus('verified');
      } catch {
        if (cancelled) return;
        setStatus('failed');
      }
    }

    verifyAndComputeSegments();
    return () => {
      cancelled = true;
    };
  }, [text, startByte, endByte, snippetText, snippetHash]);

  const badge = (() => {
    switch (status) {
      case 'verified':
        return (
          <span className="px-2 py-1 bg-green-100 text-green-800 text-xs rounded-full">
            verified
          </span>
        );
      case 'failed':
        return (
          <span className="px-2 py-1 bg-red-100 text-red-800 text-xs rounded-full">
            failed
          </span>
        );
      default:
        return (
          <span className="px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded-full">
            verifying
          </span>
        );
    }
  })();

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        {badge}
        {status === 'failed' && (
          <span className="text-sm text-red-700">span verification failed</span>
        )}
      </div>

      <div
        dir={dir}
        className={[
          "text-lg leading-loose",
          dir === 'rtl' ? 'font-arabic text-right' : '',
        ].join(' ')}
      >
        {status === 'verified' && segments ? (
          <>
            <span className="text-gray-500">{segments.before}</span>
            <mark className="bg-yellow-200 text-inherit px-1 rounded">
              {segments.highlighted}
            </mark>
            <span className="text-gray-500">{segments.after}</span>
          </>
        ) : (
          <span className="text-gray-700">{text}</span>
        )}
      </div>
    </div>
  );
}
