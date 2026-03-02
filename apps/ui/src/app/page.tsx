import { QueryForm } from '@/components/QueryForm';

export default function Home() {
  return (
    <main className="min-h-screen p-8">
      <div className="max-w-4xl mx-auto">
        <header className="mb-8 text-center">
          <h1 className="text-4xl font-bold mb-4">Islam Intelligent</h1>
          <p className="text-lg text-gray-600 mb-2">
            Evidence-first Islamic Knowledge Intelligence Platform
          </p>
          <p className="text-sm text-gray-500">
            Every answer is backed by citations from verified sources
          </p>
        </header>

        <QueryForm />

        <footer className="mt-16 pt-8 border-t text-center text-sm text-gray-500">
          <p>
            Quran sources: <a href="https://tanzil.net" className="underline" target="_blank" rel="noopener">Tanzil Project</a> (CC-BY-3.0)
          </p>
        </footer>
      </div>
    </main>
  );
}
