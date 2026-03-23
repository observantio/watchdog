import { Sparkline, Card } from "../../components/ui";

export default function LogVolume({ volume, embedded = false }) {
  const data = volume && volume.length ? volume : [0];
  const total = data.reduce((a, b) => a + b, 0);
  const avg = data.length > 0 ? Math.round(total / data.length) : 0;
  const peak = data.length > 0 ? Math.max(...data) : 0;

  const content = (
    <>
      <div className="mb-3 w-full overflow-hidden">
        <Sparkline
          data={data}
          width={280}
          height={100}
          stroke="#60a5fa"
          strokeWidth={2}
          fill="rgba(96, 165, 250, 0.2)"
          className="w-full h-[100px]"
        />
      </div>
      <div className="grid grid-cols-3 gap-3 text-xs">
        <div className="bg-sre-surface rounded-lg p-2 max-w-full">
          <div className="text-sre-text-muted mb-1">Total</div>
          <div className="text-base font-bold text-sre-text truncate">
            {total.toLocaleString()}
          </div>
        </div>
        <div className="bg-sre-surface rounded-lg p-2 max-w-full">
          <div className="text-sre-text-muted mb-1">Avg/min</div>
          <div className="text-base font-bold text-sre-text truncate">
            {avg.toLocaleString()}
          </div>
        </div>
        <div className="bg-sre-surface rounded-lg p-2 max-w-full">
          <div className="text-sre-text-muted mb-1">Peak</div>
          <div className="text-base font-bold text-sre-text truncate">
            {peak.toLocaleString()}
          </div>
        </div>
      </div>
    </>
  );

  if (embedded) {
    return (
      <div>
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-sre-text text-left">
            Log Volume
          </h3>
          <p className="text-sm text-sre-text-muted mt-1 text-left">Over time</p>
        </div>
        {content}
      </div>
    );
  }

  return (
    <Card title="Log Volume" subtitle="Over time">
      {content}
    </Card>
  );
}
