// Kiểu và lời gọi API theo hợp đồng docs/tasks/chatbot-recommendation.md mục 1.
// Đơn vị như backend: giá triệu VND, diện tích m², khoảng cách mét.

export type PoiType = "truong_hoc" | "benh_vien" | "cho";
export type TurnStatus = "ok" | "need_clarification" | "out_of_scope" | "no_results" | "answered";

export interface ListingHit {
  listing_id: string;
  title: string;
  price: number;
  area: number;
  property_type: string | null;
  bedrooms: number | null;
  district_old: string | null;
  old_address: string | null;
  new_address: string | null;
  listing_url: string;
  posted_at: string | null;
  expired_at: string | null;
  poi_distances: Partial<Record<PoiType, number>>;
  latitude: number | null;
  longitude: number | null;
  coords_reliable: boolean;
  position: number;
  days_left: number | null;
}

export interface RelaxOption {
  field: string;
  description: string;
  result_count: number;
  message: string; // câu gửi lại nguyên văn để áp phương án này
}

export type Mode = "recommendation" | "prediction";

export interface PredictionEstimate {
  price_per_m2: number; // triệu VND/m²
  total_price: number; // triệu VND
  price_per_m2_low?: number; // khoảng tin cậy (phân vị các cây RF), triệu VND/m²
  price_per_m2_high?: number;
  distance_to_center_km: number;
  district_median_per_m2: number | null; // backend không có median của quận thì null
  median_by_type?: boolean; // true: median riêng của loại nhà này trong quận
  warnings?: string[]; // dữ liệu train thưa / ngoại suy / các cây bất đồng
}

export type PredictionStatus = "collecting" | "ready" | "predicted" | "out_of_scope";

export interface PredictionTurn {
  conversation_id: string;
  mode: "prediction";
  status: PredictionStatus;
  answer: string;
  summary: string;
  fields: Record<string, string | number | null>;
  missing: string[];
  prediction?: PredictionEstimate | null;
  suggestions?: string[]; // câu trả lời nhanh do backend chọn, hiện thành chip
}

export interface ChatTurnResult {
  conversation_id: string;
  status: TurnStatus;
  listings: ListingHit[];
  referenced_ids: string[];
  relax_options: RelaxOption[];
  degraded: boolean;
  answer: string;
  summary: string;
  suggestions?: string[]; // vd. ứng viên địa điểm trùng tên, hiện thành chip
}

export interface MapProperties {
  kind: "listing" | "poi" | "place"; // place: địa điểm có tên đang lọc, kèm bán kính
  address?: string | null;
  radius_m?: number;
  position?: number;
  listing_id?: string;
  title?: string;
  price?: number;
  area?: number;
  reliable?: boolean;
  poi_type?: PoiType;
  name?: string;
  distance_m?: number;
  near_listing_id?: string;
}

export interface MapFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] }; // [lng, lat]
  properties: MapProperties;
}

export interface MapData {
  type: "FeatureCollection";
  features: MapFeature[];
  missing_ids: string[];
}

// VITE_API_URL chọn đích: backend thật (mặc định :8000) hoặc mock (`npm run mock`, PORT=8001).
export const API_URL: string = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const GOONG_TILES_KEY: string = import.meta.env.VITE_GOONG_MAPTILES_KEY ?? "";

const PREFIX = `${API_URL}/api/v1/recommend`;

/** Lấy `detail` dạng chuỗi của FastAPI (vd. 503 "Trợ lý tạm thời không phản hồi…") nếu có. */
async function errorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // Thân lỗi không phải JSON: dùng mã trạng thái.
  }
  return `Máy chủ trả lỗi ${response.status}.`;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    throw new Error("Không kết nối được máy chủ. Kiểm tra backend (hoặc mock) đang chạy.");
  }
  if (!response.ok) {
    throw new Error(await errorDetail(response));
  }
  return (await response.json()) as T;
}

function postJson<T>(url: string, body: unknown): Promise<T> {
  return request<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function sendChat(message: string, conversationId: string | null): Promise<ChatTurnResult> {
  return postJson<ChatTurnResult>(`${PREFIX}/chat`, {
    mode: "recommendation",
    message,
    ...(conversationId ? { conversation_id: conversationId } : {}),
  });
}

export function resetConversation(conversationId: string): Promise<{ conversation_id: string }> {
  return postJson(`${PREFIX}/reset`, { conversation_id: conversationId });
}

export function fetchMap(ids: string[], conversationId: string | null = null): Promise<MapData> {
  const query = new URLSearchParams({
    ids: ids.join(","),
    radius_m: "2000",
    poi_types: "truong_hoc,benh_vien,cho",
    ...(conversationId ? { conversation_id: conversationId } : {}),
  });
  return request<MapData>(`${PREFIX}/map?${query.toString()}`);
}

export function sendPrediction(message: string, conversationId: string | null): Promise<PredictionTurn> {
  return postJson<PredictionTurn>(`${API_URL}/api/v1/chat`, {
    mode: "prediction",
    message,
    ...(conversationId ? { conversation_id: conversationId } : {}),
  });
}

export function resetPrediction(conversationId: string): Promise<{ conversation_id: string }> {
  return postJson(`${API_URL}/api/v1/reset`, { conversation_id: conversationId });
}
