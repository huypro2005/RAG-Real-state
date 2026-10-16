// Server giả theo hợp đồng docs/tasks/chatbot-recommendation.md mục 1 (Node thuần, không thư viện).
// Chạy: npm run mock  (cổng 8000, đổi bằng PORT). Dữ liệu là 5 tin mẫu ở TP.HCM.
import { createServer } from "node:http";
import { randomUUID } from "node:crypto";

const PORT = Number(process.env.PORT ?? 8000);
const TODAY = new Date();

function day(offset) {
  const d = new Date(TODAY.getTime() + offset * 86400000);
  return d.toISOString().slice(0, 10);
}

// Giá triệu VND, diện tích m², khoảng cách mét (như bảng listings).
const LISTINGS = [
  {
    listing_id: "mock-1", title: "Căn hộ Sunrise Riverside 2PN, view sông, full nội thất",
    price: 2650, area: 69, property_type: "Căn hộ chung cư", bedrooms: 2, district_old: "Quận 7",
    old_address: "Đường Nguyễn Hữu Thọ, Xã Phước Kiển, Huyện Nhà Bè",
    new_address: "Xã Nhà Bè, TP. Hồ Chí Minh", listing_url: "https://batdongsan.com.vn/mock-1",
    posted_at: day(-10), expired_at: day(20), poi_distances: { cho: 166, truong_hoc: 420 },
    latitude: 10.7098, longitude: 106.7305, coords_reliable: true, days_left: 20,
  },
  {
    listing_id: "mock-2", title: "Nhà riêng hẻm xe hơi Phan Văn Trị, 4x15m, 3 tầng",
    price: 5200, area: 60, property_type: "Nhà riêng", bedrooms: 4, district_old: "Gò Vấp",
    old_address: "Đường Phan Văn Trị, Phường 5, Quận Gò Vấp",
    new_address: "Phường Gò Vấp, TP. Hồ Chí Minh", listing_url: "https://batdongsan.com.vn/mock-2",
    posted_at: day(-3), expired_at: day(2), poi_distances: { benh_vien: 900, cho: 1600 },
    latitude: 10.8236, longitude: 106.6879, coords_reliable: true, days_left: 2,
  },
  {
    listing_id: "mock-3", title: "Bán căn hộ Vinhomes Central Park 1PN tầng cao",
    price: 900, area: 46.6, property_type: "Căn hộ chung cư", bedrooms: 1, district_old: "Bình Thạnh",
    old_address: "Đường Nguyễn Hữu Cảnh, Phường 22, Quận Bình Thạnh",
    new_address: "Phường Thạnh Mỹ Tây, TP. Hồ Chí Minh", listing_url: "https://batdongsan.com.vn/mock-3",
    posted_at: day(-20), expired_at: day(10), poi_distances: { truong_hoc: 350 },
    latitude: 10.7942, longitude: 106.7218, coords_reliable: false, days_left: 10,
  },
  {
    listing_id: "mock-4", title: "Nhà phố khu Thảo Điền, 5x20m, gần trường quốc tế",
    price: 12500, area: 100, property_type: "Nhà mặt phố", bedrooms: 5, district_old: "Quận 2",
    old_address: "Đường Xuân Thủy, Phường Thảo Điền, Quận 2",
    new_address: "Phường An Khánh, TP. Hồ Chí Minh", listing_url: "https://batdongsan.com.vn/mock-4",
    posted_at: day(-5), expired_at: day(25), poi_distances: { truong_hoc: 210, benh_vien: 1800, cho: 700 },
    latitude: 10.8032, longitude: 106.7405, coords_reliable: true, days_left: 25,
  },
  {
    listing_id: "mock-5", title: "Căn hộ Tân Bình 2PN gần sân bay, sổ hồng sẵn",
    price: 3100, area: 62, property_type: "Căn hộ chung cư", bedrooms: 2, district_old: "Tân Bình",
    old_address: "Đường Cộng Hòa, Phường 13, Quận Tân Bình",
    new_address: "Phường Tân Bình, TP. Hồ Chí Minh", listing_url: "https://batdongsan.com.vn/mock-5",
    posted_at: day(-1), expired_at: day(29), poi_distances: { cho: 480, benh_vien: 1200 },
    latitude: 10.8014, longitude: 106.6425, coords_reliable: true, days_left: 29,
  },
].map((hit, index) => ({ ...hit, position: index + 1 }));

// POI mẫu quanh từng tin: [loại, tên, độ lệch vĩ độ, dĩ lệch kinh độ, mét].
const POI_OFFSETS = [
  ["cho", "Chợ mẫu", 0.0012, 0.0008, 166],
  ["truong_hoc", "Trường mẫu", -0.003, 0.002, 420],
  ["benh_vien", "Bệnh viện mẫu", 0.006, -0.004, 900],
];

