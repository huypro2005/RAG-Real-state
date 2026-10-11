// Hàm định dạng thuần túy (có unit test). Cùng quy ước với backend: dấu phẩy thập phân.
import type { ListingHit, PoiType } from "./api";

export const POI_LABELS: Record<PoiType, string> = {
  truong_hoc: "Trường học",
  benh_vien: "Bệnh viện",
  cho: "Chợ",
};

const EXPIRING_DAYS = 3;

function trimNumber(value: number, digits: number): string {
  const text = value.toFixed(digits);
  const trimmed = text.includes(".") ? text.replace(/0+$/, "").replace(/\.$/, "") : text;
  return trimmed.replace(".", ",");
}

/** 2650 -> "2,65 tỷ", 900 -> "900 triệu" (đầu vào là triệu VND). */
export function formatPrice(millionVnd: number): string {
  if (millionVnd >= 1000) {
    return `${trimNumber(millionVnd / 1000, 3)} tỷ`;
  }
  return `${trimNumber(millionVnd, 3)} triệu`;
}

/** Đơn giá triệu VND/m², làm tròn 1 chữ số: 19.3133 -> "19,3 triệu/m²", 125 -> "125 triệu/m²". */
export function formatPricePerM2(millionVnd: number): string {
  if (millionVnd >= 1000) {
    return `${trimNumber(millionVnd / 1000, 2)} tỷ/m²`;
  }
  return `${trimNumber(millionVnd, 1)} triệu/m²`;
}

/** 166 -> "166 m", 1600 -> "1,6 km", 2000 -> "2 km". */
export function formatDistance(meters: number): string {
  if (meters < 1000) {
    return `${Math.round(meters)} m`;
  }
  return `${trimNumber(meters / 1000, 1)} km`;
}

/** "2026-09-20" -> "20/09/2026". Cắt chuỗi, không qua Date để khỏi lệch múi giờ. */
export function formatDate(iso: string | null): string {
  if (!iso) {
    return "";
  }
  const [year, month, day] = iso.slice(0, 10).split("-");
  return `${day}/${month}/${year}`;
}

/** Diện tích m²: 53 -> "53 m²", 46.6 -> "46,6 m²". */
export function formatArea(area: number): string {
  return `${trimNumber(area, 1)} m²`;
}

/** Nhãn cảnh báo của một tin (spec mục 3.4). */
export function listingWarnings(hit: ListingHit): string[] {
  const warnings: string[] = [];
  if (hit.days_left !== null) {
    if (hit.days_left < 0) {
      warnings.push("Tin đã hết hạn");
    } else if (hit.days_left <= EXPIRING_DAYS) {
      warnings.push(`Sắp hết hạn (còn ${hit.days_left} ngày)`);
    }
  }
  if (!hit.coords_reliable) {
    warnings.push("Tọa độ chưa đáng tin");
  }
  return warnings;
}

/** POI gần nhất trong các loại có số liệu, hoặc null nếu không có. */
export function nearestPoi(
  distances: ListingHit["poi_distances"],
): { type: PoiType; meters: number } | null {
  let best: { type: PoiType; meters: number } | null = null;
  for (const [type, meters] of Object.entries(distances) as [PoiType, number][]) {
    if (best === null || meters < best.meters) {
      best = { type, meters };
    }
  }
  return best;
}

/** Nhãn các trường của mode dự đoán giá (khóa như `PredictionTurn.fields` của backend). */
export const FIELD_LABELS: Record<string, string> = {
  property_type: "Loại nhà đất",
  district: "Quận/huyện",
  address: "Địa chỉ",
  area: "Diện tích",
  bedrooms: "Phòng ngủ",
  frontage: "Mặt tiền",
  floors: "Số tầng",
};

/** Giá trị một trường dự đoán để hiển thị: diện tích "60 m²", mặt tiền "4,5 m", còn lại giữ nguyên. */
export function formatField(key: string, value: string | number): string {
  if (typeof value !== "number") return value;
  if (key === "area") return formatArea(value);
  if (key === "frontage") return `${trimNumber(value, 1)} m`;
  return trimNumber(value, 1);
}

/** Khoảng giá tổng từ khoảng giá/m²: (55, 70, 60m²) -> "3,3 – 4,2 tỷ"; thiếu biên thì null. */
export function formatPriceRange(low: number | undefined, high: number | undefined, area: number): string | null {
  if (low === undefined || high === undefined || area <= 0) return null;
  const [from, to] = [formatPrice(low * area), formatPrice(high * area)];
  const sameUnit = from.endsWith(" tỷ") && to.endsWith(" tỷ");
  return sameUnit ? `${from.replace(" tỷ", "")} – ${to}` : `${from} – ${to}`;
}
