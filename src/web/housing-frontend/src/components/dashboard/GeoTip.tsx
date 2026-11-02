import type { GeoPoint } from "../../api";
import { formatNumber, typeLabel } from "../../dashboard";
import { TipRow } from "./ChartTip";

/** Nội dung tooltip của một điểm: giá đậm trước, rồi diện tích, loại, tọa độ. */
export function GeoTip({ point, color }: { point: GeoPoint; color: string }) {
  return (
    <>
      <TipRow color={color} value={`${formatNumber(point.price_per_m2, 1)} triệu/m²`} label={typeLabel(point.type)} />
      <TipRow value={`${formatNumber(point.area, 0)} m²`} label="diện tích" />
      <TipRow value={`${formatNumber(point.lat, 4)}, ${formatNumber(point.lon, 4)}`} label="vĩ độ, kinh độ" />
    </>
  );
}
