import { describe, expect, it } from "vitest";
import type { ListingHit } from "./api";
import { formatArea, formatDate, formatDistance, formatPrice, listingWarnings, nearestPoi } from "./format";

function hit(overrides: Partial<ListingHit>): ListingHit {
  return {
    listing_id: "1", title: "t", price: 1, area: 1, property_type: null, bedrooms: null,
    district_old: null, old_address: null, new_address: null, listing_url: "https://x",
    posted_at: null, expired_at: null, poi_distances: {}, latitude: 10.7, longitude: 106.7,
    coords_reliable: true, position: 1, days_left: 30, ...overrides,
  };
}

describe("formatPrice", () => {
  it("tỷ và triệu", () => {
    expect(formatPrice(2650)).toBe("2,65 tỷ");
    expect(formatPrice(2065)).toBe("2,065 tỷ");
    expect(formatPrice(3000)).toBe("3 tỷ");
    expect(formatPrice(900)).toBe("900 triệu");
  });
});

describe("formatDistance", () => {
  it("mét và km", () => {
    expect(formatDistance(166)).toBe("166 m");
    expect(formatDistance(1600)).toBe("1,6 km");
    expect(formatDistance(2000)).toBe("2 km");
  });
});

describe("formatDate / formatArea", () => {
  it("dd/mm/yyyy", () => {
    expect(formatDate("2026-09-05")).toBe("05/09/2026");
    expect(formatDate(null)).toBe("");
  });
  it("diện tích", () => {
    expect(formatArea(53)).toBe("53 m²");
    expect(formatArea(46.6)).toBe("46,6 m²");
  });
});

describe("listingWarnings", () => {
  it("không cảnh báo khi còn hạn và tọa độ tốt", () => {
    expect(listingWarnings(hit({}))).toEqual([]);
    expect(listingWarnings(hit({ days_left: null }))).toEqual([]);
  });
  it("sắp hết hạn tại biên 3 ngày, không báo ở 4 ngày", () => {
    expect(listingWarnings(hit({ days_left: 3 }))).toEqual(["Sắp hết hạn (còn 3 ngày)"]);
    expect(listingWarnings(hit({ days_left: 0 }))).toEqual(["Sắp hết hạn (còn 0 ngày)"]);
    expect(listingWarnings(hit({ days_left: 4 }))).toEqual([]);
  });
  it("đã hết hạn và tọa độ không đáng tin", () => {
    expect(listingWarnings(hit({ days_left: -1, coords_reliable: false }))).toEqual([
      "Tin đã hết hạn",
      "Tọa độ chưa đáng tin",
    ]);
  });
});

describe("nearestPoi", () => {
  it("chọn loại gần nhất", () => {
    expect(nearestPoi({ truong_hoc: 400, cho: 166 })).toEqual({ type: "cho", meters: 166 });
    expect(nearestPoi({})).toBeNull();
  });
});
