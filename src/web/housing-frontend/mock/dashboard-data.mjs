// Dữ liệu mẫu cho dashboard mô hình (docs/tasks/model-dashboard.md mục 1-2), sinh bằng PRNG có seed
// nên mỗi lần chạy mock ra cùng một bộ số. Hình dạng số liệu bám số đo thật: giá/m² trung vị ≈ 100 triệu,
// đuôi phải dài, R² log ≈ 0,83–0,86, MAE ≈ 31–34 triệu/m². Đây là số GIẢ, chỉ để dựng giao diện.

const TYPES = [
  { code: 0, label: "Căn hộ chung cư", share: 0.3, median: 70, sigma: 0.38 },
  { code: 2, label: "Nhà riêng", share: 0.38, median: 105, sigma: 0.4 },
  { code: 3, label: "Biệt thự, liền kề", share: 0.08, median: 120, sigma: 0.42 },
  { code: 4, label: "Nhà mặt phố", share: 0.14, median: 200, sigma: 0.5 },
  { code: 7, label: "Đất", share: 0.1, median: 80, sigma: 0.62 },
];

const FEATURES = [
  ["loại nhà đất", 0.43], ["cách trung tâm", 0.27], ["diện tích", 0.19], ["địa chỉ", 0.15],
  ["tọa độ x", 0.09], ["tọa độ y", 0.07], ["mặt tiền", 0.05], ["phòng ngủ", 0.03],
  ["số tầng", 0.012], ["số phòng vệ sinh", 0.004], ["đường vào", -0.002],
];

// Mỗi phiên bản: số dòng, mục tiêu R² log, độ lệch phần dư (chỉnh để MAE ≈ 31–34), số đặc trưng.
const VERSIONS = [
  { id: 7, seed: 107, created_at: "2026-10-31T08:00:00+07:00", trigger: "ingest", status: "skipped", is_active: false, best_candidate: null, train_rows: 5230, test_rows: 0, charts: false, metrics: null },
  { id: 6, seed: 106, created_at: "2026-10-31T09:30:00+07:00", trigger: "manual", status: "running", is_active: false, best_candidate: null, train_rows: null, test_rows: null, charts: false, metrics: null },
  { id: 5, seed: 105, created_at: "2026-10-30T09:12:00+07:00", trigger: "ingest", status: "failed", is_active: false, best_candidate: null, train_rows: 0, test_rows: 0, charts: false, metrics: null },
  { id: 4, seed: 104, created_at: "2026-10-28T20:41:00+07:00", trigger: "manual", status: "succeeded", is_active: false, best_candidate: "hist_gradient_boosting", train_rows: 5304, test_rows: 1121, charts: false, metrics: { r2_log: 0.848, mae: 31.9, mape: 0.236 } },
  { id: 3, seed: 103, created_at: "2026-10-24T10:05:00+07:00", trigger: "ingest", status: "succeeded", is_active: true, best_candidate: "extra_trees", train_rows: 5198, test_rows: 1102, charts: true, sigma: 0.163, features: 11, tail: 1.2 },
  { id: 2, seed: 102, created_at: "2026-10-12T15:30:00+07:00", trigger: "manual", status: "succeeded", is_active: false, best_candidate: "random_forest", train_rows: 4870, test_rows: 983, charts: true, sigma: 0.168, features: 10, tail: 1.3 },
  { id: 1, seed: 101, created_at: "2026-09-29T08:00:00+07:00", trigger: "bootstrap", status: "succeeded", is_active: false, best_candidate: "random_forest", train_rows: 4421, test_rows: 902, charts: true, sigma: 0.175, features: 9, tail: 1.4 },
];

// Sai số dự đoán lớn hơn ở nhà đắt (mặt phố, biệt thự) nên MAE tuyệt đối cao hơn dù R² log vẫn tốt.
const NOISE = { 0: 0.5, 2: 0.8, 3: 2.0, 4: 2.8, 7: 0.9 };

function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function normal(rand) {
  return Math.sqrt(-2 * Math.log(1 - rand())) * Math.cos(2 * Math.PI * rand());
}

function quantile(sorted, q) {
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  return sorted[lo] + (sorted[Math.ceil(pos)] - sorted[lo]) * (pos - lo);
}

const round = (value, digits = 1) => Number(value.toFixed(digits));

function draw(rand, n, tail) {
  const cumulative = [];
  let sum = 0;
  for (const type of TYPES) cumulative.push((sum += type.share));
  return Array.from({ length: n }, () => {
    const pick = rand();
    const type = TYPES[cumulative.findIndex((c) => pick <= c)] ?? TYPES[0];
    // Phân phối lognormal, thỉnh thoảng nhân thêm hệ số để đuôi phải dài như dữ liệu thật.
    const spike = rand() < 0.06 ? 1 + rand() * tail : 1;
    return { type: type.code, price: type.median * Math.exp(type.sigma * normal(rand)) * spike };
  });
}

