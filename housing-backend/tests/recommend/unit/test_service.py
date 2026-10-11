"""RecommendationService + ConversationStore với TurnInterpreter giả (không gọi OpenAI).

Câu trả lời do code viết nên tất định; tìm kiếm chạy trên DB thật.
"""

import httpx
from fakes import AS_OF, FakeEmbeddingClient, FakeInterpreter, plan

from app.services.recommendation.schemas import PoiRequest, SearchConstraints
from app.services.recommendation.service import (
    MAX_MESSAGE_CHARS,
    ConversationStore,
    RecommendationService,
)
from app.services.recommendation.text_rules import MessageRules


def run_chat(run_db, plans, messages, store=None, client=None, ids=None):
    """Chạy lần lượt messages (mỗi câu ứng với một TurnPlan); trả (kết quả, interpreter)."""
    interpreter = FakeInterpreter(plans)

    async def chat(session):
        service = RecommendationService(
            store=store, interpreter=interpreter,
            embedding_client=client or FakeEmbeddingClient(), engine=session.bind,
            rerank_enabled=False,
        )
        results = []
        for i, message in enumerate(messages):
            conversation_id = (ids[i] if ids else None) or (
                results[-1].conversation_id if results else None
            )
            results.append(await service.chat(conversation_id, message, AS_OF))
        return results

    return run_db(chat), interpreter


def test_store_returns_copies_so_state_cannot_leak():
    store = ConversationStore()
    state = store.get("a")
    state.constraints.price_max = 3000
    assert store.get("a").constraints.price_max is None  # chưa save thì không đổi
    store.save(state)
    state.constraints.price_max = 9000
    assert store.get("a").constraints.price_max == 3000


def test_progressive_clarification_then_results(run_db):
    results, interpreter = run_chat(run_db, [
        plan(property_kinds=["can_ho"]),
        plan("answer_clarification", price_max=3000, district_names=["Thủ Đức"]),
    ], ["Mình muốn mua căn hộ", "Dưới 3 tỷ, khu Thủ Đức"])
    first, second = results
    assert first.status == "need_clarification" and first.listings == []
    assert first.constraints.property_types == ["Căn hộ chung cư"]  # điều kiện một phần vẫn giữ
    assert interpreter.calls[1][1]["pending_question"] == "budget_or_area"
    assert second.status == "ok" and 1 <= len(second.listings) <= 5
    assert second.constraints.property_types == ["Căn hộ chung cư"]
    assert len(second.constraints.district_ids) == 3
    assert all(h.price <= 3000 and h.property_type == "Căn hộ chung cư" for h in second.listings)
    assert second.answer.endswith("Giá là giá rao bán tham khảo.")


def test_out_of_scope_keeps_constraints_and_results(run_db):
    (found, refused, detail), _ = run_chat(run_db, [
        plan(price_max=5000, district_names=["Quận 7"]),
        plan("out_of_scope"),
        plan("ask_detail"),
    ], ["Nhà Quận 7 dưới 5 tỷ", "Còn Hà Nội thì sao?", "Căn 1 thế nào"])
    assert refused.status == "out_of_scope" and refused.listings == []
    assert refused.constraints == found.constraints
    assert detail.referenced_ids == [found.listings[0].listing_id]


def test_detail_and_compare_only_use_last_results(run_db):
    (found, detail, compare, wrong, by_id), _ = run_chat(run_db, [
        plan(price_max=5000, district_names=["Quận 7"]),
        plan("ask_detail"),
        plan("compare"),
        plan("ask_detail"),
        plan("ask_detail"),
    ], ["Nhà Quận 7 dưới 5 tỷ", "Căn thứ 2?", "So sánh căn 1 và 3", "Căn thứ 7?", "Tin 00000000?"])
    ids = [hit.listing_id for hit in found.listings]
    assert detail.status == "answered" and detail.referenced_ids == [ids[1]]
    assert compare.referenced_ids == [ids[0], ids[2]]
    assert wrong.status == "answered" and wrong.referenced_ids == []
    assert "Không tìm thấy căn thứ 7" in wrong.answer
    assert by_id.referenced_ids == [] and "Không tìm thấy tin 00000000" in by_id.answer
    assert detail.constraints == found.constraints  # hỏi chi tiết không đổi điều kiện


def test_reset_clears_everything_and_old_conditions_do_not_return(run_db):
    (_, reset, after), interpreter = run_chat(run_db, [
        plan(price_max=3000, district_names=["Quận 7"], property_kinds=["can_ho"],
             near_pois=[PoiRequest(poi_type="benh_vien", max_distance_m=2000)]),
        plan("reset"),
        plan(price_max=8000, district_names=["Bình Thạnh"]),
    ], ["Căn hộ Q7 dưới 3 tỷ gần bệnh viện", "Tìm lại từ đầu", "Nhà Bình Thạnh dưới 8 tỷ"])
    assert reset.status == "need_clarification" and reset.constraints == SearchConstraints()
    assert interpreter.calls[2][1]["last_results"] == []
    assert after.status == "ok"
    assert after.constraints.property_types == [] and after.constraints.near_pois == []
    assert after.constraints.price_max == 8000 and len(after.constraints.district_ids) == 1


