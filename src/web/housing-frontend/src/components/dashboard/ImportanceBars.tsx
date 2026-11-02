import { useState } from "react";
import type { FeatureImportanceItem } from "../../api";
import { formatNumber, sentenceCase } from "../../dashboard";
import { ChartTip, TipRow } from "./ChartTip";

/** Thanh ngang độ quan trọng đặc trưng: một màu (cùng một đại lượng), sắp giảm dần, nhãn giá trị ngay đầu thanh. */
export function ImportanceBars({ items }: { items: FeatureImportanceItem[] }) {
  const [active, setActive] = useState<number | null>(null);
  const max = Math.max(...items.map((item) => item.importance), 1e-9);
  const item = active === null ? null : items[active];

  return (
    <div className="chart">
      <ul className="bars" aria-label="Độ quan trọng đặc trưng">
        {items.map((entry, index) => (
          <li
            key={entry.feature} tabIndex={0} className={index === active ? "bars__row bars__row--on" : "bars__row"}
            onPointerEnter={() => setActive(index)} onPointerLeave={() => setActive(null)}
            onFocus={() => setActive(index)} onBlur={() => setActive(null)}
          >
            <span className="bars__name">{sentenceCase(entry.feature)}</span>
            <span className="bars__track">
              <span className="bars__bar" style={{ width: `${(Math.max(entry.importance, 0) / max) * 82}%` }} />
              <span className="bars__value">{formatNumber(entry.importance, 3)}</span>
            </span>
          </li>
        ))}
      </ul>
      {item && (
        <ChartTip x={170} y={(active ?? 0) * 33 + 8} width={600}>
          <TipRow value={`${formatNumber(item.importance, 3)} ± ${formatNumber(item.std, 3)}`} label={`${sentenceCase(item.feature)}: giảm R² log khi xáo trộn`} />
        </ChartTip>
      )}
    </div>
  );
}
