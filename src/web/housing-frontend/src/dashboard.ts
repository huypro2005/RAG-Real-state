// Phần tính toán/định dạng thuần túy của dashboard mô hình (có unit test, không đụng DOM).
import type { DashboardModelSummary, DistrictTypeMedian, GeoPoint, ModelMetrics, PriceBin, ScatterPoint } from "./api";

/** Thứ tự màu cố định theo loại nhà: căn hộ, nhà riêng, biệt thự/liền kề, mặt phố, đất = slot 1–5 của palette. */
export const TYPE_ORDER = [0, 2, 3, 4, 7] as const;
export const TYPE_NAMES: Record<number, string> = {
  0: "Căn hộ chung cư", 2: "Nhà riêng", 3: "Biệt thự, liền kề", 4: "Nhà mặt phố", 7: "Đất", 9: "Kho, nhà xưởng",
};

/** Nhãn hiển thị của một mã loại nhà; mã chưa biết là "Khác". */
export function typeLabel(code: number): string {
  return TYPE_NAMES[code] ?? "Khác";
}
/** Hình đi kèm màu (mã hóa thứ hai cho người mù màu; palette chỉ đủ 3 màu an toàn khi mọi cặp có thể kề nhau). */
export const TYPE_SHAPES = ["circle", "square", "triangle", "diamond", "cross"] as const;
export type TypeShape = (typeof TYPE_SHAPES)[number];

/** Vị trí 0–4 của loại nhà trong thứ tự cố định, hoặc -1 nếu là loại lạ. */
export function typeSlot(code: number): number {
  return (TYPE_ORDER as readonly number[]).indexOf(code);
}

/** Màu theo loại nhà (token CSS); loại lạ dùng màu trung tính. Màu theo thực thể, không theo thứ hạng. */
export function typeColor(code: number): string {
  const slot = typeSlot(code);
  return slot < 0 ? "var(--viz-neutral)" : `var(--viz-${slot + 1})`;
}

export function typeShape(code: number): TypeShape {
  return TYPE_SHAPES[Math.max(typeSlot(code), 0)];
}

/** Các mã loại nhà có trong dữ liệu, theo thứ tự cố định; loại lạ xếp cuối theo mã. */
export function orderedTypes(codes: Iterable<number>): number[] {
  const unique = [...new Set(codes)];
  const known = TYPE_ORDER.filter((code) => unique.includes(code));
  return [...known, ...unique.filter((code) => typeSlot(code) < 0).sort((a, b) => a - b)];
}

/** Tick "đẹp" (1/2/5 × 10^k) từ 0 và phủ hết [0, max]: tick cuối luôn ≥ max để cột không tràn khung. */
export function niceTicks(max: number, target = 5): number[] {
  if (!(max > 0)) return [0];
  const raw = max / target;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = ([1, 2, 5, 10].find((m) => m * magnitude >= raw) ?? 10) * magnitude;
  return Array.from({ length: Math.ceil(max / step - 1e-9) + 1 }, (_, i) => Number((i * step).toFixed(10)));
}

/** Tick 1–2–5 cho trục log trong [min, max]. */
export function logTicks(min: number, max: number): number[] {
  const ticks: number[] = [];
  for (let k = Math.floor(Math.log10(min)); 10 ** k <= max; k += 1) {
    for (const m of [1, 2, 5]) {
      const value = m * 10 ** k;
      if (value >= min && value <= max) ticks.push(value);
    }
  }
  return ticks;
}

/** Biên trục log theo các mốc 1–2–5 phủ hết dữ liệu (vd. 12…640 -> 10…1000), để trục không phình vì vài điểm. */
export function logDomain(values: number[]): [number, number] {
  const [lo, hi] = [Math.min(...values), Math.max(...values)];
  const ticks = logTicks(10 ** (Math.floor(Math.log10(lo)) - 1), 10 ** (Math.ceil(Math.log10(hi)) + 1));
  return [Math.max(...ticks.filter((t) => t <= lo)), Math.min(...ticks.filter((t) => t >= hi))];
}

/** Hàm tuyến tính domain → range. */
export function scaleLinear(d0: number, d1: number, r0: number, r1: number): (value: number) => number {
  return (value) => r0 + ((value - d0) / (d1 - d0)) * (r1 - r0);
}

