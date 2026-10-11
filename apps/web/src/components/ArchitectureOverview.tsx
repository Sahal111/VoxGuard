const services = [
  { name: "API Gateway", port: 8000, role: "Request routing & correlation" },
  { name: "Auth Service", port: 8001, role: "Authentication & sessions" },
  { name: "Voter Service", port: 8002, role: "Elections & eligibility" },
  { name: "Ballot Service", port: 8003, role: "Vote casting & receipts" },
  { name: "Audit Service", port: 8004, role: "Hash chain & verification" },
  { name: "Result Service", port: 8005, role: "Tally & finalization" },
  { name: "Security Service", port: 8006, role: "Anomaly detection & alerts" },
];

export function ArchitectureOverview() {
  return (
    <div className="glass-card rounded-xl p-8">
      <h2 className="text-xl font-bold text-vg-text mb-6 flex items-center gap-3">
        <span className="w-8 h-8 rounded-lg bg-vg-accent/20 flex items-center justify-center text-vg-accent text-sm">
          ⚙
        </span>
        System Architecture
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {services.map((svc) => (
          <div
            key={svc.name}
            className="rounded-lg bg-vg-primary/50 border border-vg-surface-light/50 p-4 transition-colors hover:border-vg-accent/30"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-vg-text">
                {svc.name}
              </span>
              <span className="text-xs font-mono text-vg-text-muted bg-vg-surface px-2 py-0.5 rounded">
                :{svc.port}
              </span>
            </div>
            <p className="text-xs text-vg-text-muted">{svc.role}</p>
          </div>
        ))}
      </div>
      <div className="mt-6 flex flex-wrap gap-4 text-xs text-vg-text-muted">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded bg-blue-500/20 border border-blue-500/30" />
          PostgreSQL (6 databases)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded bg-amber-500/20 border border-amber-500/30" />
          RabbitMQ (event bus)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded bg-red-500/20 border border-red-500/30" />
          Redis (cache & rate limiting)
        </span>
      </div>
    </div>
  );
}
