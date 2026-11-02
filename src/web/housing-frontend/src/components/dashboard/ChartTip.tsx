import type { ReactNode } from "react";

interface Props {
  x: number; // vị trí con trỏ trong khung biểu đồ (px)
  y: number;
  width: number; // bề rộng khung, để lật tooltip sang trái khi sát mép phải
  children: ReactNode;
}

/** Tooltip dùng chung: giá trị là chữ đậm, nhãn là chữ phụ; nội dung là React node nên không chèn HTML thô. */
export function ChartTip({ x, y, width, children }: Props) {
  const flip = x > width * 0.55;
  return (
    <div className={`tip${flip ? " tip--left" : ""}`} style={{ left: x, top: y }} role="status">
      {children}
    </div>
  );
}

/** Một dòng tooltip: nét ngắn màu series (không dùng ô vuông), giá trị đậm rồi nhãn. */
export function TipRow({ color, value, label }: { color?: string; value: string; label: string }) {
  return (
    <div className="tip__row">
      {color && <span className="tip__key" style={{ background: color }} aria-hidden="true" />}
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
