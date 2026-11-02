import { useId, useMemo, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import type { GeoScatter } from "../../api";
import {
  PRICE_STOPS, areaQuantile, areaRadius, formatNumber, frameHeight, makeProjection, nearestPoint, priceColor,
  rangeTicks, visibleGeoPoints,
} from "../../dashboard";
import type { Bounds } from "../../dashboard";
import { useElementWidth } from "../../useElementWidth";
import { ChartTip } from "./ChartTip";
import { GeoTip } from "./GeoTip";

interface Props {
  geo: GeoScatter;
  bounds: Bounds;
  type: number | null; // chỉ để lọc, không mã hóa
  sizeByArea: boolean;
}

const FLAT_RADIUS = 3;

/**
 * Scatter phẳng kiểu notebook: x = kinh độ, y = vĩ độ (đúng tỉ lệ), màu = giá/m² (thang turbo, cắt p5–p95),
 * cỡ = √diện tích (cắt p95), chấm tròn bán trong suốt. Thang màu dọc và mốc cỡ nằm bên phải, trong cùng SVG.
 */
export function GeoPlot({ geo, bounds, type, sizeByArea }: Props) {
  const [ref, width] = useElementWidth<HTMLDivElement>(640);
  const [active, setActive] = useState<number | null>(null);
  const gradientId = useId();
  const clipId = useId();
  const narrow = width < 480;
  const M = { top: 8, right: 6, bottom: 38, left: narrow ? 46 : 54 };
  const barZone = narrow ? 66 : 92;
  const plotW = Math.max(width - M.left - M.right - barZone, 140);
  const proj = makeProjection(bounds, plotW, frameHeight(bounds, plotW, 200, 720));
  const left = M.left; // sát trục, thang màu ngay cạnh khung
  const right = left + proj.width;
  const base = M.top + proj.height;

  const points = useMemo(() => visibleGeoPoints(geo.points, bounds, type), [geo, bounds, type]);
  const cap = useMemo(() => areaQuantile(geo.points, 0.95), [geo]);
  // Khung nhỏ (điện thoại) thì chấm nhỏ lại để không che hết nhau.
  const shrink = plotW < 300 ? 0.7 : 1;
  const radius = (area: number) => shrink * (sizeByArea ? areaRadius(area, cap) : FLAT_RADIUS);
  const placed = useMemo(
    () => points.map((p) => ({ x: M.left + proj.x(p.lon), y: M.top + proj.y(p.lat) })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [points, width, bounds],
  );
  // Duyệt bằng bàn phím: ←/→ theo kinh độ, ↑/↓ theo vĩ độ.
  const orders = useMemo(() => {
    const ids = points.map((_, i) => i);
    return { lon: [...ids].sort((a, b) => points[a].lon - points[b].lon), lat: [...ids].sort((a, b) => points[a].lat - points[b].lat) };
  }, [points]);

  const move = (event: PointerEvent<SVGRectElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const index = nearestPoint(placed, event.clientX - box.left + left, event.clientY - box.top + M.top);
    setActive(index < 0 ? null : index);
  };
  const onKeyDown = (event: KeyboardEvent<SVGSVGElement>) => {
    const axis = ({ ArrowLeft: [-1, "lon"], ArrowRight: [1, "lon"], ArrowDown: [-1, "lat"], ArrowUp: [1, "lat"] } as Record<string, [number, "lon" | "lat"]>)[event.key];
    if (!axis || points.length === 0) return;
    event.preventDefault();
    const order = orders[axis[1]];
    const at = active === null ? -1 : order.indexOf(active);
    setActive(order[at < 0 ? (axis[0] > 0 ? 0 : order.length - 1) : Math.min(Math.max(at + axis[0], 0), order.length - 1)]);
  };

  // Thang màu dọc + mốc cỡ điểm bên phải khung.
  const { p5, p95 } = geo.price_clip;
  const barX = right + 14;
  const barTop = M.top + 22;
  const barH = Math.min(Math.max(proj.height - 22, 100), 240);
  const marks = [0, 0.25, 0.5, 0.75, 1];
  const sizeTop = barTop + barH + 46;
  const sizes = [areaQuantile(geo.points, 0.1), areaQuantile(geo.points, 0.5), cap];
  const totalH = Math.max(base + M.bottom, sizeByArea ? sizeTop + 3 * 24 : 0);

  const center = geo.center;
  const centerIn = center.lat >= bounds.lat[0] && center.lat <= bounds.lat[1] && center.lon >= bounds.lon[0] && center.lon <= bounds.lon[1];
  const point = active === null ? null : points[active];
  return (
    <div className="chart geo" ref={ref}>
      <svg
        width={width} height={totalH} role="group" tabIndex={0} onKeyDown={onKeyDown} onBlur={() => setActive(null)} onPointerLeave={() => setActive(null)}
        aria-label={`Giá/m² theo vị trí: ${formatNumber(points.length)} chấm. Mũi tên để duyệt từng điểm, hoặc dùng nút Xem bảng.`}
      >
        <defs>
          <clipPath id={clipId}><rect x={left} y={M.top} width={proj.width} height={proj.height} /></clipPath>
          <linearGradient id={gradientId} x1="0" y1="1" x2="0" y2="0">
            {PRICE_STOPS.map((color, i) => <stop key={color} offset={i / (PRICE_STOPS.length - 1)} stopColor={color} />)}
          </linearGradient>
        </defs>
        {rangeTicks(bounds.lat[0], bounds.lat[1], 5).map((tick) => (
          <g key={`lat-${tick}`}>
            <line className="grid" x1={left} x2={right} y1={M.top + proj.y(tick)} y2={M.top + proj.y(tick)} />
            <text className="tick" x={left - 6} y={M.top + proj.y(tick)} textAnchor="end" dominantBaseline="middle">{formatNumber(tick, 2)}°</text>
          </g>
        ))}
        {rangeTicks(bounds.lon[0], bounds.lon[1], Math.max(2, Math.round(proj.width / 90))).map((tick) => (
          <g key={`lon-${tick}`}>
            <line className="grid" y1={M.top} y2={base} x1={M.left + proj.x(tick)} x2={M.left + proj.x(tick)} />
            <text className="tick" x={M.left + proj.x(tick)} y={base + 14} textAnchor="middle">{formatNumber(tick, 2)}°</text>
          </g>
        ))}
        <rect className="frame" x={left} y={M.top} width={proj.width} height={proj.height} />
        <text className="tick" x={(left + right) / 2} y={base + 30} textAnchor="middle">Kinh độ</text>
        <text className="tick" transform={`translate(11 ${M.top + proj.height / 2}) rotate(-90)`} textAnchor="middle">Vĩ độ</text>
        <g clipPath={`url(#${clipId})`}>
          {points.map((p, i) => (
            <circle key={i} className="geo-dot" cx={placed[i].x} cy={placed[i].y} r={radius(p.area)} fill={priceColor(p.price_per_m2, geo.price_clip)} />
          ))}
          {point && active !== null && <circle className="geo-dot geo-dot--on" cx={placed[active].x} cy={placed[active].y} r={radius(point.area) + 2} />}
          {centerIn && (
            <g className="center" aria-label={center.name}>
              <circle cx={M.left + proj.x(center.lon)} cy={M.top + proj.y(center.lat)} r={7} />
              <path d={`M${M.left + proj.x(center.lon) - 4},${M.top + proj.y(center.lat)}h8M${M.left + proj.x(center.lon)},${M.top + proj.y(center.lat) - 4}v8`} />
            </g>
          )}
        </g>
        {centerIn && (
          <text
            className="label" y={M.top + proj.y(center.lat) - 8} textAnchor={proj.x(center.lon) > proj.width * 0.45 ? "end" : "start"}
            x={M.left + proj.x(center.lon) + (proj.x(center.lon) > proj.width * 0.45 ? -10 : 10)}
          >{center.name}</text>
        )}
        <rect className="hit" x={left} y={M.top} width={proj.width} height={proj.height} onPointerMove={move} />

        <text className="bar-title" x={barX} y={M.top + 8}>Giá/m²</text>
        <text className="tick" x={barX} y={M.top + 20}>triệu</text>
        <rect x={barX} y={barTop + 8} width={12} height={barH} rx={3} fill={`url(#${gradientId})`} role="img" aria-label={`Thang màu giá từ ${formatNumber(p5, 0)} đến ${formatNumber(p95, 0)} triệu/m²`} />
        {marks.map((t) => (
          <text key={t} className="tick" x={barX + 18} y={barTop + 8 + barH * (1 - t)} dominantBaseline="middle">
            {t === 0 ? "≤ " : t === 1 ? "≥ " : ""}{formatNumber(p5 + (p95 - p5) * t, 0)}
          </text>
        ))}
        {sizeByArea && (
          <g>
            <text className="bar-title" x={barX} y={sizeTop - 8}>Diện tích</text>
            {sizes.map((area, i) => (
              <g key={i}>
                <circle className="size-dot" cx={barX + 8} cy={sizeTop + 6 + i * 24} r={areaRadius(area, cap)} />
                <text className="tick" x={barX + 24} y={sizeTop + 6 + i * 24} dominantBaseline="middle">{i === 2 ? "≥ " : ""}{formatNumber(area, 0)} m²</text>
              </g>
            ))}
          </g>
        )}
      </svg>
      {point && active !== null && (
        <ChartTip x={placed[active].x} y={placed[active].y} width={width}>
          <GeoTip point={point} color={priceColor(point.price_per_m2, geo.price_clip)} />
        </ChartTip>
      )}
    </div>
  );
}