def test_conversations_are_isolated(run_db):
    store = ConversationStore()
    (_, other, again), interpreter = run_chat(run_db, [
        plan(price_max=3000, district_names=["Quận 7"]),
        plan(property_kinds=["dat"]),
        plan("refine", bedrooms_min=2),
    ], ["Q7 dưới 3 tỷ", "Mua đất", "Thêm 2 phòng ngủ"], store=store, ids=["A", "B", "A"])
    assert other.status == "need_clarification"  # B không thấy ngân sách/khu vực của A
    assert other.constraints == SearchConstraints(property_types=["Bán đất"])
    assert again.constraints.property_types == [] and again.constraints.price_max == 3000
    assert interpreter.calls[1][1]["current_constraints"]["price_max"] is None


def test_invalid_merge_asks_again_and_keeps_previous_constraints(run_db):
    (found, invalid), _ = run_chat(run_db, [
        plan(price_max=3000, district_names=["Quận 7"]),
        plan("refine", price_min=5000),
    ], ["Q7 dưới 3 tỷ", "Từ 5 tỷ trở lên"])
    assert invalid.status == "need_clarification"
    assert "giá tối thiểu lớn hơn giá tối đa" in invalid.answer
    assert invalid.constraints == found.constraints


def test_unknown_area_asks_again(run_db):
    (result,), _ = run_chat(run_db, [plan(district_names=["Quận 13"])], ["Quận 13"])
    assert result.status == "need_clarification" and "Quận 13" in result.answer
    assert result.constraints == SearchConstraints()


def test_no_results_reports_only_counted_relax_options(run_db):
    (result,), _ = run_chat(run_db, [
        plan(price_max=1000, district_names=["Quận 1"], property_kinds=["nha_mat_pho"]),
    ], ["Nhà mặt phố Quận 1 dưới 1 tỷ"])
    assert result.status == "no_results" and result.listings == []
    assert result.relax_options and all(o.result_count > 0 for o in result.relax_options)
    for option in result.relax_options:
        assert f"{option.description}: có {option.result_count} tin" in result.answer


def test_embed_failure_still_answers_and_is_flagged(run_db):
    (result,), _ = run_chat(
        run_db, [plan(price_max=5000, district_names=["Quận 7"])], ["Q7 dưới 5 tỷ"],
        client=FakeEmbeddingClient(embed_error=httpx.ConnectTimeout("Kaggle tắt")),
    )
    assert result.status == "ok" and result.degraded and result.listings
    assert "gián đoạn" in result.answer


def test_long_message_is_truncated_before_interpreter(run_db):
    (result,), interpreter = run_chat(
        run_db, [plan("out_of_scope")], ["a" * (MAX_MESSAGE_CHARS + 500)]
    )
    assert len(interpreter.calls[0][0]) == MAX_MESSAGE_CHARS
    assert result.answer.startswith("(Tin nhắn dài hơn 1000 ký tự")


def test_code_rules_override_llm_plan(run_db):
    """C45#2, C31#2, C35#4: LLM đề xuất sai, quy tắc tất định trong code thắng."""
    (_, reset, again, wrong_ref, ward), _ = run_chat(run_db, [
        plan(price_max=4000, district_names=["Quận 7"], property_kinds=["can_ho"]),
        plan("search", price_max=4000, district_names=["Quận 7"], property_kinds=["can_ho"]),
        plan(price_max=4000, district_names=["Quận 7"], property_kinds=["can_ho"]),
        plan("ask_detail"),
        plan("refine", district_names=["Thủ Đức"]),
    ], ["Căn hộ Quận 7 dưới 4 tỷ", "Thôi tìm lại từ đầu nhé", "Căn hộ Quận 7 dưới 4 tỷ",
        "Căn thứ mười có view đẹp không?", "Thử phường Thủ Đức xem"])
    assert reset.status == "need_clarification" and reset.constraints == SearchConstraints()
    assert wrong_ref.status == "answered" and wrong_ref.referenced_ids == []
    assert "Không tìm thấy căn thứ 10" in wrong_ref.answer
    assert ward.constraints.district_ids == [] and len(ward.constraints.new_ward_ids) == 1
    assert again.answer.startswith("Mình tìm được")