/** Chỉ số bin chứa `value` (bin cuối gồm cả mép phải), -1 nếu ngoài trục. */
export function findBin(bins: PriceBin[], value: number): number {
  if (bins.length === 0 || value < bins[0].x0 || value > bins[bins.length - 1].x1) return -1;
  const index = bins.findIndex((bin) => value >= bin.x0 && value < bin.x1);
  return index >= 0 ? index : bins.length - 1;
}

/** Bin đã sắp theo x0 (backend không đảm bảo thứ tự) kèm tỷ lệ trên tổng số tin trong biểu đồ. */
export function prepareBins(bins: PriceBin[]): (PriceBin & { share: number })[] {
  const sorted = [...bins].sort((a, b) => a.x0 - b.x0);
  const total = sorted.reduce((sum, bin) => sum + bin.count, 0);
  return sorted.map((bin) => ({ ...bin, share: total > 0 ? bin.count / total : 0 }));
}

/** Điểm gần con trỏ nhất trong bán kính `radius` px (lớp "Voronoi" cho scatter dày); -1 nếu không có. */
export function nearestPoint(points: { x: number; y: number }[], px: number, py: number, radius = 24): number {
  let best = -1;
  let bestDist = radius * radius;
  points.forEach((point, index) => {
    const dist = (point.x - px) ** 2 + (point.y - py) ** 2;
    if (dist <= bestDist) {
      best = index;
      bestDist = dist;
    }
  });
  return best;
}

export type MetricKey = "r2_log" | "mae" | "mape";
/** R² càng cao càng tốt; MAE, MAPE càng thấp càng tốt. */
const HIGHER_IS_BETTER: Record<MetricKey, boolean> = { r2_log: true, mae: false, mape: false };

export type Verdict = "better" | "worse" | "same";

/** Δ = A − B của một metric và A tốt hơn/kém hơn/ngang B; null nếu thiếu số liệu. */
export function metricDelta(
  key: MetricKey, a: ModelMetrics | null, b: ModelMetrics | null,
): { delta: number; verdict: Verdict } | null {
  const [x, y] = [a?.[key], b?.[key]];
  if (x == null || y == null) return null;
  const delta = x - y;
  const tolerance = key === "mae" ? 0.05 : 0.0005;
  if (Math.abs(delta) < tolerance) return { delta, verdict: "same" };
  return { delta, verdict: delta > 0 === HIGHER_IS_BETTER[key] ? "better" : "worse" };
}

/** Chuỗi theo thời gian (cũ → mới) của một metric, bỏ phiên bản chưa có số đo. */
export function trendSeries(models: DashboardModelSummary[], key: MetricKey): { id: number; value: number }[] {
  return models
    .filter((model) => model.metrics?.[key] != null)
    .sort((a, b) => a.created_at.localeCompare(b.created_at))
    .map((model) => ({ id: model.id, value: model.metrics?.[key] as number }));
}

export interface DistrictGroup {
  district: number;
  name: string;
  total: number;
  values: Map<number, { median: number; n: number }>;
}

/** Gom danh sách phẳng quận × loại nhà thành từng quận, xếp theo số tin giảm dần, lấy `limit` quận đầu. */
export function groupDistrictTypes(rows: DistrictTypeMedian[], limit: number): DistrictGroup[] {
  const groups = new Map<number, DistrictGroup>();
  for (const row of rows) {
    const group = groups.get(row.district) ?? { district: row.district, name: row.district_name, total: 0, values: new Map() };
    group.total += row.n;
    group.values.set(row.property_type, { median: row.median, n: row.n });
    groups.set(row.district, group);
  }
  return [...groups.values()].sort((a, b) => b.total - a.total).slice(0, limit);
}

