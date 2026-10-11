interface StatusIndicatorProps {
  status: "checking" | "connected" | "disconnected";
}

export function StatusIndicator({ status }: StatusIndicatorProps) {
  const config = {
    checking: { color: "bg-vg-warning", label: "Connecting..." },
    connected: { color: "bg-vg-success", label: "API Connected" },
    disconnected: { color: "bg-vg-danger", label: "API Offline" },
  };

  const { color, label } = config[status];

  return (
    <div className="flex items-center gap-2 text-sm text-vg-text-muted">
      <span
        className={`inline-block w-2 h-2 rounded-full ${color} animate-pulse-dot`}
      />
      <span>{label}</span>
    </div>
  );
}
