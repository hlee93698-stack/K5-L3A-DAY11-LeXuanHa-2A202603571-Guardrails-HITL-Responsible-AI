"""
Lab 11 — Optional enrichment: Human-in-the-Loop Design
  (Không chấm — tham khảo. Tóm tắt nộp do scripts/grade.py tự sinh,
   không viết report/*.md tay.)
  - Confidence Router
  - 3 HITL decision points
"""
from dataclasses import dataclass


# ============================================================
# Optional enrichment: ConfidenceRouter (không chấm)
#
# Route agent responses based on confidence scores:
#   - HIGH (>= 0.9): Auto-send to user
#   - MEDIUM (0.7 - 0.9): Queue for human review
#   - LOW (< 0.7): Escalate to human immediately
#
# Special case: if the action is HIGH_RISK (e.g., money transfer,
# account deletion), ALWAYS escalate regardless of confidence.
#
# Implement the route() method.
# ============================================================

HIGH_RISK_ACTIONS = [
    "transfer_money",
    "close_account",
    "change_password",
    "delete_data",
    "update_personal_info",
]


@dataclass
class RoutingDecision:
    """Result of the confidence router."""
    action: str          # "auto_send", "queue_review", "escalate"
    confidence: float
    reason: str
    priority: str        # "low", "normal", "high"
    requires_human: bool


class ConfidenceRouter:
    """Route agent responses based on confidence and risk level.

    Thresholds:
        HIGH:   confidence >= 0.9 -> auto-send
        MEDIUM: 0.7 <= confidence < 0.9 -> queue for review
        LOW:    confidence < 0.7 -> escalate to human

    High-risk actions always escalate regardless of confidence.
    """

    HIGH_THRESHOLD = 0.9
    MEDIUM_THRESHOLD = 0.7

    def route(self, response: str, confidence: float,
              action_type: str = "general") -> RoutingDecision:
        """Route a response based on confidence score and action type.

        Args:
            response: The agent's response text
            confidence: Confidence score between 0.0 and 1.0
            action_type: Type of action (e.g., "general", "transfer_money")

        Returns:
            RoutingDecision with routing action and metadata
        """
        # Clamp so a bad score (NaN, <0, >1) can never auto-send.
        try:
            conf = float(confidence)
        except (TypeError, ValueError):
            conf = 0.0
        if conf != conf:  # NaN
            conf = 0.0
        conf = min(max(conf, 0.0), 1.0)

        action_key = (action_type or "general").strip().lower()
        if action_key in HIGH_RISK_ACTIONS:
            return RoutingDecision(
                action="escalate",
                confidence=conf,
                reason=f"High-risk action: {action_key}",
                priority="high",
                requires_human=True,
            )

        if conf >= self.HIGH_THRESHOLD:
            return RoutingDecision(
                action="auto_send",
                confidence=conf,
                reason="High confidence",
                priority="low",
                requires_human=False,
            )

        if conf >= self.MEDIUM_THRESHOLD:
            return RoutingDecision(
                action="queue_review",
                confidence=conf,
                reason="Medium confidence — needs review",
                priority="normal",
                requires_human=True,
            )

        return RoutingDecision(
            action="escalate",
            confidence=conf,
            reason="Low confidence — escalating",
            priority="high",
            requires_human=True,
        )


# ============================================================
# Optional enrichment: 3 HITL decision points (không chấm)
# Không bắt buộc điền. Tóm tắt bài nộp: chạy scripts/grade.py
# (tự sinh lab_report.md) — không viết report tay.
#
# For each decision point, define:
# - trigger: What condition activates this HITL check?
# - hitl_model: Which model? (human-in-the-loop, human-on-the-loop,
#   human-as-tiebreaker)
# - context_needed: What info does the human reviewer need?
# - example: A concrete scenario
# - approval_path: What approve/reject/timeout decision is recorded?
# - audit_fields: Which correlation ID, intent and proposed action/diff are logged?
#
# Think about real banking scenarios where human judgment is critical.
# ============================================================