function priceDistribution(rand, version) {
  const rows = draw(rand, version.train_rows, version.tail);
  const sorted = rows.map((row) => row.price).sort((a, b) => a - b);
  const p99 = quantile(sorted, 0.99);
  const width = [2, 5, 10, 20].find((w) => Math.ceil(p99 / w) <= 36) ?? 20;
  const count = Math.ceil(p99 / width);
  const bins = Array.from({ length: count }, (_, i) => ({ x0: i * width, x1: (i + 1) * width, count: 0 }));
  let clipped = 0;
  for (const price of sorted) {
    const index = Math.floor(price / width);
    if (index >= count) clipped += 1;
    else bins[index].count += 1;
  }
  const byType = {};
  for (const type of TYPES) {
    const own = rows.filter((row) => row.type === type.code).map((row) => row.price).sort((a, b) => a - b);
    byType[type.code] = {
      label: type.label, n: own.length, median: round(quantile(own, 0.5)),
      p10: round(quantile(own, 0.1)), p90: round(quantile(own, 0.9)),
    };
  }
  return {
    unit: "triệu/m²", bins, clipped_above: clipped,
    stats: {
      n: sorted.length, mean: round(sorted.reduce((a, b) => a + b, 0) / sorted.length),
      median: round(quantile(sorted, 0.5)), p10: round(quantile(sorted, 0.1)), p90: round(quantile(sorted, 0.9)),
    },
    by_type: byType,
  };
}

function scatter(rand, version) {
  const test = draw(rand, version.test_rows, version.tail);
  const points = test.map(({ type, price }) => ({
    actual: round(price), predicted: round(price * Math.exp(version.sigma * (NOISE[type] ?? 1) * normal(rand))),
    type, district: Math.floor(rand() * 24),
  }));
  const residuals = points.map((p) => Math.log(p.predicted) - Math.log(p.actual));
  const logs = points.map((p) => Math.log(p.actual));
  const mean = logs.reduce((a, b) => a + b, 0) / logs.length;
  const sst = logs.reduce((acc, v) => acc + (v - mean) ** 2, 0);
  const sse = residuals.reduce((acc, v) => acc + v * v, 0);
  const abs = points.map((p) => Math.abs(p.predicted - p.actual));
  const pct = points.map((p, i) => abs[i] / p.actual);
  const shown = points.sort(() => rand() - 0.5).slice(0, 800); // lấy mẫu có seed cố định
  return {
    points: shown, n_test: version.test_rows, r2_log: round(1 - sse / sst, 3),
    mae: round(abs.reduce((a, b) => a + b, 0) / abs.length), mape: round(pct.reduce((a, b) => a + b, 0) / pct.length, 3),
    residual_q90_log: round(quantile(residuals.map(Math.abs).sort((a, b) => a - b), 0.9), 3),
  };
}

function charts(version) {
  const rand = rng(version.seed);
  const distribution = priceDistribution(rand, version);
  const plot = scatter(rand, version);
  const items = FEATURES.slice(0, version.features).map(([feature, importance], i) => ({
    feature, importance: round(importance * (1 - 0.05 * (3 - version.id)), 3),
    std: round(Math.abs(importance) * 0.06 + 0.002 + i * 0.0004, 3),
  }));
  const chosen = version.best_candidate;
  const candidates = [
    ["extra_trees", 0.001], ["random_forest", 0], ["hist_gradient_boosting", -0.004], ["gradient_boosting", -0.012], ["ridge", -0.1],
  ].map(([name, shift]) => ({
    name, cv_r2: round(plot.r2_log - 0.008 + shift, 3), cv_std: round(0.008 + Math.abs(shift) * 0.05, 3),
    test_r2_log: round(plot.r2_log + shift - (name === chosen ? 0 : 0.002), 3),
    mae: round(plot.mae * (1 - shift * 3), 1), chosen: name === chosen,
  }));
  return {
    schema_version: 1, price_distribution: distribution, scatter: plot,
    feature_importance: { method: "permutation_r2_log", items }, district_type_median: districtTypeMedian(rand),
    // Phiên bản #1 giả lập "bản cũ chưa có geo_scatter" để thử trạng thái thiếu dữ liệu.
    ...(version.id > 1 ? { geo_scatter: geoScatter(rand, version) } : {}), candidates,
  };
}

const DISTRICTS = [
  ["Quận 1", 1.9], ["Quận 2", 1.35], ["Quận 3", 1.7], ["Quận 4", 1.1], ["Quận 5", 1.25], ["Quận 6", 0.85],
  ["Quận 7", 1.1], ["Quận 8", 0.8], ["Quận 9", 0.7], ["Quận 10", 1.3], ["Quận 11", 1.0], ["Quận 12", 0.65],
  ["Bình Thạnh", 1.15], ["Gò Vấp", 0.85], ["Phú Nhuận", 1.55], ["Tân Bình", 1.2], ["Tân Phú", 0.9],
  ["Bình Tân", 0.7], ["Thủ Đức", 0.8], ["Bình Chánh", 0.45], ["Hóc Môn", 0.4], ["Củ Chi", 0.3],
  ["Nhà Bè", 0.5], ["Cần Giờ", 0.25],
];

