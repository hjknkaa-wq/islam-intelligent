import { EvidenceHighlight } from '@/components/EvidenceHighlight';

export default function EvidenceHighlightDevPage() {
  const text = 'مرحبا بالعالم';
  const snippetText = 'بالعالم';
  const startByte = 11;
  const endByte = 25;
  const snippetHash = '90f0b82e5b9ccc9cc48188cea80eaaf1221e9ce266ee1e00632833f911dbb251';

  const mismatchHash = '00'.repeat(32);

  return (
    <main className="min-h-screen p-8">
      <div className="max-w-3xl mx-auto space-y-8">
        <header className="space-y-2">
          <h1 className="text-3xl font-bold">EvidenceHighlight Demo</h1>
          <p className="text-sm text-gray-600">
            Verified example highlights the span; mismatch shows an error and does not highlight.
          </p>
        </header>

        <section className="p-4 bg-white border rounded-lg shadow-sm space-y-3">
          <h2 className="font-semibold text-gray-800">Verified</h2>
          <EvidenceHighlight
            text={text}
            startByte={startByte}
            endByte={endByte}
            snippetText={snippetText}
            snippetHash={snippetHash}
          />
        </section>

        <section className="p-4 bg-white border rounded-lg shadow-sm space-y-3">
          <h2 className="font-semibold text-gray-800">Mismatch</h2>
          <EvidenceHighlight
            text={text}
            startByte={startByte}
            endByte={endByte}
            snippetText={snippetText}
            snippetHash={mismatchHash}
          />
        </section>
      </div>
    </main>
  );
}
