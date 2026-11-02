import { useState } from "react";
import type { KeyboardEvent } from "react";
import { formatNumber, niceTicks, scaleLinear, typeColor, typeLabel } from "../../dashboard";
import type { DistrictGroup } from "../../dashboard";
import { useElementWidth } from "../../useElementWidth";
import { ChartTip, TipRow } from "./ChartTip";

interface Props {
  groups: DistrictGroup[];
  types: number[]; // loại nhà đang hiện, theo thứ tự màu cố định
}

const HEIGHT = 300;

/** Cột nhóm: mỗi quận một nhóm, mỗi loại nhà một cột (màu theo thực thể). Giá trung vị, triệu/m². */
export function DistrictBars({ groups, types }: Props) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const slot = (width - 52 - 8) / Math.max(groups.length, 1);
  const rotate = slot < 64;
  const m = { top: 12, right: 8, bottom: rotate ? 64 : 36, left: 52 };
  const barW = Math.max(3, Math.min(18, (slot - 10) / Math.max(types.length, 1) - 2));
  const ticks = niceTicks(Math.max(1, ...groups.flatMap((g) => types.map((t) => g.values.get(t)?.median ?? 0))), 5);
  const top = ticks[ticks.length - 1] || 1;
  const y = scaleLinear(0, top, HEIGHT - m.bottom, m.top);
  const base = HEIGHT - m.bottom;

  const onKeyDown = (event: KeyboardEvent<SVGSVGElement>) => {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    setActive(Math.min(Math.max((active ?? (step > 0 ? -1 : groups.length)) + step, 0), groups.length - 1));
  };

  const group = active === null ? null : groups[active];
  const tipX = active === null ? 0 : m.left + slot * (active + 0.5);
  return (
    <div className="chart" ref={ref}>
      <svg width={width} height={HEIGHT} role="group" aria-label="Giá trung vị theo quận và loại nhà" tabIndex={0} onKeyDown={onKeyDown} onBlur={() => setActive(null)} onPointerLeave={() => setActive(null)}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line className="grid" x1={m.left} x2={width - m.right} y1={y(tick)} y2={y(tick)} />
            <text className="tick" x={m.left - 8} y={y(tick)} textAnchor="end" dominantBaseline="middle">{formatNumber(tick)}</text>
          </g>
        ))}
        {groups.map((g, gi) => {
          const left = m.left + slot * gi + (slot - types.length * (barW + 2) + 2) / 2;
          const cx = m.left + slot * (gi + 0.5);
          return (
            <g key={g.district} className={gi === active ? "group group--on" : "group"}>
              {types.map((type, ti) => {
                const value = g.values.get(type)?.median;
                if (value === undefined) return null;
                const r = Math.min(3, barW / 2);
                const x0 = left + ti * (barW + 2);
                const t = y(value);
                return <path key={type} className="mark" fill={typeColor(type)} d={`M${x0},${base}V${t + r}Q${x0},${t} ${x0 + r},${t}H${x0 + barW - r}Q${x0 + barW},${t} ${x0 + barW},${t + r}V${base}Z`} />;
              })}
              <text
                className="tick" x={cx} y={base + 16} textAnchor={rotate ? "end" : "middle"}
                transform={rotate ? `rotate(-40 ${cx} ${base + 16})` : undefined}
              >{g.name}</text>
              <rect className="hit" x={m.left + slot * gi} y={m.top} width={slot} height={base - m.top + 24} onPointerMove={() => setActive(gi)} />
            </g>
          );
        })}
        <line className="axis" x1={m.left} x2={width - m.right} y1={base} y2={base} />
      </svg>
      {group && (
        <ChartTip x={tipX} y={m.top + 20} width={width}>
          <div className="tip__title">{group.name}</div>
          {types.filter((t) => group.values.has(t)).map((t) => (
            <TipRow key={t} color={typeColor(t)} value={`${formatNumber(group.values.get(t)?.median ?? 0, 1)} triệu/m²`} label={`${typeLabel(t)} · ${formatNumber(group.values.get(t)?.n ?? 0)} tin`} />
          ))}
        </ChartTip>
      )}
    </div>
  );
}