hitl_decision_points = [
    {
        "id": 1,
        "name": "Chuyển tiền giá trị lớn / tới người nhận mới",
        "trigger": (
            "Agent đề xuất transfer_money với số tiền >= 50.000.000 VND, "
            "hoặc người nhận chưa từng giao dịch, hoặc ConfidenceRouter trả về escalate."
        ),
        "hitl_model": "human-in-the-loop",
        "context_needed": (
            "Số tài khoản nguồn/đích (che bớt), số tiền, lịch sử 30 ngày, "
            "điểm rủi ro gian lận, đoạn hội thoại dẫn tới yêu cầu, kết quả xác thực OTP."
        ),
        "example": (
            "Khách nhắn 'chuyển gấp 120 triệu cho tài khoản mới, đang bị công an gọi' — "
            "dấu hiệu lừa đảo giả danh; giao dịch bị giữ lại chờ nhân viên gọi xác minh."
        ),
        "approval_path": (
            "Approve → thực hiện giao dịch và gửi biên nhận; Reject → huỷ, báo khách lý do "
            "chung chung + hotline; Timeout 15 phút → tự huỷ (fail-closed), không bao giờ tự duyệt."
        ),
        "audit_fields": (
            "correlation_id, user_id, intent=transfer_money, amount, payee_hash, "
            "risk_score, proposed_action, reviewer_id, decision, decided_at"
        ),
    },
    {
        "id": 2,
        "name": "Thay đổi thông tin định danh / bảo mật tài khoản",
        "trigger": (
            "Action thuộc change_password, update_personal_info hoặc close_account — "
            "luôn escalate theo HIGH_RISK_ACTIONS, bất kể confidence."
        ),
        "hitl_model": "human-in-the-loop",
        "context_needed": (
            "Diff trước/sau (SĐT, email, địa chỉ), kênh yêu cầu, thiết bị/IP mới hay cũ, "
            "lần đổi gần nhất, kết quả eKYC."
        ),
        "example": (
            "Yêu cầu đổi số điện thoại nhận OTP từ thiết bị lạ lúc 2h sáng, ngay sau đó "
            "đòi đóng tài khoản tiết kiệm — nhân viên khoá tạm và liên hệ số cũ."
        ),
        "approval_path": (
            "Approve → áp dụng diff, gửi thông báo tới kênh cũ; Reject → giữ nguyên, khoá "
            "tạm 24h nếu nghi chiếm đoạt; Timeout 30 phút → giữ nguyên trạng thái."
        ),
        "audit_fields": (
            "correlation_id, user_id, intent, field_diff (đã che PII), device_id, ip, "
            "reviewer_id, decision, reason_code, decided_at"
        ),
    },
    {
        "id": 3,
        "name": "Phản hồi bị guardrail/judge nghi ngờ",
        "trigger": (
            "OutputGuardrailPlugin redact secret/PII, LLM-judge trả UNSAFE, hoặc "
            "confidence trong khoảng 0.7–0.9 (queue_review)."
        ),
        "hitl_model": "human-on-the-loop",
        "context_needed": (
            "Câu hỏi gốc, phản hồi gốc và bản đã redact, danh sách issues, verdict của judge, "
            "lớp đã chặn trong audit log."
        ),
        "example": (
            "Agent trả lời lãi suất 5.5% trong khi bảng chuẩn là 4.25% — judge đánh dấu "
            "hallucination; khách nhận câu trả lời an toàn, reviewer sửa nội dung sau."
        ),
        "approval_path": (
            "Khách nhận bản an toàn ngay; reviewer xem hàng đợi: Approve → đánh dấu false "
            "positive để chỉnh rule; Reject → gắn nhãn sự cố, cập nhật test; "
            "Timeout 24h → tự đóng, vẫn giữ bản đã chặn."
        ),
        "audit_fields": (
            "correlation_id, request_id, layer, issues, judge_verdict, original_hash, "
            "redacted_preview, reviewer_id, label, decided_at"
        ),
    },
]


# ============================================================
# Quick tests
# ============================================================

def test_confidence_router():
    """Test ConfidenceRouter with sample scenarios."""
    router = ConfidenceRouter()

    test_cases = [
        ("Balance inquiry", 0.95, "general"),
        ("Interest rate question", 0.82, "general"),
        ("Ambiguous request", 0.55, "general"),
        ("Transfer $50,000", 0.98, "transfer_money"),
        ("Close my account", 0.91, "close_account"),
    ]

    print("Testing ConfidenceRouter:")
    print("=" * 80)
    print(f"{'Scenario':<25} {'Conf':<6} {'Action Type':<18} {'Decision':<15} {'Priority':<10} {'Human?'}")
    print("-" * 80)

    for scenario, conf, action_type in test_cases:
        decision = router.route(scenario, conf, action_type)
        print(
            f"{scenario:<25} {conf:<6.2f} {action_type:<18} "
            f"{decision.action:<15} {decision.priority:<10} "
            f"{'Yes' if decision.requires_human else 'No'}"
        )

    print("=" * 80)


def test_hitl_points():
    """Display HITL decision points."""
    print("\nHITL Decision Points:")
    print("=" * 60)
    for point in hitl_decision_points:
        print(f"\n  Decision Point #{point['id']}: {point['name']}")
        print(f"    Trigger:  {point['trigger']}")
        print(f"    Model:    {point['hitl_model']}")
        print(f"    Context:  {point['context_needed']}")
        print(f"    Example:  {point['example']}")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    test_confidence_router()
    test_hitl_points()
