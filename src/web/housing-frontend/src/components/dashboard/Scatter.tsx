import { useId, useMemo, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import type { ScatterPoint } from "../../api";
import { formatNumber, logTicks, nearestPoint, scaleLinear, typeColor, typeLabel, typeShape } from "../../dashboard";
import type { TypeShape } from "../../dashboard";
import { useElementWidth } from "../../useElementWidth";
import { ChartTip, TipRow } from "./ChartTip";

interface Props {
  points: ScatterPoint[]; // các điểm đang hiện (đã lọc theo loại)
  domain: [number, number]; // cố định theo toàn bộ điểm để ẩn/hiện loại không làm trục nhảy
  q90: number; // sai số log phân vị 90: vẽ dải ±q quanh y = x
  compact?: boolean; // ô nhỏ khi tách theo loại
  caption: string;
}

const R = 4.5;

/** Hình đánh dấu theo loại; viền 2px màu nền (paint-order) để điểm chồng nhau vẫn tách được. */
export function Marker({ shape, x, y, color, active, radius = R }: { shape: TypeShape; x: number; y: number; color: string; active: boolean; radius?: number }) {
  const r = active ? radius + 2 : radius;
  const common = { fill: color, className: active ? "dot dot--on" : "dot" };
  switch (shape) {
    case "square":
      return <rect {...common} x={x - r} y={y - r} width={2 * r} height={2 * r} rx={1} />;
    case "triangle":
      return <path {...common} d={`M${x},${y - r - 1}L${x + r + 1},${y + r}L${x - r - 1},${y + r}Z`} />;
    case "diamond":
      return <path {...common} d={`M${x},${y - r - 1}L${x + r + 1},${y}L${x},${y + r + 1}L${x - r - 1},${y}Z`} />;
    case "cross":
      return <path className={active ? "dot dot--cross dot--on" : "dot dot--cross"} style={active ? undefined : { stroke: color }} d={`M${x - r},${y - r}L${x + r},${y + r}M${x + r},${y - r}L${x - r},${y + r}`} />;
    default:
      return <circle {...common} cx={x} cy={y} r={r} />;
  }
}

/** Scatter thực tế vs dự đoán trên trục log: y = x là dự đoán đúng, màu + hình theo loại nhà. */
export function Scatter({ points, domain, q90, compact = false, caption }: Props) {
  const [ref, width] = useElementWidth<HTMLDivElement>(compact ? 240 : 560);
  const [active, setActive] = useState<number | null>(null);
  const clipId = useId();
  const m = compact ? { top: 8, right: 8, bottom: 30, left: 34 } : { top: 12, right: 16, bottom: 44, left: 52 };
  const height = compact ? Math.round(width * 0.85) : Math.min(Math.round(width * 0.85), 440);
  const [d0, d1] = domain;
  const x = scaleLinear(Math.log10(d0), Math.log10(d1), m.left, width - m.right);
  const y = scaleLinear(Math.log10(d0), Math.log10(d1), height - m.bottom, m.top);
  const ticks = logTicks(d0, d1).filter((tick) => !compact || String(tick)[0] !== "2");

  // Toạ độ pixel tính một lần cho mỗi lần đổi dữ liệu/cỡ; con trỏ chỉ quét mảng này.
  const placed = useMemo(
    () => points.map((p) => ({ x: x(Math.log10(p.actual)), y: y(Math.log10(p.predicted)) })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [points, width, height],
  );
  const order = useMemo(() => points.map((_, i) => i).sort((a, b) => points[a].actual - points[b].actual), [points]);
  const clamp = (value: number) => Math.min(Math.max(value, d0), d1);
  const band = [
    [d0, clamp(d0 * Math.exp(q90))], [d1, clamp(d1 * Math.exp(q90))], [d1, clamp(d1 * Math.exp(-q90))], [d0, clamp(d0 * Math.exp(-q90))],
  ].map(([a, b]) => `${x(Math.log10(a))},${y(Math.log10(b))}`).join(" ");

  const move = (event: PointerEvent<SVGRectElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const index = nearestPoint(placed, event.clientX - box.left + m.left, event.clientY - box.top + m.top);
    setActive(index < 0 ? null : index);
  };
  const onKeyDown = (event: KeyboardEvent<SVGSVGElement>) => {
    if (points.length === 0 || !["ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown"].includes(event.key)) return;
    event.preventDefault();
    const forward = event.key === "ArrowRight" || event.key === "ArrowUp";
    const at = active === null ? -1 : order.indexOf(active);
    const next = Math.min(Math.max(at + (forward ? 1 : -1), 0), order.length - 1);
    setActive(order[active === null ? (forward ? 0 : order.length - 1) : next]);
  };

  const point = active === null ? null : points[active];
  const place = active === null ? null : placed[active];
  return (
    <div className="chart" ref={ref}>
      <svg width={width} height={height} role="group" aria-label={caption} tabIndex={0} onKeyDown={onKeyDown} onBlur={() => setActive(null)} onPointerLeave={() => setActive(null)}>
        <defs>
          <clipPath id={clipId}>
            <rect x={m.left} y={m.top} width={width - m.left - m.right} height={height - m.top - m.bottom} />
          </clipPath>
        </defs>
        {ticks.map((tick) => (
          <g key={tick}>
            <line className="grid" x1={m.left} x2={width - m.right} y1={y(Math.log10(tick))} y2={y(Math.log10(tick))} />
            <line className="grid" y1={m.top} y2={height - m.bottom} x1={x(Math.log10(tick))} x2={x(Math.log10(tick))} />
            <text className="tick" x={m.left - 6} y={y(Math.log10(tick))} textAnchor="end" dominantBaseline="middle">{tick}</text>
            <text className="tick" x={x(Math.log10(tick))} y={height - m.bottom + 14} textAnchor="middle">{tick}</text>
          </g>
        ))}
        <line className="axis" x1={m.left} x2={width - m.right} y1={height - m.bottom} y2={height - m.bottom} />
        <line className="axis" x1={m.left} x2={m.left} y1={m.top} y2={height - m.bottom} />
        <g clipPath={`url(#${clipId})`}>
          <polygon points={band} className="band" />
          <line className="diag" x1={x(Math.log10(d0))} y1={y(Math.log10(d0))} x2={x(Math.log10(d1))} y2={y(Math.log10(d1))} />
          {points.map((p, i) => (
            i === active ? null : <Marker key={i} shape={typeShape(p.type)} x={placed[i].x} y={placed[i].y} color={typeColor(p.type)} active={false} />
          ))}
          {point && place && <Marker shape={typeShape(point.type)} x={place.x} y={place.y} color={typeColor(point.type)} active />}
        </g>
        {!compact && <text className="label" x={width - m.right - 4} y={y(Math.log10(d1)) + 16} textAnchor="end">y = x: dự đoán đúng</text>}
        <text className="tick" x={(m.left + width - m.right) / 2} y={height - 6} textAnchor="middle">Thực tế (triệu/m²)</text>
        {!compact && <text className="tick" transform={`translate(12 ${(m.top + height - m.bottom) / 2}) rotate(-90)`} textAnchor="middle">Dự đoán (triệu/m²)</text>}
        <rect className="hit" x={m.left} y={m.top} width={width - m.left - m.right} height={height - m.top - m.bottom} onPointerMove={move} />
      </svg>
      {point && place && (
        <ChartTip x={place.x} y={place.y} width={width}>
          <TipRow color={typeColor(point.type)} value={`${formatNumber(point.actual, 1)} → ${formatNumber(point.predicted, 1)}`} label="thực tế → dự đoán (triệu/m²)" />
          <TipRow value={`${point.predicted >= point.actual ? "+" : "−"}${formatNumber(Math.abs(point.predicted / point.actual - 1) * 100, 0)}%`} label={`sai lệch · ${typeLabel(point.type)}`} />
        </ChartTip>
      )}
    </div>
  );
}
