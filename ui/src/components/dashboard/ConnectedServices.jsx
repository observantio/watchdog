import { SERVICES } from "../../constants/dashboard";

export function ConnectedServices() {
  return (
    <div className="grid grid-cols-1 gap-6">
      {SERVICES.map((service) => (
        <div
          key={service.name}
          className="flex items-center gap-4 p-6 bg-sre-bg-alt rounded-lg border border-sre-border hover:border-sre-primary/50 transition-all duration-200"
        >
          <div className="flex-shrink-0 w-12 h-12 bg-sre-primary/10 rounded-lg flex items-center justify-center text-sre-primary">
            {service.icon}
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-semibold text-sre-text text-left text-lg">
              {service.name}
            </div>
            <div className="text-sm text-sre-text-muted mt-1 text-left">
              {service.description}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