/** Tóm tắt thực tế/dự đoán theo loại nhà (bảng thay thế của scatter). */
export function summarizeScatter(points: ScatterPoint[]) {
  const middle = (values: number[]) => {
    const sorted = [...values].sort((a, b) => a - b);
    const half = sorted.length >> 1;
    return sorted.length % 2 ? sorted[half] : (sorted[half - 1] + sorted[half]) / 2;
  };
  return orderedTypes(points.map((p) => p.type)).map((type) => {
    const own = points.filter((p) => p.type === type);
    return {
      type, n: own.length,
      medianActual: middle(own.map((p) => p.actual)),
      medianPredicted: middle(own.map((p) => p.predicted)),
      mae: own.reduce((sum, p) => sum + Math.abs(p.predicted - p.actual), 0) / own.length,
    };
  });
}

export function paginate<T>(items: T[], page: number, size: number): { rows: T[]; pages: number; page: number } {
  const pages = Math.max(1, Math.ceil(items.length / size));
  const current = Math.min(Math.max(page, 1), pages);
  return { rows: items.slice((current - 1) * size, current * size), pages, page: current };
}

// ---- Định dạng (dấu phẩy thập phân, như format.ts) ----

const vnNumber = (digits: number) => new Intl.NumberFormat("vi-VN", { minimumFractionDigits: digits, maximumFractionDigits: digits });

/** 5198 -> "5.198", 0.8321 (2 chữ số) -> "0,83". */
export function formatNumber(value: number, digits = 0): string {
  return vnNumber(digits).format(value);
}

/** Giá trị metric để hiện: R² "0,832", MAE "27,8", MAPE "17,0%"; thiếu thì "—". */
export function formatMetric(key: MetricKey, value: number | null | undefined): string {
  if (value == null) return "—";
  if (key === "r2_log") return formatNumber(value, 3);
  if (key === "mape") return `${formatNumber(value * 100, 1)}%`;
  return formatNumber(value, 1);
}

/** Δ có dấu: "+0,012", "−1,8", "−0,5 điểm %" cho MAPE. */
export function formatDelta(key: MetricKey, delta: number): string {
  const sign = delta > 0 ? "+" : delta < 0 ? "−" : "";
  const magnitude = Math.abs(delta);
  if (key === "r2_log") return `${sign}${formatNumber(magnitude, 3)}`;
  if (key === "mape") return `${sign}${formatNumber(magnitude * 100, 1)} điểm %`;
  return `${sign}${formatNumber(magnitude, 1)}`;
}