/** Trung vị theo quận × loại nhà; nhóm dưới 5 tin bị bỏ như spec. */
function districtTypeMedian(rand) {
  const rows = [];
  DISTRICTS.forEach(([name, factor], district) => {
    for (const type of TYPES) {
      const n = Math.floor(rand() * rand() * 220);
      if (n < 5) continue;
      rows.push({
        district, district_name: name, property_type: type.code, label: type.label,
        median: round(type.median * factor * Math.exp(0.12 * normal(rand))), n,
      });
    }
  });
  return rows;
}

// Tâm các quận [lat, lon, độ tản (độ), trọng số số tin, hệ số giá]: dày ở nội thành, đắt quanh Quận 1/3/Phú Nhuận.
const GEO = [
  [10.776, 106.700, 0.012, 9, 1.9], [10.784, 106.686, 0.010, 7, 1.7], [10.799, 106.680, 0.009, 6, 1.55],
  [10.811, 106.709, 0.014, 9, 1.15], [10.762, 106.667, 0.010, 6, 1.3], [10.754, 106.664, 0.009, 5, 1.25],
  [10.757, 106.705, 0.008, 4, 1.1], [10.734, 106.722, 0.014, 8, 1.1], [10.801, 106.653, 0.012, 8, 1.2],
  [10.838, 106.665, 0.014, 9, 0.85], [10.867, 106.654, 0.022, 7, 0.65], [10.850, 106.760, 0.028, 8, 0.8],
  [10.790, 106.740, 0.016, 5, 1.35], [10.840, 106.800, 0.030, 5, 0.7], [10.765, 106.600, 0.022, 6, 0.7],
  [10.790, 106.630, 0.012, 5, 0.9], [10.748, 106.635, 0.011, 4, 0.85], [10.722, 106.628, 0.014, 4, 0.8],
  [10.765, 106.650, 0.010, 4, 1.0], [10.680, 106.580, 0.040, 3, 0.45], [10.890, 106.590, 0.035, 2, 0.4],
  [10.970, 106.490, 0.050, 2, 0.3], [10.690, 106.740, 0.025, 2, 0.5], [10.410, 106.960, 0.060, 1, 0.25],
];

/** ≤ 1.200 điểm tọa độ × giá × diện tích, giá cao hơn gần tâm (Nhà thờ Đức Bà) và theo hệ số quận. */
function geoScatter(rand, version) {
  const center = { name: "Nhà thờ Đức Bà", lat: 10.7798, lon: 106.699 };
  const total = GEO.reduce((sum, g) => sum + g[3], 0);
  const points = Array.from({ length: 1200 }, () => {
    let pick = rand() * total;
    const g = GEO.find((item) => (pick -= item[3]) <= 0) ?? GEO[0];
    const type = TYPES[Math.min(Math.floor(rand() * rand() * 5.5), 4)];
    const lat = g[0] + g[2] * normal(rand);
    const lon = g[1] + g[2] * normal(rand);
    const km = Math.hypot((lat - center.lat) * 111, (lon - center.lon) * 109);
    const price = type.median * g[4] * Math.exp(0.22 * normal(rand)) * (1 + 0.5 * Math.exp(-km / 4));
    const area = type.code === 0 ? 45 + rand() * 60 : type.code === 7 ? 60 + rand() * 300 : 30 + rand() * rand() * 220;
    return { lat: round(lat, 5), lon: round(lon, 5), price_per_m2: round(price), area: round(area), type: type.code };
  });
  const prices = points.map((p) => p.price_per_m2).sort((a, b) => a - b);
  const lats = points.map((p) => p.lat);
  const lons = points.map((p) => p.lon);
  return {
    points, n_total: version.train_rows,
    bounds: { lat: [round(Math.min(...lats) - 0.01, 3), round(Math.max(...lats) + 0.01, 3)], lon: [round(Math.min(...lons) - 0.01, 3), round(Math.max(...lons) + 0.01, 3)] },
    price_clip: { p5: round(quantile(prices, 0.05)), p95: round(quantile(prices, 0.95)) },
    center,
  };
}

const CHARTS = new Map(VERSIONS.filter((v) => v.charts).map((v) => [v.id, charts(v)]));

function summary(version) {
  const own = CHARTS.get(version.id)?.scatter;
  const metrics = own ? { r2_log: own.r2_log, mae: own.mae, mape: own.mape } : version.metrics;
  return {
    id: version.id, created_at: version.created_at, trigger: version.trigger, status: version.status,
    is_active: version.is_active, best_candidate: version.best_candidate, train_rows: version.train_rows,
    test_rows: version.test_rows, metrics, has_charts: version.charts,
  };
}

export function dashboardList() {
  return VERSIONS.map(summary);
}

/** `ref` là id số hoặc "active"; trả null nếu không có phiên bản đó. */
export function dashboardDetail(ref) {
  const version = ref === "active" ? VERSIONS.find((v) => v.is_active) : VERSIONS.find((v) => String(v.id) === ref);
  if (!version) return null;
  return { ...summary(version), charts: CHARTS.get(version.id) ?? null };
}
