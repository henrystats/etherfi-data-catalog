from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.prepare_kyberswap_depositor_intelligence import (
    ATTRIBUTED_HOLDINGS_QUERY_ID,
    ETHERFI_ACTIVITY_OUTPUT_COLUMNS,
    ETHERFI_ACTIVITY_QUERY_ID,
    ETHERFI_ACTIVITY_SOURCE_COLUMNS,
    REFERRAL_DEPOSITS_OUTPUT_COLUMNS,
    REFERRAL_DEPOSITS_QUERY_ID,
    REFERRAL_DEPOSITS_SOURCE_COLUMNS,
    KyberSwapDepositorIntelligenceError,
    build_kyberswap_depositor_intelligence,
    prepare_kyberswap_etherfi_activity,
    prepare_kyberswap_referral_deposits,
    validate_kyberswap_depositor_intelligence,
)


ADDRESS_A = "0x" + "a" * 40
ADDRESS_B = "0x" + "b" * 40
TX_A = "0x" + "1" * 64
TX_B = "0x" + "2" * 64
TX_C = "0x" + "3" * 64
UPDATED = "2026-08-03T04:20:03Z"


def _prepare_deposits(rows: list[dict]) -> list[dict]:
    return prepare_kyberswap_referral_deposits(
        rows,
        source_query_id=REFERRAL_DEPOSITS_QUERY_ID,
        source_execution_id="deposit-execution",
        source_last_updated=UPDATED,
        generated_at=UPDATED,
        source_columns=REFERRAL_DEPOSITS_SOURCE_COLUMNS,
    ).rows


def _prepare_activity(rows: list[dict]) -> list[dict]:
    return prepare_kyberswap_etherfi_activity(
        rows,
        source_query_id=ETHERFI_ACTIVITY_QUERY_ID,
        source_execution_id="activity-execution",
        source_last_updated="2026-08-03T05:20:03Z",
        generated_at="2026-08-03T05:20:03Z",
        source_columns=ETHERFI_ACTIVITY_SOURCE_COLUMNS,
    ).rows


def _deposit_row(**overrides: object) -> dict:
    row = {
        "tx_hash": TX_A,
        "address": ADDRESS_A.upper().replace("0X", "0x"),
        "blockchain": "Ethereum",
        "block_time": "2026-08-02 12:00:00",
        "strategy_symbol": "liquidETH",
        "amount_usd": "100.2500",
    }
    row.update(overrides)
    return row


def _activity_row(**overrides: object) -> dict:
    row = {
        "event": "withdraw",
        "address": ADDRESS_A,
        "project": "ether.fi",
        "blockchain": "arbitrum",
        "tx_hash": TX_B,
        "block_time": "2026-08-02T13:00:00Z",
        "amount_usd": "-5.50",
        "token_symbol": "eETH",
        "label": "Withdrawal",
    }
    row.update(overrides)
    return row


def _holding_row(**overrides: object) -> dict:
    row = {
        "day": "2026-08-02",
        "address": ADDRESS_A,
        "strategy_symbol": "liquidETH",
        "base_asset": "WETH",
        "depositor_type": "New Depositor",
        "referral_balance": "100",
        "previous_balance": "0",
        "total_current_balance": "85",
        "campaign_supported_balance": "85",
        "final_attributable_balance": "85",
        "exited_balance": "15",
        "current_token": "liquidETH",
        "current_token_category": "Liquid",
        "current_balance": "60",
        "attributed_balance": "60",
        "unattributed_balance": "0",
        "destination_status": "active",
        "allocation_rank": 1,
        "allocation_rule": "rule_b_current_positions_fit",
        "methodology_id": "kyberswap_attributed_holdings_v1",
        "source_query_id": ATTRIBUTED_HOLDINGS_QUERY_ID,
        "source_execution_id": "holdings-execution",
        "source_last_updated": "2026-08-03T03:20:03Z",
        "generated_at": "2026-08-03T03:20:03Z",
    }
    row.update(overrides)
    return row


def _holdings() -> list[dict]:
    return [
        _holding_row(),
        _holding_row(
            current_token="weETH",
            current_token_category="Restaking",
            current_balance="25",
            attributed_balance="25",
            allocation_rank=2,
        ),
        _holding_row(
            current_token="Exited",
            current_token_category="Exited",
            current_balance="0",
            attributed_balance="15",
            unattributed_balance="0",
            destination_status="exited",
            allocation_rank=3,
        ),
    ]


