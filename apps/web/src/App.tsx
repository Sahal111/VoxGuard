import "./index.css";
import { StatusIndicator } from "./components/StatusIndicator";
import { FeatureGrid } from "./components/FeatureGrid";
import { ArchitectureOverview } from "./components/ArchitectureOverview";
import { useHealthCheck } from "./hooks/useHealthCheck";

function App() {
  const { status } = useHealthCheck();

  return (
    <div className="min-h-screen bg-grid">
      {/* ── Navigation ────────────────────────────────────────── */}
      <nav className="fixed top-0 left-0 right-0 z-50 glass-card border-t-0 border-x-0">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-vg-accent to-indigo-500 flex items-center justify-center font-bold text-white text-sm">
              VG
            </div>
            <span className="text-lg font-bold tracking-tight text-vg-text">
              VoxGuard
            </span>
          </div>
          <StatusIndicator status={status} />
        </div>
      </nav>

      {/* ── Hero ──────────────────────────────────────────────── */}
      <main className="max-w-7xl mx-auto px-6 pt-32 pb-20">
        <section className="text-center mb-20">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-vg-accent/10 border border-vg-accent/20 text-vg-accent text-sm font-medium mb-8">
            <span className="w-1.5 h-1.5 rounded-full bg-vg-accent animate-pulse-dot" />
            Verifiable Digital Election System
          </div>

          <h1 className="text-5xl md:text-7xl font-black tracking-tight mb-6">
            <span className="text-vg-text">Every Vote.</span>
            <br />
            <span className="text-gradient">Protected. Verifiable.</span>
          </h1>

          <p className="text-lg md:text-xl text-vg-text-muted max-w-2xl mx-auto leading-relaxed mb-10">
            A microservices-based election platform with cryptographic audit
            trails, identity-vote separation, and three-way result
            reconciliation.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a
              href="/docs"
              className="inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-xl bg-gradient-to-r from-vg-accent to-indigo-500 text-white font-semibold transition-all duration-300 hover:shadow-lg hover:shadow-vg-accent/25 hover:-translate-y-0.5"
            >
              API Documentation
              <span className="text-white/70">→</span>
            </a>
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-xl border border-vg-surface-light text-vg-text font-semibold transition-all duration-300 hover:bg-vg-surface hover:border-vg-text-muted/30"
            >
              View Source
            </a>
          </div>
        </section>

        {/* ── Features ────────────────────────────────────────── */}
        <section className="mb-20">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-vg-text mb-4">
              Security by Design
            </h2>
            <p className="text-vg-text-muted max-w-xl mx-auto">
              Every architectural decision prioritizes vote integrity,
              auditability, and privacy separation.
            </p>
          </div>
          <FeatureGrid />
        </section>

        {/* ── Architecture ────────────────────────────────────── */}
        <section className="mb-20">
          <ArchitectureOverview />
        </section>

        {/* ── Status Footer ───────────────────────────────────── */}
        <footer className="text-center text-sm text-vg-text-muted border-t border-vg-surface-light/30 pt-8">
          <p className="mb-2">
            VoxGuard — Verifiable Digital Election System
          </p>
          <p className="text-xs">
            Foundation build · Phase 09 · Development environment
          </p>
        </footer>
      </main>
    </div>
  );
}

export default App;
