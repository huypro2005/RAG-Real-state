import { describe, expect, it } from "vitest";
import type { DashboardModelSummary, DistrictTypeMedian, GeoPoint } from "./api";
import {
  PRICE_STOPS, areaQuantile, areaRadius, defaultBounds, defaultVersion, extremes, findBin, formatDateTime, formatDelta, formatMetric,
  formatNumber, frameHeight, groupDistrictTypes, gridSummary, logDomain, logTicks, makeProjection, metricDelta,
  nearestPoint, niceTicks, orderedTypes, outsideCount, paginate, prepareBins, priceColor, priceFraction, rangeTicks,
  sentenceCase, statusBadge, summarizeScatter, trendSeries, typeColor, typeLabel, typeShape, typeSlot, visibleGeoPoints,
} from "./dashboard";

function model(id: number, overrides: Partial<DashboardModelSummary> = {}): DashboardModelSummary {
  return {
    id, created_at: `2026-10-${String(10 + id).padStart(2, "0")}T00:00:00Z`, trigger: "manual", status: "succeeded",
    is_active: false, best_candidate: "extra_trees", train_rows: 100, test_rows: 20,
    metrics: { r2_log: 0.8, mae: 30, mape: 0.2 }, has_charts: true, ...overrides,
  };
}

describe("màu theo loại nhà", () => {
  it("thứ tự cố định: căn hộ 0, nhà riêng 2, biệt thự 3, mặt phố 4, đất 7", () => {
    expect([0, 2, 3, 4, 7].map(typeColor)).toEqual([
      "var(--viz-1)", "var(--viz-2)", "var(--viz-3)", "var(--viz-4)", "var(--viz-5)",
    ]);
    expect(typeShape(0)).toBe("circle");
    expect(typeShape(7)).toBe("cross");
  });

  it("màu theo thực thể, không theo thứ hạng: bỏ bớt loại thì màu các loại còn lại giữ nguyên", () => {
    expect(typeSlot(4)).toBe(3);
    expect(orderedTypes([7, 4]).map(typeColor)).toEqual(["var(--viz-4)", "var(--viz-5)"]);
  });

  it("loại lạ dùng màu trung tính và xếp cuối", () => {
    expect(typeColor(99)).toBe("var(--viz-neutral)");
    expect(orderedTypes([99, 7, 0, 5])).toEqual([0, 7, 5, 99]);
  });
});

describe("histogram", () => {
  const bins = [{ x0: 0, x1: 20, count: 3 }, { x0: 20, x1: 40, count: 1 }];

  it("findBin: bin chứa giá trị, mép phải thuộc bin cuối, ngoài trục là -1", () => {
    expect(findBin(bins, 5)).toBe(0);
    expect(findBin(bins, 20)).toBe(1);
    expect(findBin(bins, 40)).toBe(1);
    expect(findBin(bins, 41)).toBe(-1);
    expect(findBin([], 1)).toBe(-1);
  });

  it("prepareBins sắp theo x0 và tính tỷ lệ", () => {
    const result = prepareBins([bins[1], bins[0]]);
    expect(result.map((bin) => bin.x0)).toEqual([0, 20]);
    expect(result[0].share).toBeCloseTo(0.75);
  });

  it("niceTicks và logTicks cho số tròn", () => {
    expect(niceTicks(317)).toEqual([0, 100, 200, 300, 400]);
    expect(niceTicks(300)).toEqual([0, 100, 200, 300]);
    expect(niceTicks(0)).toEqual([0]);
    expect(logTicks(8, 600)).toEqual([10, 20, 50, 100, 200, 500]);
    expect(logDomain([12, 640, 90])).toEqual([10, 1000]);
    expect(logDomain([21, 300])).toEqual([20, 500]);
  });
});

describe("metricDelta", () => {
  const a = { r2_log: 0.85, mae: 28, mape: 0.17 };
  const b = { r2_log: 0.83, mae: 30, mape: 0.17 };

  it("R² tăng là tốt hơn, MAE giảm là tốt hơn", () => {
    expect(metricDelta("r2_log", a, b)?.verdict).toBe("better");
    expect(metricDelta("mae", a, b)).toEqual({ delta: -2, verdict: "better" });
    expect(metricDelta("mae", b, a)?.verdict).toBe("worse");
  });

  it("chênh không đáng kể là ngang nhau; thiếu số đo là null", () => {
    expect(metricDelta("mape", a, b)?.verdict).toBe("same");
    expect(metricDelta("mae", a, null)).toBeNull();
    expect(metricDelta("mae", a, { ...b, mae: null })).toBeNull();
  });
});