def test_referral_deposits_normalize_exact_schema_and_provenance() -> None:
    result = prepare_kyberswap_referral_deposits(
        [_deposit_row()],
        source_query_id=REFERRAL_DEPOSITS_QUERY_ID,
        source_execution_id="deposit-execution",
        source_last_updated=UPDATED,
        generated_at=UPDATED,
        source_columns=REFERRAL_DEPOSITS_SOURCE_COLUMNS,
    )

    assert result.columns == list(REFERRAL_DEPOSITS_OUTPUT_COLUMNS)
    assert result.rows == [
        {
            "tx_hash": TX_A,
            "address": ADDRESS_A,
            "blockchain": "ethereum",
            "block_time": "2026-08-02T12:00:00Z",
            "strategy_symbol": "liquidETH",
            "amount_usd": "100.25",
            "source_query_id": REFERRAL_DEPOSITS_QUERY_ID,
            "source_execution_id": "deposit-execution",
            "source_last_updated": UPDATED,
            "generated_at": UPDATED,
        }
    ]
    assert result.summary["total_amount_usd"] == "100.25"


@pytest.mark.parametrize("value", [None, "NaN", "Infinity", -1])
def test_referral_deposits_reject_invalid_or_negative_amount(value: object) -> None:
    with pytest.raises(KyberSwapDepositorIntelligenceError, match="amount_usd"):
        _prepare_deposits([_deposit_row(amount_usd=value)])


def test_source_schema_and_supported_chain_are_strict() -> None:
    with pytest.raises(KyberSwapDepositorIntelligenceError, match="schema mismatch"):
        prepare_kyberswap_referral_deposits(
            [_deposit_row()],
            source_query_id=REFERRAL_DEPOSITS_QUERY_ID,
            source_execution_id="deposit-execution",
            source_last_updated=UPDATED,
            generated_at=UPDATED,
            source_columns=(*REFERRAL_DEPOSITS_SOURCE_COLUMNS, "unexpected"),
        )
    with pytest.raises(KyberSwapDepositorIntelligenceError, match="unsupported"):
        _prepare_deposits([_deposit_row(blockchain="solana")])


def test_activity_preserves_signed_amount_and_sorts_newest_first() -> None:
    result = prepare_kyberswap_etherfi_activity(
        [
            _activity_row(),
            _activity_row(
                tx_hash=TX_C,
                block_time="2026-08-02T14:00:00+00:00",
                event="deposit",
                amount_usd="10.00",
                label="Deposit",
            ),
        ],
        source_query_id=ETHERFI_ACTIVITY_QUERY_ID,
        source_execution_id="activity-execution",
        source_last_updated="2026-08-03T05:20:03Z",
        generated_at="2026-08-03T05:20:03Z",
        source_columns=ETHERFI_ACTIVITY_SOURCE_COLUMNS,
    )

    assert result.columns == list(ETHERFI_ACTIVITY_OUTPUT_COLUMNS)
    assert [row["tx_hash"] for row in result.rows] == [TX_C, TX_B]
    assert result.rows[1]["amount_usd"] == "-5.5"
    assert result.summary["negative_amount_rows"] == 1
    assert result.summary["net_amount_usd"] == "4.5"


def test_event_sorting_treats_fractional_seconds_chronologically() -> None:
    deposits = _prepare_deposits(
        [
            _deposit_row(block_time="2026-08-02T12:00:00Z"),
            _deposit_row(
                tx_hash=TX_C,
                block_time="2026-08-02T12:00:00.500000Z",
            ),
        ]
    )

    assert [row["tx_hash"] for row in deposits] == [TX_C, TX_A]


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), "-Infinity"])
def test_activity_rejects_null_or_non_finite_amount(value: object) -> None:
    with pytest.raises(KyberSwapDepositorIntelligenceError, match="amount_usd"):
        _prepare_activity([_activity_row(amount_usd=value)])


def test_wallet_index_deduplicates_group_values_and_reconciles() -> None:
    deposits = _prepare_deposits(
        [
            _deposit_row(),
            _deposit_row(
                tx_hash=TX_C,
                block_time="2026-08-02T15:00:00Z",
                amount_usd="15",
            ),
        ]
    )
    activity = _prepare_activity([_activity_row()])
    result = build_kyberswap_depositor_intelligence(
        _holdings(),
        deposits,
        activity,
        source_execution_ids={
            ATTRIBUTED_HOLDINGS_QUERY_ID: "holdings-execution",
            REFERRAL_DEPOSITS_QUERY_ID: "deposit-execution",
            ETHERFI_ACTIVITY_QUERY_ID: "activity-execution",
        },
    )
    payload = validate_kyberswap_depositor_intelligence(result.payload)
    wallet = payload["wallets"][0]

    assert payload["wallet_index"] == {ADDRESS_A: 0}
    assert wallet["total_referral_deposits_usd"] == "100"
    assert wallet["attributed_tvl_usd"] == "85"
    assert wallet["exited_balance_usd"] == "15"
    assert wallet["retention_rate"] == "0.85"
    assert wallet["products_deposited"] == ["liquidETH"]
    assert wallet["current_tokens"] == ["liquidETH", "weETH"]
    assert wallet["current_token_categories"] == ["Liquid", "Restaking"]
    assert wallet["latest_referral_deposit_time"] == "2026-08-02T15:00:00Z"
    assert wallet["latest_referral_deposit_usd"] == "15"
    assert wallet["latest_activity_amount_usd"] == "-5.5"
    assert [row["exited_balance_usd"] for row in wallet["positions"]] == [
        "0",
        "0",
        "15",
    ]
    assert result.summary["reconciliation_delta_usd"] == "0"
    assert payload["concentration"]["referral_deposits"]["tiers"][0] == {
        "top_n": 1,
        "value_usd": "100",
        "share": "1",
    }


