const features = [
  {
    icon: "🛡️",
    title: "Tamper-Evident Audit",
    description:
      "Cryptographic hash chain ensures every action is recorded and any modification is detectable.",
  },
  {
    icon: "🔒",
    title: "Identity-Vote Separation",
    description:
      "Voter identity and ballot choice are stored in isolated databases with pseudonymous references.",
  },
  {
    icon: "✅",
    title: "Three-Way Reconciliation",
    description:
      "Results verified across ballot records, audit chain, and voter participation before finalization.",
  },
  {
    icon: "⚡",
    title: "Double-Vote Prevention",
    description:
      "Database-level unique constraints with idempotency ensure exactly one vote per eligible voter.",
  },
  {
    icon: "🔍",
    title: "Real-Time Anomaly Detection",
    description:
      "Security service monitors voting patterns and raises alerts on suspicious activity.",
  },
  {
    icon: "🏗️",
    title: "Microservices Architecture",
    description:
      "Six independent services with database-per-service isolation and event-driven communication.",
  },
];

export function FeatureGrid() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {features.map((feature) => (
        <div
          key={feature.title}
          className="glass-card rounded-xl p-6 transition-all duration-300 hover:border-vg-accent/30 hover:-translate-y-1"
        >
          <div className="text-3xl mb-4">{feature.icon}</div>
          <h3 className="text-lg font-semibold text-vg-text mb-2">
            {feature.title}
          </h3>
          <p className="text-sm text-vg-text-muted leading-relaxed">
            {feature.description}
          </p>
        </div>
      ))}
    </div>
  );
}
