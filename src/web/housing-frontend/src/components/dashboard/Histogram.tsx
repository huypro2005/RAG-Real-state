import { useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import type { PriceBin } from "../../api";
import { formatNumber, niceTicks, scaleLinear } from "../../dashboard";
import { useElementWidth } from "../../useElementWidth";
import { ChartTip, TipRow } from "./ChartTip";

interface Props {
  bins: (PriceBin & { share: number })[]; // đã sắp theo x0
  unit: string;
  color: string; // màu cột: màu loại nhà đang xem, hoặc trung tính khi xem tất cả
  median: number;
  p10: number;
  p90: number;
  caption: string; // mô tả cho trình đọc màn hình
}

const HEIGHT = 280;
const M = { top: 20, right: 12, bottom: 40, left: 44 };

/** Histogram phân bố giá/m². Cột sát nhau cách 2px; đường trung vị + dải p10–p90 là lớp tham chiếu. */
export function Histogram({ bins, unit, color, median, p10, p90, caption }: Props) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const [pointer, setPointer] = useState({ x: 0, y: 0 });
  if (bins.length === 0) return null;

  const xMax = bins[bins.length - 1].x1;
  const yTicks = niceTicks(Math.max(...bins.map((bin) => bin.count)), 4);
  const yMax = yTicks[yTicks.length - 1] || 1;
  const x = scaleLinear(bins[0].x0, xMax, M.left, width - M.right);
  const y = scaleLinear(0, yMax, HEIGHT - M.bottom, M.top);
  const inRange = (value: number) => value >= bins[0].x0 && value <= xMax;
  const xTicks = niceTicks(xMax, width < 420 ? 4 : 7).filter((tick) => tick <= xMax);

  const move = (event: PointerEvent<SVGRectElement>, index: number) => {
    const box = event.currentTarget.ownerSVGElement?.getBoundingClientRect();
    setActive(index);
    setPointer({ x: event.clientX - (box?.left ?? 0), y: event.clientY - (box?.top ?? 0) });
  };
  const onKeyDown = (event: KeyboardEvent<SVGSVGElement>) => {
    const keys: Record<string, number> = {
      ArrowRight: Math.min((active ?? -1) + 1, bins.length - 1), ArrowLeft: Math.max((active ?? 1) - 1, 0),
      Home: 0, End: bins.length - 1,
    };
    if (!(event.key in keys)) return;
    event.preventDefault();
    const index = keys[event.key];
    setActive(index);
    setPointer({ x: (x(bins[index].x0) + x(bins[index].x1)) / 2, y: y(bins[index].count) });
  };

  const bin = active === null ? null : bins[active];
  return (
    <div className="chart" ref={ref}>
      <svg
        width={width} height={HEIGHT} role="group" aria-label={caption} tabIndex={0}
        onKeyDown={onKeyDown} onBlur={() => setActive(null)} onPointerLeave={() => setActive(null)}
      >
        {yTicks.map((tick) => (
          <g key={tick}>
            <line className="grid" x1={M.left} x2={width - M.right} y1={y(tick)} y2={y(tick)} />
            <text className="tick" x={M.left - 8} y={y(tick)} textAnchor="end" dominantBaseline="middle">{formatNumber(tick)}</text>
          </g>
        ))}
        {inRange(p10) && inRange(p90) && (
          <rect x={x(p10)} y={M.top} width={x(p90) - x(p10)} height={HEIGHT - M.bottom - M.top} fill={color} opacity={0.1} />
        )}
        {bins.map((item, index) => {
          const left = x(item.x0) + 1;
          const w = Math.max(x(item.x1) - x(item.x0) - 2, 1);
          const top = y(item.count);
          const r = Math.min(4, w / 2, HEIGHT - M.bottom - top);
          const path = `M${left},${HEIGHT - M.bottom}V${top + r}Q${left},${top} ${left + r},${top}H${left + w - r}Q${left + w},${top} ${left + w},${top + r}V${HEIGHT - M.bottom}Z`;
          return item.count > 0 && <path key={item.x0} d={path} fill={color} className={index === active ? "mark mark--on" : "mark"} />;
        })}
        <line className="axis" x1={M.left} x2={width - M.right} y1={HEIGHT - M.bottom} y2={HEIGHT - M.bottom} />
        {xTicks.map((tick) => (
          <text key={tick} className="tick" x={x(tick)} y={HEIGHT - M.bottom + 16} textAnchor="middle">{formatNumber(tick)}</text>
        ))}
        <text className="tick" x={(M.left + width - M.right) / 2} y={HEIGHT - 6} textAnchor="middle">{`Giá mỗi m² (${unit})`}</text>
        {inRange(median) && (
          <g>
            <line className="ref" x1={x(median)} x2={x(median)} y1={M.top - 4} y2={HEIGHT - M.bottom} />
            <text className="label" x={x(median) + (x(median) > width * 0.7 ? -6 : 6)} y={M.top + 4} textAnchor={x(median) > width * 0.7 ? "end" : "start"}>
              {`Trung vị ${formatNumber(median, 1)}`}
            </text>
          </g>
        )}
        {bins.map((item, index) => (
          <rect
            key={item.x0} className="hit" x={x(item.x0)} y={M.top} width={x(item.x1) - x(item.x0)}
            height={HEIGHT - M.bottom - M.top} onPointerMove={(event) => move(event, index)}
            data-index={index}
          />
        ))}
      </svg>
      {bin && (
        <ChartTip x={pointer.x} y={pointer.y} width={width}>
          <TipRow color={color} value={`${formatNumber(bin.count)} tin (${formatNumber(bin.share * 100, 1)}%)`} label={`${formatNumber(bin.x0)} – ${formatNumber(bin.x1)} ${unit}`} />
        </ChartTip>
      )}
    </div>
  );
}