/** ISO -> "14:05 30/10/2026" theo giờ Việt Nam, bất kể múi giờ máy. */
export function formatDateTime(iso: string): string {
  const parts = new Intl.DateTimeFormat("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh", day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return `${get("hour")}:${get("minute")} ${get("day")}/${get("month")}/${get("year")}`;
}

/** "loại nhà đất" -> "Loại nhà đất" (tên đặc trưng của server viết thường). */
export function sentenceCase(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const TRIGGERS: Record<string, string> = { bootstrap: "Khởi tạo", ingest: "Nạp dữ liệu mới", manual: "Thủ công" };
export function triggerLabel(trigger: string): string {
  return TRIGGERS[trigger] ?? trigger;
}

export type Tone = "ok" | "info" | "bad" | "muted";
const STATUSES: Record<string, { label: string; tone: Tone }> = {
  succeeded: { label: "Thành công", tone: "ok" },
  success: { label: "Thành công", tone: "ok" },
  running: { label: "Đang huấn luyện", tone: "info" },
  failed: { label: "Thất bại", tone: "bad" },
  skipped: { label: "Bỏ qua", tone: "muted" },
};
/** Huy hiệu trạng thái: chữ + biểu tượng đi kèm màu (không dùng màu một mình). */
export function statusBadge(status: string): { label: string; tone: Tone } {
  return STATUSES[status] ?? { label: status, tone: "muted" };
}

/** Phiên bản mặc định khi mở dashboard: bản đang chạy, không có thì bản thành công mới nhất, rồi bản đầu danh sách. */
export function defaultVersion(models: DashboardModelSummary[]): number | null {
  const pick = models.find((m) => m.is_active) ?? models.find((m) => m.has_charts) ?? models[0];
  return pick?.id ?? null;
}

// ---- Bản đồ giá theo vị trí (geo_scatter) ----

/** Vĩ độ TP.HCM: kinh độ phải nhân cos(vĩ độ) thì khoảng cách ngang mới đúng tỉ lệ. */
const COS_LAT = Math.cos((10.8 * Math.PI) / 180);

export interface Bounds { lat: [number, number]; lon: [number, number] }

/** Vùng đô thị chính (mặc định); "Toàn TP.HCM" dùng bounds của server. */
export const URBAN_BOUNDS: Bounds = { lat: [10.65, 10.95], lon: [106.55, 106.85] };

function quantile(sorted: number[], q: number): number {
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  return sorted[lo] + (sorted[Math.ceil(pos)] - sorted[lo]) * (pos - lo);
}

/** Vị trí 0–1 của giá trên thang, cắt ở [p5, p95] để ngoại lai không làm thang bị dồn về một đầu. */
export function priceFraction(price: number, clip: { p5: number; p95: number }): number {
  if (clip.p95 <= clip.p5) return 0;
  return Math.min(1, Math.max(0, (price - clip.p5) / (clip.p95 - clip.p5)));
}

/**
 * Thang màu cầu vồng kiểu "turbo" (xanh dương → lơ → lục → vàng → cam → đỏ), theo yêu cầu người dùng
 * giống plot của notebook. Bỏ hai đầu quá tối của turbo để điểm rẻ vẫn thấy được trên nền tối.
 */
export const PRICE_STOPS = ["#4662d7", "#36aaf9", "#1ae4b6", "#72fe5e", "#c7ef34", "#faba39", "#f66b19", "#ca2a04"];

/** Màu của một mức giá: nội suy tuyến tính trong RGB giữa hai mốc kề nhau của PRICE_STOPS. */
export function priceColor(price: number, clip: { p5: number; p95: number }): string {
  const t = priceFraction(price, clip) * (PRICE_STOPS.length - 1);
  const k = Math.min(PRICE_STOPS.length - 2, Math.floor(t));
  const channel = (hex: string, i: number) => parseInt(hex.slice(1 + 2 * i, 3 + 2 * i), 16);
  const rgb = [0, 1, 2].map((i) => Math.round(channel(PRICE_STOPS[k], i) + (channel(PRICE_STOPS[k + 1], i) - channel(PRICE_STOPS[k], i)) * (t - k)));
  return "#" + rgb.map((v) => v.toString(16).padStart(2, "0")).join("");
}

/** Bán kính điểm (px) theo √diện tích, cắt ở `cap` (p95) để vài lô đất khổng lồ không che hết bản đồ. */
export function areaRadius(area: number, cap: number, min = 2.5, max = 8): number {
  if (!(area > 0) || !(cap > 0)) return min;
  return min + (max - min) * Math.sqrt(Math.min(area, cap) / cap);
}

/** Phân vị diện tích (q trong 0–1) của các điểm có diện tích hợp lệ. */
export function areaQuantile(points: GeoPoint[], q: number): number {
  const areas = points.map((p) => p.area).filter((a) => a > 0).sort((a, b) => a - b);
  return areas.length ? quantile(areas, q) : 1;
}

/**
 * Khung mặc định: phân vị 1–99 của toạ độ (bỏ vài điểm xa), giới hạn trong vùng đô thị chính,
 * đệm 3%. Nếu dữ liệu hẹp hơn vùng đô thị thì lấy khung hẹp.
 */
export function defaultBounds(points: GeoPoint[], limit: Bounds = URBAN_BOUNDS): Bounds {
  const span = (values: number[], [lo, hi]: [number, number]): [number, number] => {
    if (values.length < 2) return [lo, hi];
    const sorted = [...values].sort((a, b) => a - b);
    const pad = (quantile(sorted, 0.99) - quantile(sorted, 0.01)) * 0.03 + 0.005;
    return [Math.max(lo, quantile(sorted, 0.01) - pad), Math.min(hi, quantile(sorted, 0.99) + pad)];
  };
  return { lat: span(points.map((p) => p.lat), limit.lat), lon: span(points.map((p) => p.lon), limit.lon) };
}

const inBounds = (p: GeoPoint, b: Bounds) => p.lat >= b.lat[0] && p.lat <= b.lat[1] && p.lon >= b.lon[0] && p.lon <= b.lon[1];

/** Điểm trong khung và đúng loại nhà (null = tất cả), xếp rẻ trước – đắt sau để điểm đắt không bị che. */
export function visibleGeoPoints(points: GeoPoint[], bounds: Bounds, type: number | null): GeoPoint[] {
  return points
    .filter((p) => (type === null || p.type === type) && inBounds(p, bounds))
    .sort((a, b) => a.price_per_m2 - b.price_per_m2);
}

/** Số điểm (đúng loại nhà) nằm ngoài khung hiện tại. */
export function outsideCount(points: GeoPoint[], bounds: Bounds, type: number | null): number {
  return points.filter((p) => (type === null || p.type === type) && !inBounds(p, bounds)).length;
}

/** Chiều cao khung (px) để vừa chiều rộng `width` mà đúng tỉ lệ (kinh độ nhân cos vĩ độ). */
export function frameHeight(bounds: Bounds, width: number, min = 240, max = 760): number {
  const ratio = (bounds.lat[1] - bounds.lat[0]) / ((bounds.lon[1] - bounds.lon[0]) * COS_LAT);
  return Math.round(Math.min(max, Math.max(min, width * ratio)));
}

/** Chiếu (lon, lat) lên khung `width` × `height` (đã đúng tỉ lệ qua frameHeight); lệch nhỏ thì co đều hai trục, căn sát góc trái. */
export function makeProjection(bounds: Bounds, width: number, height: number) {
  const spanX = (bounds.lon[1] - bounds.lon[0]) * COS_LAT;
  const spanY = bounds.lat[1] - bounds.lat[0];
  const scale = Math.min(width / spanX, height / spanY);
  const [w, h] = [spanX * scale, spanY * scale];
  const offsetX = 0;
  return {
    width: w, height: h, scale, offsetX,
    x: (lon: number) => offsetX + (lon - bounds.lon[0]) * COS_LAT * scale,
    y: (lat: number) => (bounds.lat[1] - lat) * scale,
  };
}

/** Tick đều trên đoạn [min, max] với bước 1/2/5 × 10^k (vd. độ vĩ/kinh). */
export function rangeTicks(min: number, max: number, target = 5): number[] {
  const raw = (max - min) / target;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = ([1, 2, 5, 10].find((m) => m * magnitude >= raw * (1 - 1e-9)) ?? 10) * magnitude;
  const ticks: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) ticks.push(Number(v.toFixed(6)));
  return ticks;
}

/** n điểm rẻ nhất và n điểm đắt nhất (bảng thay thế). */
export function extremes(points: GeoPoint[], n: number): { cheapest: GeoPoint[]; priciest: GeoPoint[] } {
  const sorted = [...points].sort((a, b) => a.price_per_m2 - b.price_per_m2);
  return { cheapest: sorted.slice(0, n), priciest: sorted.slice(-n).reverse() };
}

/** Tóm tắt theo ô lưới `cells` × `cells` phủ bounds: số điểm và giá trung vị, bỏ ô trống; xếp theo số điểm giảm dần. */
export function gridSummary(points: GeoPoint[], bounds: Bounds, cells: number) {
  const [dLat, dLon] = [(bounds.lat[1] - bounds.lat[0]) / cells, (bounds.lon[1] - bounds.lon[0]) / cells];
  const buckets = new Map<string, number[]>();
  for (const p of points) {
    const row = Math.min(cells - 1, Math.max(0, Math.floor((bounds.lat[1] - p.lat) / dLat)));
    const col = Math.min(cells - 1, Math.max(0, Math.floor((p.lon - bounds.lon[0]) / dLon)));
    const key = `${row},${col}`;
    buckets.set(key, [...(buckets.get(key) ?? []), p.price_per_m2]);
  }
  return [...buckets.entries()].map(([key, prices]) => {
    const [row, col] = key.split(",").map(Number);
    const sorted = prices.sort((a, b) => a - b);
    const half = sorted.length >> 1;
    return {
      row, col, n: sorted.length,
      median: sorted.length % 2 ? sorted[half] : (sorted[half - 1] + sorted[half]) / 2,
      lat: bounds.lat[1] - (row + 0.5) * dLat, lon: bounds.lon[0] + (col + 0.5) * dLon,
    };
  }).sort((a, b) => b.n - a.n);
}