def test_compare_answer_uses_positions_of_last_results(run_db):
    (found, compare), _ = run_chat(run_db, [
        plan(price_max=5000, district_names=["Quận 7"]),
        plan("compare"),
    ], ["Nhà Quận 7 dưới 5 tỷ", "So sánh căn 1 và căn 3"])
    ids = [hit.listing_id for hit in found.listings]
    assert compare.referenced_ids == [ids[0], ids[2]]  # code trích "căn 3", bỏ đề xuất [1, 2]
    assert f"Căn 3 [Tin {ids[2]}]" in compare.answer


def test_reset_clears_state_even_when_new_area_is_unknown(run_db):
    """Spec 9 #21: xóa ngay khi đòi tìm lại, kể cả nếu điều kiện mới bị hỏi lại."""
    (_, reset), _ = run_chat(run_db, [
        plan(price_max=4000, district_names=["Quận 7"]),
        plan("reset", district_names=["Quận 13"]),
    ], ["Q7 dưới 4 tỷ", "Tìm lại từ đầu, ở Quận 13"])
    assert reset.status == "need_clarification" and reset.constraints == SearchConstraints()
    assert reset.answer.startswith("Mình đã xoá điều kiện cũ và tìm lại từ đầu.")
    assert "Quận 13" in reset.answer


def test_approximate_price_end_to_end_then_new_max_drops_derived_min(run_db):
    (first, second), _ = run_chat(run_db, [
        plan(price_max=3000, price_approx=True, district_names=["Quận 7"]),
        plan("relax", price_max=4000),
    ], ["Căn hộ Q7 tầm 3 tỷ", "Nâng ngân sách lên 4 tỷ"])
    assert (first.constraints.price_min, first.constraints.price_max) == (2400, 3150)
    assert "giá khoảng 2,4 tỷ – 3,15 tỷ" in first.answer
    assert all(2400 <= h.price <= 3150 for h in first.listings)
    assert (second.constraints.price_min, second.constraints.price_max) == (None, 4000)
    assert "Đã tăng ngân sách lên 4 tỷ." in second.answer


def test_budget_reversal_waits_for_confirmation_then_applies_or_cancels(run_db):
    (_, ask, yes, ask_again, no), interpreter = run_chat(run_db, [
        plan(price_max=6000, district_names=["Quận 7"]),
        plan("relax", price_max=4500),
        plan("relax", price_max=3000),
    ], ["Nhà Q7 dưới 6 tỷ", "Nâng ngân sách lên 4 tỷ rưỡi", "ừ đúng rồi",
        "Nâng ngân sách lên 3 tỷ", "thôi giữ nguyên"])
    assert ask.status == "need_clarification" and ask.constraints.price_max == 6000
    assert yes.status == "ok" and yes.constraints.price_max == 4500  # B4: "ừ" áp giá đang chờ
    assert ask_again.status == "need_clarification" and ask_again.constraints.price_max == 4500
    assert no.status == "answered" and no.constraints.price_max == 4500
    assert len(interpreter.calls) == 3  # hai câu xác nhận không gọi LLM


def test_dropped_poi_is_reported_and_superlative_narrows_referenced_ids(run_db):
    (found, ask), _ = run_chat(run_db, [
        plan(price_max=5000, district_names=["Quận 7"],
             near_pois=[PoiRequest(poi_type="truong_hoc", max_distance_m=None)]),
        plan("ask_detail"),
    ], ["Nhà Q7 dưới 5 tỷ gần abc", "Căn nào rẻ nhất?"])
    assert "Mình chưa hiểu rõ điều kiện gần trường học nên chưa áp dụng." in found.answer
    cheapest = min(h.price for h in found.listings)
    assert ask.referenced_ids == [h.listing_id for h in found.listings if h.price == cheapest]


def test_reduce_to_amount_is_applied_as_the_new_max(run_db):  # H7: không nhân 0,9 lên số khách nói
    (_, reduced), _ = run_chat(run_db, [
        plan(price_max=5000, district_names=["Quận 7"]),
        plan("relax", price_max=3200, cheaper=True),
    ], ["Nhà Q7 dưới 5 tỷ", "thôi giảm xuống 3tỷ2"])
    assert reduced.constraints.price_max == 3200
    assert "Đã giảm ngân sách xuống 3,2 tỷ." in reduced.answer


def test_out_of_range_amount_is_reported_with_the_number_the_user_typed(run_db):  # I4
    (asked,), _ = run_chat(run_db, [plan(price_max=3.8, price_approx=True)], ["khoảng 3tr8 thôi"])
    assert asked.status == "need_clarification"
    assert "mức giá 3,8 triệu nằm ngoài khoảng 100 triệu-500 tỷ" in asked.answer
    assert asked.answer.count("mức giá") == 1


