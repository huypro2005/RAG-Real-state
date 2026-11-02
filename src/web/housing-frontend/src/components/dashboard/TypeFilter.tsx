import { typeColor, typeLabel, typeShape } from "../../dashboard";

/** Ký hiệu 12px của một loại nhà: cùng màu + hình với điểm trên scatter. */
export function TypeKey({ type }: { type: number }) {
  const color = typeColor(type);
  const body = {
    circle: <circle cx="6" cy="6" r="5" fill={color} />,
    square: <rect x="1" y="1" width="10" height="10" rx="1" fill={color} />,
    triangle: <path d="M6 0.5L11.5 11H0.5Z" fill={color} />,
    diamond: <path d="M6 0.5L11.5 6L6 11.5L0.5 6Z" fill={color} />,
    cross: <path d="M1.5 1.5L10.5 10.5M10.5 1.5L1.5 10.5" stroke={color} strokeWidth="2.2" strokeLinecap="round" />,
  }[typeShape(type)];
  return <svg className="typekey" width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">{body}</svg>;
}

const name = typeLabel;

/** Legend bật/tắt từng loại (hiện nhiều loại cùng lúc). */
export function TypeToggles({ types, hidden, onToggle }: { types: number[]; hidden: Set<number>; onToggle: (type: number) => void }) {
  return (
    <div className="chips" role="group" aria-label="Hiện hoặc ẩn từng loại nhà">
      {types.map((type) => (
        <button key={type} type="button" className="toggle" aria-pressed={!hidden.has(type)} onClick={() => onToggle(type)}>
          <TypeKey type={type} />{name(type)}
        </button>
      ))}
    </div>
  );
}

/** Chọn một loại nhà (hoặc tất cả) cho đường tham chiếu của histogram. */
export function TypeSelect({ types, value, onChange }: { types: number[]; value: number | null; onChange: (type: number | null) => void }) {
  return (
    <div className="chips" role="group" aria-label="Loại nhà của đường tham chiếu">
      <button type="button" className="toggle" aria-pressed={value === null} onClick={() => onChange(null)}>Tất cả</button>
      {types.map((type) => (
        <button key={type} type="button" className="toggle" aria-pressed={value === type} onClick={() => onChange(type)}>
          <TypeKey type={type} />{name(type)}
        </button>
      ))}
    </div>
  );
}
