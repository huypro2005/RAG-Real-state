import type { PropertyKind } from "../format";

// Hình nét đơn sắc theo loại nhà, thay cho ảnh khi tin chưa có ảnh (không dùng ảnh giả).
const SHAPES: Record<PropertyKind, JSX.Element> = {
  apartment: (
    <>
      <path d="M14 46V12h20v34M34 22h10v24" />
      <path d="M19 18h3M26 18h3M19 25h3M26 25h3M19 32h3M26 32h3M38 28h2M38 35h2M22 46v-6h4v6" />
    </>
  ),
  house: (
    <>
      <path d="M10 26 28 12l18 14M15 22v24h26V22" />
      <path d="M24 46V35h8v11M19 28h4M33 28h4" />
    </>
  ),
  villa: (
    <>
      <path d="M6 28 20 18l14 10M10 25v21h40V30M34 28l8-6 10 8" />
      <path d="M16 46v-8h6v8M28 34h4M40 34h4M6 46h48" />
    </>
  ),
  land: (
    <>
      <path d="M8 40 20 18h22l10 22Z" />
      <path d="M14 29h33M24 18l-4 22M37 18l3 22" />
      <path d="M28 10v8M28 10l6 2-6 2" />
    </>
  ),
};

export function PropertyThumb({ kind }: { kind: PropertyKind }) {
  return (
    <svg className="thumb__art" viewBox="0 0 56 56" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      {SHAPES[kind]}
    </svg>
  );
}