def test_switching_to_land_drops_the_old_bedroom_condition(run_db):  # G8
    (_, land), _ = run_chat(run_db, [
        plan(price_max=3000, district_names=["Quận 2"], property_kinds=["can_ho"], bedrooms_min=1),
        plan("refine", price_max=2000, district_names=["Huyện Củ Chi"],
             property_kinds=["dat_nen_du_an"]),
    ], ["can ho 1pn q2 duoi 3 ty", "dat nen cu chi duoi 2 ty"])
    assert land.constraints.bedrooms_min is None


def test_detail_question_after_no_results_says_to_relax_conditions(run_db):
    """Câu hỏi chi tiết sau lượt no_results: nói rõ lượt trước không có tin, không tìm lại."""
    (empty, by_position, vague), interpreter = run_chat(run_db, [
        plan(price_max=1000, district_names=["Quận 1"], property_kinds=["nha_mat_pho"]),
        plan("ask_detail"),
        plan("search"),  # LLM coi câu hỏi là một lần tìm mới
    ], ["Nhà mặt phố Quận 1 dưới 1 tỷ", "căn thứ 2 diện tích bao nhiêu?",
        "chủ nhà có thương lượng không?"])
    assert empty.status == "no_results"
    for result in (by_position, vague):
        assert result.status == "answered" and result.listings == [] and not result.relax_options
        assert result.answer == "Lượt trước chưa có tin nào khớp, bạn nới điều kiện nhé."
        assert result.constraints == empty.constraints
    assert len(interpreter.calls) == 3


def test_vague_detail_question_asks_which_listing_without_searching_again(run_db):
    (found, no_target, with_target, ranking), _ = run_chat(run_db, [
        plan(price_max=5000, district_names=["Quận 7"]),
        plan("search"),
        plan("ask_detail"),
        plan("ask_detail"),
    ], ["Nhà Quận 7 dưới 5 tỷ", "chủ nhà có thương lượng không?",
        "căn 2 hướng nhà thế nào?", "căn nào rẻ nhất?"])
    assert len(found.listings) == 5
    assert no_target.status == "answered" and no_target.listings == []
    assert no_target.answer == "Bạn muốn hỏi căn nào (1–5)?"
    assert no_target.constraints == found.constraints
    assert "Bạn muốn hỏi căn nào" not in with_target.answer  # đã nói "căn 2"
    assert ranking.referenced_ids  # hỏi xếp hạng cả danh sách vẫn trả lời


def test_detail_question_without_any_previous_listing_says_so(run_db):
    (result,), _ = run_chat(run_db, [plan("refine")], ["hướng nhà thế nào?"])
    assert result.status == "answered" and result.listings == []
    assert result.answer == "Mình chưa gợi ý tin nào để hỏi chi tiết."


def test_reset_with_new_conditions_does_not_report_changes_against_old_state(run_db):
    (found, reset), _ = run_chat(run_db, [
        plan(price_max=5000, district_names=["Quận 7"], property_kinds=["can_ho"]),
        plan("search", price_max=2000, district_names=["Huyện Củ Chi"],
             property_kinds=["dat_nen_du_an"]),
    ], ["Căn hộ Quận 7 dưới 5 tỷ", "thôi bỏ hết, tìm đất nền Củ Chi dưới 2 tỷ"])
    assert found.status == "ok"
    assert reset.answer.startswith("Mình đã xoá điều kiện cũ và tìm lại từ đầu.")
    assert "Đã giảm" not in reset.answer and "Đã đổi" not in reset.answer
    assert reset.constraints.price_max == 2000
    assert reset.constraints.property_types == ["Đất nền dự án"]


def test_relax_option_message_is_a_sendable_sentence_the_rules_keep(run_db):
    (empty,), _ = run_chat(run_db, [
        plan(price_max=1000, district_names=["Quận 1"], property_kinds=["nha_mat_pho"]),
    ], ["Nhà mặt phố Quận 1 dưới 1 tỷ"])
    assert empty.relax_options
    assert all(o.message == o.description for o in empty.relax_options)
    expected = {  # TurnPlan hợp lý của từng câu: quy tắc tất định không được làm mất ý
        "tăng ngân sách lên 3,6 tỷ": plan("relax", price_max=3600),
        "bỏ điều kiện gần bệnh viện": plan("relax", clear=["near_pois.benh_vien"]),
        "bỏ điều kiện loại nhà đất": plan("relax", clear=["property_types"]),
        "mở rộng ra toàn TP.HCM": plan("relax", clear=["district_ids", "new_ward_ids"]),
    }
    current = SearchConstraints(price_max=3000)
    for message, proposed in expected.items():
        fixed = MessageRules(message).correct(proposed, current, ["Quận 1"], [], ["Quận 1"])
        assert fixed.plan.intent == "relax" and not fixed.ignored, message
        assert set(fixed.plan.clear_fields) == set(proposed.clear_fields), message
        assert fixed.plan.set_fields.price_max == proposed.set_fields.price_max, message
