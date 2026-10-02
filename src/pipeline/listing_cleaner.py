"""Làm sạch tin đăng crawl (CrawlData/data.json, JSON Lines) trước khi nạp vào database.

Đầu ra (mặc định data/listings/):
  listings_clean.jsonl     mỗi listing_id một dòng, kèm quality_flags và raw_record
  listings_rejected.jsonl  tin không được nạp, kèm lý do và raw_record
  cleaning_report.json     số liệu từng bước, lý do loại, cờ chất lượng, số ô trống

Nguyên tắc:
  - Loại tin khi field bắt buộc cho cả hai pipeline (giá, diện tích, mã tin, URL, tiêu đề)
    thiếu hoặc sai rõ ràng, hoặc tin nằm ngoài TP.HCM cũ.
  - Field phụ có giá trị bất khả thi được đặt None và gắn cờ; giá trị gốc vẫn ở raw_record.
  - Không suy đoán: không suy ra địa chỉ mới từ địa chỉ cũ, không tự sửa giá. Sửa duy nhất
    diện tích bị đọc sai dấu phân cách hàng nghìn, và chỉ khi khớp giá/m² của website.
Đơn vị giữ như crawler: price (triệu VND), price_per_m2 (triệu VND/m²).
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


class ListingCleaner:
    """Chuẩn hóa → sửa/gắn cờ giá trị sai → bỏ trùng → tách tin sạch và tin bị loại."""

    # 24 quận/huyện TP.HCM cũ, viết như district_old (so sánh không phân biệt hoa thường).
    OLD_HCM_DISTRICTS = [
        'bình chánh', 'bình tân', 'bình thạnh', 'cần giờ', 'củ chi', 'gò vấp',
        'hóc môn', 'nhà bè', 'phú nhuận', 'quận 1', 'quận 10', 'quận 11',
        'quận 12', 'quận 2', 'quận 3', 'quận 4', 'quận 5', 'quận 6',
        'quận 7', 'quận 8', 'quận 9', 'thủ đức', 'tân bình', 'tân phú',
    ]
    # Khung tọa độ TP.HCM cũ. Website gán (21.0289, 105.8524) - trung tâm Hà Nội - cho tin
    # không có vị trí; khung này loại điểm đó.
    HCM_LATITUDE = (10.3, 11.2)
    HCM_LONGITUDE = (106.3, 107.1)

    MIN_AREA = 10                   # m²; nhỏ hơn là lỗi parse (ví dụ area = 1)
    PRICE_PER_M2_RANGE = (1, 2000)  # triệu/m², tính bằng price / area
    PRICE_PER_M2_TOLERANCE = 0.05   # lệch tương đối cho phép giữa price_per_m2 và price / area
    # Ngưỡng trên của field phụ; vượt ngưỡng thì đặt None.
    FIELD_MAX = {'bedrooms': 50, 'bathrooms': 50, 'floors': 81, 'frontage': 200, 'road_width': 200}
    # Nhóm pháp lý: xét theo thứ tự, khớp nhóm đầu tiên; không khớp nhóm nào -> 'khac'.
    LEGAL_GROUPS = {
        'dang_cho_so': r'chờ sổ',
        'so_do_so_hong': r'sổ (?:hồng|đỏ)|\bshr\b|có sổ|sổ riêng|sổ chung',
        'hop_dong_mua_ban': r'hợp đồng mua bán|\bhđmb\b|\bhdmb\b',
    }

    TEXT_COLUMNS = [
        'transaction_type', 'property_type', 'province_old', 'district_old', 'old_ward',
        'new_ward', 'new_city', 'old_address', 'old_address_detail', 'new_address',
        'legal', 'interior', 'listing_id', 'listing_url', 'title',
    ]
    NUMBER_COLUMNS = ['price', 'price_per_m2', 'area', 'frontage', 'bedrooms', 'bathrooms',
                      'road_width', 'floors', 'latitude', 'longitude']
    OUTPUT_COLUMNS = [
        'listing_id', 'listing_url', 'title', 'description', 'transaction_type', 'property_type',
        'price', 'price_per_m2', 'area', 'frontage', 'bedrooms', 'bathrooms', 'road_width',
        'floors', 'legal', 'legal_group', 'interior', 'province_old', 'district_old', 'old_ward',
        'old_address', 'old_address_detail', 'new_ward', 'new_city', 'new_address',
        'latitude', 'longitude', 'posted_at', 'expired_at', 'quality_flags', 'raw_record',
    ]

    def run(self, input_path, output_dir):
        """Đọc file JSON Lines, làm sạch, ghi ba file đầu ra; trả về (tin sạch, tin bị loại, báo cáo)."""
        records, malformed = [], []
        with input_path.open(encoding='utf-8') as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    malformed.append(line_number)

        clean, rejected = self.clean(records)

        output_dir.mkdir(parents=True, exist_ok=True)
        for name, frame in (('listings_clean', clean), ('listings_rejected', rejected)):
            rows = frame.astype(object).where(frame.notna(), None).to_dict('records')
            with (output_dir / f'{name}.jsonl').open('w', encoding='utf-8', newline='\n') as stream:
                for row in rows:
                    stream.write(json.dumps(row, ensure_ascii=False, default=int) + '\n')

        report = {
            'input_file': str(input_path),
            'generated_at': datetime.now().astimezone().isoformat(timespec='seconds'),
            'input_lines': len(records) + len(malformed),
            'malformed_lines': malformed,
            'duplicates_removed': len(records) - len(clean) - len(rejected),
            'unique_listings': len(clean) + len(rejected),
            'rejected': len(rejected),
            'clean': len(clean),
            'reject_reasons': rejected['reason'].value_counts().to_dict(),
            'quality_flags': clean['quality_flags'].explode().value_counts().to_dict(),
            'null_counts': clean.drop(columns=['quality_flags', 'raw_record']).isna().sum().to_dict(),
            'property_types': clean['property_type'].value_counts().to_dict(),
            'legal_groups': clean['legal_group'].fillna('null').value_counts().to_dict(),
            'expired_filter': 'disabled',
        }
        (output_dir / 'cleaning_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=int), encoding='utf-8')
        return clean, rejected, report

    def clean(self, raw_records):
        """Nhận list dict thô, trả về (DataFrame tin sạch, DataFrame tin bị loại)."""
        listings = self._normalize(raw_records)
        listings = self._fix_and_flag(listings)

        # Bỏ trùng listing_id: giữ bản có posted_at mới nhất; bằng nhau thì giữ dòng sau
        # trong file (sort ổn định giữ thứ tự gốc). Tin thiếu listing_id để lại cho bước loại.
        listings = listings.sort_values('posted_at', kind='stable', na_position='first')
        listings = listings[listings['listing_id'].isna()
                            | ~listings.duplicated('listing_id', keep='last')]

        reason = self._reject_reasons(listings)
        clean = listings.loc[reason == '', self.OUTPUT_COLUMNS].sort_values('listing_id')
        rejected = listings.loc[reason != '', ['listing_id', 'raw_record']]
        rejected.insert(0, 'reason', reason[reason != ''])
        return clean.reset_index(drop=True), rejected.reset_index(drop=True)

    def _normalize(self, raw_records):
        """Đưa dữ liệu thô về đúng kiểu: text sạch khoảng trắng, số dương, ngày ISO."""
        listings = pd.DataFrame(raw_records).reindex(
            columns=self.TEXT_COLUMNS + self.NUMBER_COLUMNS
            + ['description', 'posting_date', 'expiration_date'])
        listings['raw_record'] = raw_records

        # Text một dòng: Unicode NFC, gom khoảng trắng, bỏ khoảng trắng trước dấu phẩy.
        for column in self.TEXT_COLUMNS:
            text = (listings[column].astype('string').str.normalize('NFC')
                    .str.split().str.join(' ').str.replace(r'\s+,', ',', regex=True))
            listings[column] = text.mask(text == '')
        for column in ('legal', 'interior'):
            listings[column] = listings[column].str.rstrip('.').str.strip()

        # Mô tả: chỉ sửa khoảng trắng, giữ xuống dòng (tối đa một dòng trống), không xóa nội dung.
        listings['description'] = (
            listings['description'].astype('string').str.normalize('NFC')
            .str.replace(r'[^\S\n]+', ' ', regex=True)
            .str.replace(r' ?\n ?', '\n', regex=True)
            .str.replace(r'\n{3,}', '\n\n', regex=True)
            .str.strip())

        # Số: chỉ nhận số dương; chữ, số 0, số âm -> NaN.
        numbers = listings[self.NUMBER_COLUMNS].apply(pd.to_numeric, errors='coerce')
        listings[self.NUMBER_COLUMNS] = numbers.where(numbers > 0)

        # Ngày dd/mm/yyyy -> 'yyyy-mm-dd' (chuỗi ISO sắp xếp đúng thứ tự thời gian).
        for source, target in (('posting_date', 'posted_at'), ('expiration_date', 'expired_at')):
            listings[target] = pd.to_datetime(
                listings[source], format='%d/%m/%Y', errors='coerce').dt.strftime('%Y-%m-%d')

        legal = listings['legal'].str.casefold().fillna('')
        listings['legal_group'] = pd.Series(np.select(
            [legal.str.contains(pattern, regex=True) for pattern in self.LEGAL_GROUPS.values()],
            list(self.LEGAL_GROUPS), default='khac'), index=listings.index
        ).where(listings['legal'].notna())
        return listings

    def _fix_and_flag(self, listings):
        """Sửa lỗi diện tích kiểm chứng được, đặt None cho giá trị bất khả thi, gắn quality_flags."""
        price, price_per_m2 = listings['price'], listings['price_per_m2']
        tolerance = self.PRICE_PER_M2_TOLERANCE * price_per_m2

        # Crawler đọc '1.437 m²' thành 1.437. Chỉ nhân 1000 khi kết quả khớp giá/m² website.
        area_x1000 = (listings['area'] * 1000).round(3)
        area_fixed = (listings['area'] < self.MIN_AREA) & ((price / area_x1000 - price_per_m2).abs() <= tolerance)
        listings.loc[area_fixed, 'area'] = area_x1000
        area = listings['area']

        flags = {
            'area_thousands_separator_fixed': area_fixed,
            'price_per_m2_mismatch': (price / area - price_per_m2).abs() > tolerance,
        }
        for field, maximum in self.FIELD_MAX.items():
            flags[f'{field}_out_of_range'] = listings[field] > maximum
        flags['frontage_exceeds_area'] = (listings['frontage'] > area) & ~flags['frontage_out_of_range']
        coords_missing = listings['latitude'].isna() | listings['longitude'].isna()
        flags['coords_invalid'] = coords_missing
        flags['coords_outside_hcm'] = ~coords_missing & ~(
            listings['latitude'].between(*self.HCM_LATITUDE)
            & listings['longitude'].between(*self.HCM_LONGITUDE))
        flags['posted_at_invalid'] = listings['posted_at'].isna()
        flags['expired_at_invalid'] = listings['expired_at'].isna()

        for field in self.FIELD_MAX:
            listings[field] = listings[field].mask(flags[f'{field}_out_of_range'])
        listings['frontage'] = listings['frontage'].mask(flags['frontage_exceeds_area'])
        listings[['latitude', 'longitude']] = listings[['latitude', 'longitude']].mask(
            flags['coords_outside_hcm'], axis=0)
        for field in ('bedrooms', 'bathrooms', 'floors'):
            listings[field] = listings[field].round().astype('Int64')

        flag_table = pd.DataFrame(flags)
        listings['quality_flags'] = [list(flag_table.columns[row]) for row in flag_table.to_numpy()]
        return listings

    def _reject_reasons(self, listings):
        """Lý do loại của từng tin ('' = giữ). Các luật xét theo thứ tự, luật đầu tiên khớp thắng."""
        price, area = listings['price'], listings['area']
        rules = {
            'missing_listing_id': listings['listing_id'].isna(),
            'missing_listing_url': listings['listing_url'].isna(),
            'missing_title': listings['title'].isna(),
            'not_for_sale': listings['transaction_type'].fillna('') != 'Bán',
            'outside_hcm': listings['province_old'].str.casefold().fillna('') != 'hồ chí minh',
            'district_outside_old_hcm':
                ~listings['district_old'].str.casefold().isin(self.OLD_HCM_DISTRICTS).fillna(False),
            'missing_price': price.isna(),
            'missing_area': area.isna(),
            'area_too_small': area < self.MIN_AREA,
            'price_equals_price_per_m2': price == listings['price_per_m2'],
            'price_per_m2_out_of_range': ~(price / area).between(*self.PRICE_PER_M2_RANGE),
            # Lọc tin hết hạn: tạm tắt, chưa dùng ở giai đoạn này. Khi cần bật, đặt as_of là
            # ngày chạy pipeline dạng 'yyyy-mm-dd' rồi bỏ comment dòng dưới:
            # 'expired': listings['expired_at'] < as_of,
        }
        return pd.Series(np.select(list(rules.values()), list(rules), default=''),
                         index=listings.index)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--input', type=Path, default=ROOT / 'CrawlData/data.json')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'data/listings')
    args = parser.parse_args()
    _, _, report = ListingCleaner().run(args.input.resolve(), args.output_dir.resolve())
    summary = {k: report[k] for k in ('input_lines', 'duplicates_removed', 'unique_listings',
                                       'rejected', 'clean', 'reject_reasons', 'quality_flags')}
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=int))


if __name__ == '__main__':
    main()