describe("định dạng", () => {
  it("số và metric dùng dấu phẩy thập phân", () => {
    expect(formatNumber(5198)).toBe("5.198");
    expect(formatMetric("r2_log", 0.8321)).toBe("0,832");
    expect(formatMetric("mape", 0.172)).toBe("17,2%");
    expect(formatMetric("mae", null)).toBe("—");
  });

  it("Δ có dấu", () => {
    expect(formatDelta("r2_log", 0.012)).toBe("+0,012");
    expect(formatDelta("mae", -1.84)).toBe("−1,8");
    expect(formatDelta("mape", -0.005)).toBe("−0,5 điểm %");
  });

  it("thời điểm theo giờ Việt Nam", () => {
    expect(formatDateTime("2026-10-30T07:05:00Z")).toBe("14:05 30/10/2026");
    expect(formatDateTime("2026-10-30T20:05:00Z")).toBe("03:05 31/10/2026");
  });

  it("tên đặc trưng viết hoa chữ đầu, nhãn trạng thái", () => {
    expect(sentenceCase("loại nhà đất")).toBe("Loại nhà đất");
    expect(statusBadge("failed")).toEqual({ label: "Thất bại", tone: "bad" });
    expect(statusBadge("lạ").tone).toBe("muted");
  });
});

describe("dữ liệu theo phiên bản", () => {
  it("trendSeries xếp cũ → mới và bỏ bản không có metric", () => {
    const models = [model(3), model(1, { metrics: { r2_log: 0.7, mae: 40, mape: 0.3 } }), model(2, { metrics: null })];
    expect(trendSeries(models, "r2_log")).toEqual([{ id: 1, value: 0.7 }, { id: 3, value: 0.8 }]);
  });

  it("defaultVersion ưu tiên bản active, rồi bản có charts", () => {
    expect(defaultVersion([model(1), model(2, { is_active: true })])).toBe(2);
    expect(defaultVersion([model(1, { has_charts: false }), model(2)])).toBe(2);
    expect(defaultVersion([])).toBeNull();
  });

  it("paginate kẹp trang vào khoảng hợp lệ", () => {
    expect(paginate([1, 2, 3, 4, 5, 6], 2, 5)).toEqual({ rows: [6], pages: 2, page: 2 });
    expect(paginate([1, 2], 9, 5).page).toBe(1);
  });
});

describe("quận × loại nhà và scatter", () => {
  const rows: DistrictTypeMedian[] = [
    { district: 1, district_name: "Quận 1", property_type: 0, label: "Căn hộ", median: 150, n: 10 },
    { district: 1, district_name: "Quận 1", property_type: 2, label: "Nhà riêng", median: 300, n: 5 },
    { district: 2, district_name: "Quận 2", property_type: 0, label: "Căn hộ", median: 90, n: 40 },
  ];

  it("groupDistrictTypes gom theo quận, quận nhiều tin đứng đầu, cắt theo limit", () => {
    const groups = groupDistrictTypes(rows, 1);
    expect(groups).toHaveLength(1);
    expect(groups[0].name).toBe("Quận 2");
    const both = groupDistrictTypes(rows, 5);
    expect(both[1].values.get(2)).toEqual({ median: 300, n: 5 });
  });

  it("summarizeScatter tính trung vị và MAE từng loại", () => {
    const summary = summarizeScatter([
      { actual: 100, predicted: 90, type: 2, district: 0 },
      { actual: 200, predicted: 230, type: 2, district: 0 },
      { actual: 50, predicted: 50, type: 0, district: 0 },
    ]);
    expect(summary.map((row) => row.type)).toEqual([0, 2]);
    expect(summary[1]).toMatchObject({ n: 2, medianActual: 150, medianPredicted: 160, mae: 20 });
  });

  it("nearestPoint chọn điểm gần nhất trong bán kính", () => {
    const points = [{ x: 0, y: 0 }, { x: 10, y: 0 }];
    expect(nearestPoint(points, 8, 1)).toBe(1);
    expect(nearestPoint(points, 100, 100)).toBe(-1);
  });
});

describe("nhãn loại nhà", () => {
  it("mã 9 là Kho, nhà xưởng; mã lạ là Khác", () => {
    expect(typeLabel(9)).toBe("Kho, nhà xưởng");
    expect(typeLabel(0)).toBe("Căn hộ chung cư");
    expect(typeLabel(42)).toBe("Khác");
  });
});