def test_wallet_output_and_checksum_are_deterministic() -> None:
    deposits = _prepare_deposits([_deposit_row()])
    activity = _prepare_activity([_activity_row()])
    first = build_kyberswap_depositor_intelligence(
        list(reversed(_holdings())), deposits, activity
    ).payload
    second = build_kyberswap_depositor_intelligence(
        _holdings(), deposits, activity
    ).payload
    assert first == second
    assert first["generated_at"] == "2026-08-03T05:20:03Z"

    tampered = deepcopy(first)
    tampered["wallets"][0]["attributed_tvl_usd"] = "84"
    with pytest.raises(KyberSwapDepositorIntelligenceError, match="concentration"):
        validate_kyberswap_depositor_intelligence(tampered)


def test_wallet_summary_sums_one_referral_balance_per_product() -> None:
    second_product = [
        _holding_row(
            strategy_symbol="liquidUSD",
            referral_balance="40",
            total_current_balance="30",
            campaign_supported_balance="30",
            final_attributable_balance="30",
            exited_balance="10",
            current_token="liquidUSD",
            current_token_category="Liquid",
            current_balance="30",
            attributed_balance="30",
            allocation_rank=1,
        ),
        _holding_row(
            strategy_symbol="liquidUSD",
            referral_balance="40",
            total_current_balance="30",
            campaign_supported_balance="30",
            final_attributable_balance="30",
            exited_balance="10",
            current_token="Exited",
            current_token_category="Exited",
            current_balance="0",
            attributed_balance="10",
            destination_status="exited",
            allocation_rank=2,
        ),
    ]
    payload = build_kyberswap_depositor_intelligence(
        [*_holdings(), *second_product],
        _prepare_deposits([_deposit_row()]),
        _prepare_activity([_activity_row()]),
    ).payload
    wallet = payload["wallets"][0]

    assert wallet["products_deposited"] == ["liquidETH", "liquidUSD"]
    assert wallet["num_products_deposited"] == 2
    assert wallet["total_referral_deposits_usd"] == "140"
    assert wallet["attributed_tvl_usd"] == "115"
    assert wallet["exited_balance_usd"] == "25"
    assert wallet["retention_rate"].startswith("0.821428571428")


def test_cross_source_wallet_coverage_must_reconcile() -> None:
    deposits = _prepare_deposits([_deposit_row(address=ADDRESS_B)])
    activity = _prepare_activity([_activity_row()])
    with pytest.raises(
        KyberSwapDepositorIntelligenceError,
        match="cross-source wallet coverage",
    ):
        build_kyberswap_depositor_intelligence(_holdings(), deposits, activity)


def test_sub_cent_orphan_referral_deposit_is_an_explicit_warning() -> None:
    deposits = _prepare_deposits(
        [
            _deposit_row(),
            _deposit_row(address=ADDRESS_B, amount_usd="0.00000000000040905515"),
        ]
    )
    result = build_kyberswap_depositor_intelligence(
        _holdings(),
        deposits,
        _prepare_activity([_activity_row()]),
    )

    assert result.payload["wallet_index"] == {ADDRESS_A: 0}
    assert result.warnings[0] == {
        "code": "immaterial_orphan_referral_deposit",
        "wallet_count": 1,
        "event_count": 1,
        "amount_usd": "0.00000000000040905515",
        "threshold_usd": "0.005",
        "message": (
            "Sub-cent referral-deposit events without a matching attributed-holdings "
            "wallet were excluded from wallet summaries and retained in the validated "
            "source artifact"
        ),
    }


def test_holdings_reconciliation_rejects_duplicate_group_exit_value() -> None:
    broken = _holdings()
    broken[1]["exited_balance"] = "14"
    with pytest.raises(
        KyberSwapDepositorIntelligenceError,
        match="conflicting balances",
    ):
        build_kyberswap_depositor_intelligence(
            broken,
            _prepare_deposits([_deposit_row()]),
            _prepare_activity([_activity_row()]),
        )