function chatResult(body) {
  const message = String(body.message ?? "").toLowerCase();
  const base = {
    conversation_id: body.conversation_id ?? randomUUID(),
    listings: [], referenced_ids: [], relax_options: [], degraded: false,
    answer: "", summary: "",
  };
  if (message.includes("thuê") || message.includes("thời tiết")) {
    return { ...base, status: "out_of_scope", summary: "Mình chỉ hỗ trợ tìm mua bất động sản ở TP.HCM." };
  }
  if (message.includes("so sánh")) {
    const text = "Căn 1 rẻ hơn căn 3 hơn 1,7 tỷ nhưng nhỏ hơn không đáng kể; căn 1 gần chợ hơn.";
    return { ...base, status: "answered", referenced_ids: ["mock-1", "mock-3"], summary: text, answer: text };
  }
  if (message.includes("hiếm")) {
    return {
      ...base, status: "no_results",
      summary: "Không có tin nào khớp mọi điều kiện.",
      relax_options: [
        { field: "price_max", description: "Nếu tăng ngân sách lên 3,6 tỷ: có 1 tin", result_count: 1, message: "tăng ngân sách lên 3,6 tỷ" },
        { field: "near_pois", description: "Nếu bỏ điều kiện gần bệnh viện: có 3 tin", result_count: 3, message: "bỏ điều kiện gần bệnh viện" },
      ],
    };
  }
  if (message.includes("muốn mua nhà") && !/\d|quận|q\./.test(message)) {
    return { ...base, status: "need_clarification", summary: "Bạn muốn mua ở khu vực nào và ngân sách khoảng bao nhiêu?" };
  }
  const summary = "Mình tìm được 5 tin phù hợp với điều kiện của bạn, xếp theo độ gần ý bạn nhất.";
  return {
    ...base, status: "ok", listings: LISTINGS, referenced_ids: LISTINGS.map((h) => h.listing_id),
    degraded: message.includes("degraded"), summary, answer: `${summary}\n(khối từng tin…)`,
  };
}

// Mode dự đoán giá (POST /api/v1/chat): có số m² thì "predicted", chưa có thì hỏi thêm.
function predictionResult(body) {
  const base = {
    conversation_id: body.conversation_id ?? randomUUID(), mode: "prediction",
    answer: "", fields: {}, missing: [],
  };
  const area = /(\d+(?:[.,]\d+)?)\s*(?:m2|m²)/i.exec(String(body.message ?? ""));
  if (!area) {
    const summary = "Nhà rộng bao nhiêu m² và ở quận nào?";
    return {
      ...base, status: "collecting", summary, answer: summary, missing: ["area", "district"],
      fields: { property_type: "nhà riêng", district: null, address: null, area: null },
    };
  }
  const size = Number(area[1].replace(",", "."));
  const perM2 = 62.5;
  const summary = `Giá ước tính khoảng ${(perM2 * size / 1000).toFixed(2)} tỷ.`;
  return {
    ...base, status: "predicted", summary, answer: summary,
    fields: { property_type: "nhà riêng", district: "Gò Vấp", address: null, area: size, bedrooms: 3 },
    prediction: {
      price_per_m2: perM2, total_price: perM2 * size, price_per_m2_low: 55, price_per_m2_high: 70,
      distance_to_center_km: 7.4, district_median_per_m2: 58.1, median_by_type: true,
      warnings: ["Ít tin cùng loại trong quận này, kết quả chỉ để tham khảo."],
    },
  };
}

function mapResult(searchParams) {
  const ids = (searchParams.get("ids") ?? "").split(",").filter(Boolean);
  const hits = LISTINGS.filter((hit) => ids.includes(hit.listing_id));
  const features = hits.map((hit) => ({
    type: "Feature",
    geometry: { type: "Point", coordinates: [hit.longitude, hit.latitude] },
    properties: {
      kind: "listing", position: hit.position, listing_id: hit.listing_id,
      title: hit.title, price: hit.price, area: hit.area, reliable: hit.coords_reliable,
    },
  }));
  for (const hit of hits) {
    for (const [poiType, name, dLat, dLng, meters] of POI_OFFSETS) {
      features.push({
        type: "Feature",
        geometry: { type: "Point", coordinates: [hit.longitude + dLng, hit.latitude + dLat] },
        properties: {
          kind: "poi", poi_type: poiType, name: `${name} gần tin ${hit.position}`,
          distance_m: meters, near_listing_id: hit.listing_id,
        },
      });
    }
  }
  return {
    type: "FeatureCollection", features,
    missing_ids: ids.filter((id) => !hits.some((hit) => hit.listing_id === id)),
  };
}

function readBody(request) {
  return new Promise((resolve) => {
    let raw = "";
    request.on("data", (chunk) => { raw += chunk; });
    request.on("end", () => {
      try { resolve(JSON.parse(raw || "{}")); } catch { resolve(null); }
    });
  });
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url, `http://${request.headers.host}`);
  const send = (status, payload) => {
    response.writeHead(status, {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    });
    response.end(JSON.stringify(payload));
  };
  if (request.method === "OPTIONS") return send(204, {});
  if (url.pathname === "/health") return send(200, { status: "ok" });
  if (url.pathname === "/api/v1/recommend/map" && request.method === "GET") {
    return send(200, mapResult(url.searchParams));
  }
  if (request.method === "POST" && url.pathname.startsWith("/api/v1/recommend/")) {
    const body = await readBody(request);
    if (body === null) return send(422, { detail: "JSON không hợp lệ" });
    if (url.pathname.endsWith("/chat")) {
      if (body.mode !== "recommendation") return send(422, { detail: "mode phải là recommendation" });
      return send(200, chatResult(body));
    }
    if (url.pathname.endsWith("/reset")) return send(200, { conversation_id: body.conversation_id });
  }
  if (request.method === "POST" && ["/api/v1/chat", "/api/v1/reset"].includes(url.pathname)) {
    const body = await readBody(request);
    if (body === null) return send(422, { detail: "JSON không hợp lệ" });
    if (url.pathname.endsWith("/reset")) return send(200, { conversation_id: body.conversation_id });
    if (body.mode !== "prediction") return send(422, { detail: "mock chỉ hỗ trợ mode prediction" });
    return send(200, predictionResult(body));
  }
  return send(404, { detail: "Not found" });
});

server.listen(PORT, () => console.log(`Mock API: http://localhost:${PORT}`));
