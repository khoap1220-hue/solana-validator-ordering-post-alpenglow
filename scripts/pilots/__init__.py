# -*- coding: utf-8 -*-
"""
Zero-Exception Real Transaction & Settled Payout Completion Gate
(`evo-2026-10-28-real-payout-completion-invariant`)
"""
from typing import Any


def verify_satellite_branch_merge_eligibility(branch_entry: dict[str, Any]) -> dict[str, Any]:
    """
    Quy tắc Bất biến Không Ngoại Lệ:
    Chỉ khi nhánh vệ tinh hoàn tất >= 1 giao dịch thật từ job VÀ tiền thực tế đã về
    (`real_payout_received_usd > 0` + có mã giao dịch `payout_tx_reference`) mới tính là
    HOÀN THÀNH (`is_completed = True`, `can_merge_to_main = True`).
    """
    real_tx_count = int(branch_entry.get("real_transactions_completed", 0) or 0)
    real_payout_usd = float(branch_entry.get("real_payout_received_usd", 0.0) or 0.0)
    tx_ref = str(branch_entry.get("payout_tx_reference") or "").strip()

    is_completed = (real_tx_count >= 1) and (real_payout_usd > 0.0) and bool(tx_ref)
    return {
        "is_completed": is_completed,
        "can_merge_to_main": is_completed,
        "real_transactions_completed": real_tx_count,
        "real_payout_received_usd": real_payout_usd,
        "payout_tx_reference": tx_ref if tx_ref else None,
        "branch_completion_status": (
            "DA_HOAN_THANH_TIEN_VE_THAT"
            if is_completed
            else "CHUA_HOAN_THANH_CHO_GIAO_DICH_THAT_VA_TIEN_VE"
        ),
    }
