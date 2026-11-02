import { formatMetric, niceTicks, scaleLinear, trendSeries } from "../../dashboard";
import type { MetricKey } from "../../dashboard";
import type { DashboardModelSummary } from "../../api";
import { useElementWidth } from "../../useElementWidth";

interface Props {
  models: DashboardModelSummary[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

const HEIGHT = 170;
const M = { top: 18, right: 36, bottom: 26, left: 44 };

function Trend({ models, metric, selectedId, onSelect }: Props & { metric: MetricKey }) {
  const [ref, width] = useElementWidth<HTMLDivElement>(280);
  const series = trendSeries(models, metric);
  if (series.length === 0) return null;
  const values = series.map((s) => s.value);
  const [lo, hi] = [Math.min(...values), Math.max(...values)];
  const pad = (hi - lo || Math.abs(hi) * 0.05 || 1) * 0.3;
  const x = scaleLinear(0, Math.max(series.length - 1, 1), M.left, width - M.right);
  const y = scaleLinear(lo - pad, hi + pad, HEIGHT - M.bottom, M.top);
  const ticks = niceTicks(hi + pad, 3).filter((t) => t >= lo - pad && t <= hi + pad);
  const line = series.map((s, i) => `${i ? "L" : "M"}${x(series.length === 1 ? 0.5 : i)},${y(s.value)}`).join("");

  return (
    <div className="chart" ref={ref}>
      <svg width={width} height={HEIGHT} role="group" aria-label={`Xu hướng ${metric === "r2_log" ? "R² log" : "MAE"} qua các phiên bản`}>
        {(ticks.length > 1 ? ticks : [lo, hi]).map((tick, ti) => (
          <g key={ti}>
            <line className="grid" x1={M.left} x2={width - M.right} y1={y(tick)} y2={y(tick)} />
            <text className="tick" x={M.left - 6} y={y(tick)} textAnchor="end" dominantBaseline="middle">{formatMetric(metric, tick)}</text>
          </g>
        ))}
        <path d={line} className="line" />
        {series.map((s, i) => {
          const cx = x(series.length === 1 ? 0.5 : i);
          const on = s.id === selectedId;
          return (
            <g key={s.id} role="button" tabIndex={0} className="pt" aria-label={`Phiên bản ${s.id}: ${formatMetric(metric, s.value)}`} aria-pressed={on}
              onClick={() => onSelect(s.id)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onSelect(s.id))}>
              <circle cx={cx} cy={y(s.value)} r={14} className="hit" />
              <circle cx={cx} cy={y(s.value)} r={on ? 6 : 4} className={on ? "dot dot--sel" : "dot dot--line"} />
              <text className="tick" x={cx} y={HEIGHT - 8} textAnchor="middle">{`#${s.id}`}</text>
              {(on || i === series.length - 1) && (
                <text className="label" x={cx} y={y(s.value) - 11} textAnchor={i === series.length - 1 && series.length > 1 ? "end" : "middle"}>{formatMetric(metric, s.value)}</text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/** Hai biểu đồ đường nhỏ (R² log, MAE), mỗi đại lượng một trục: không dùng hai trục trên cùng một khung. */
export function TrendLines(props: Props) {
  return (
    <div className="trend">
      <figure><figcaption>R² log (cao hơn là tốt hơn)</figcaption><Trend {...props} metric="r2_log" /></figure>
      <figure><figcaption>MAE, triệu/m² (thấp hơn là tốt hơn)</figcaption><Trend {...props} metric="mae" /></figure>
    </div>
  );
}