describe("bản đồ giá theo vị trí", () => {
  const clip = { p5: 50, p95: 150 };
  const geo = (lat: number, lon: number, price: number, type = 0, area = 60): GeoPoint => ({ lat, lon, price_per_m2: price, area, type });
  const urban = { lat: [10.7, 10.9] as [number, number], lon: [106.6, 106.8] as [number, number] };

  it("priceFraction cắt ở p5–p95", () => {
    expect([10, 50, 100, 150, 900].map((p) => priceFraction(p, clip))).toEqual([0, 0, 0.5, 1, 1]);
    expect(priceFraction(80, { p5: 5, p95: 5 })).toBe(0);
  });

  it("priceColor: thang turbo, hai đầu là mốc đầu/cuối, giữa nội suy tuyến tính, ngoài p5–p95 bị cắt", () => {
    expect(priceColor(10, clip)).toBe(PRICE_STOPS[0]);
    expect(priceColor(50, clip)).toBe(PRICE_STOPS[0]);
    expect(priceColor(150, clip)).toBe(PRICE_STOPS[PRICE_STOPS.length - 1]);
    expect(priceColor(900, clip)).toBe(PRICE_STOPS[PRICE_STOPS.length - 1]);
    // t = 0,5 nằm đúng giữa mốc 3 và 4 (chỉ số 3 và 4 của 8 mốc, vì 0,5 * 7 = 3,5)
    expect(priceColor(100, clip)).toBe("#9df749");
    expect(priceColor(100, clip)).toMatch(/^#[0-9a-f]{6}$/);
  });

  it("areaRadius: theo căn bậc hai, cắt ở p95, nằm trong [2,5; 8]", () => {
    expect(areaRadius(0, 300)).toBe(2.5);
    expect(areaRadius(300, 300)).toBe(8);
    expect(areaRadius(5000, 300)).toBe(8);
    expect(areaRadius(75, 300)).toBeCloseTo(2.5 + 5.5 * 0.5);
  });

  it("areaQuantile bỏ diện tích không hợp lệ", () => {
    const points = [geo(0, 0, 1, 0, 10), geo(0, 0, 1, 0, 20), geo(0, 0, 1, 0, 0), geo(0, 0, 1, 0, 30)];
    expect(areaQuantile(points, 0.5)).toBe(20);
    expect(areaQuantile([], 0.5)).toBe(1);
  });

  it("defaultBounds: giới hạn trong vùng đô thị, hẹp hơn nếu dữ liệu hẹp", () => {
    const wide = [geo(10.3, 106.2, 1), geo(11.2, 107.2, 1), ...Array.from({ length: 98 }, (_, i) => geo(10.7 + i * 0.002, 106.6 + i * 0.002, 1))];
    const view = defaultBounds(wide);
    expect(view.lat[0]).toBeGreaterThanOrEqual(10.65);
    expect(view.lat[1]).toBeLessThanOrEqual(10.95);
    expect(view.lon[0]).toBeGreaterThanOrEqual(106.55);
    const narrow = defaultBounds(Array.from({ length: 50 }, (_, i) => geo(10.77 + i * 0.001, 106.69 + i * 0.001, 1)));
    expect(narrow.lat[1] - narrow.lat[0]).toBeLessThan(0.1);
  });

  it("frameHeight và makeProjection giữ tỉ lệ: kinh độ nhân cos(10,8°)", () => {
    const k = Math.cos((10.8 * Math.PI) / 180);
    const h = frameHeight(urban, 500, 0, 5000);
    expect(h / 500).toBeCloseTo(0.2 / (0.2 * k), 2);
    const p = makeProjection(urban, 500, h);
    expect(p.width).toBeCloseTo(500, 0);
    expect(p.y(10.9)).toBeCloseTo(0);
    expect(p.y(10.7)).toBeCloseTo(p.height);
    const squeezed = makeProjection(urban, 1000, 300);
    expect(squeezed.height).toBeCloseTo(300);
    expect(squeezed.width).toBeLessThan(1000);
    expect(squeezed.x(106.6)).toBeCloseTo(0);
  });

  it("rangeTicks", () => {
    expect(rangeTicks(10.7, 10.9, 4)).toEqual([10.7, 10.75, 10.8, 10.85, 10.9]);
  });

  it("visibleGeoPoints lọc theo loại và khung, xếp rẻ trước đắt sau; outsideCount đếm điểm ngoài khung", () => {
    const points = [geo(10.8, 106.7, 200), geo(10.8, 106.7, 50, 2), geo(10.8, 106.7, 100), geo(11.5, 106.7, 10)];
    expect(visibleGeoPoints(points, urban, null).map((p) => p.price_per_m2)).toEqual([50, 100, 200]);
    expect(visibleGeoPoints(points, urban, 2).map((p) => p.price_per_m2)).toEqual([50]);
    expect(outsideCount(points, urban, null)).toBe(1);
    expect(outsideCount(points, urban, 2)).toBe(0);
  });

  it("extremes lấy n điểm rẻ/đắt nhất; gridSummary gom theo ô và bỏ ô trống", () => {
    const points = [geo(10.8, 106.7, 10), geo(10.8, 106.7, 30), geo(10.8, 106.7, 20), geo(10.71, 106.61, 500)];
    const { cheapest, priciest } = extremes(points, 2);
    expect(cheapest.map((p) => p.price_per_m2)).toEqual([10, 20]);
    expect(priciest.map((p) => p.price_per_m2)).toEqual([500, 30]);
    const cells = gridSummary(points, urban, 2);
    expect(cells).toHaveLength(2);
    expect(cells[0]).toMatchObject({ n: 3, median: 20 });
    expect(cells[1]).toMatchObject({ n: 1, row: 1, col: 0 });
  });
});
