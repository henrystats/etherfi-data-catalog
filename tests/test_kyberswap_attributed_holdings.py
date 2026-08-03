from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

import pytest

from scripts.enrich_kyberswap_attributed_holdings import (
    ENRICHED_COLUMNS,
    METHODOLOGY_ID,
    METHODOLOGY_VERSION,
    SOURCE_QUERY_ID,
    SOURCE_REQUIRED_COLUMNS,
    KyberSwapAttributionError,
    enrich_kyberswap_attributed_holdings,
)


ADDRESS_A = "0x1111111111111111111111111111111111111111"
ADDRESS_B = "0x2222222222222222222222222222222222222222"
ADDRESS_C = "0x3333333333333333333333333333333333333333"
ADDRESS_D = "0x4444444444444444444444444444444444444444"
def source_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "day": "2026-07-30",
        "address": ADDRESS_A,
        "strategy_symbol": "eETH",
        "base_asset": "WETH",
        "depositor_type": "New Depositor",
        "current_token": "weETH",
        "current_token_category": "Ether.fi token",
        "referral_balance": "250",
        "current_balance": "200",
        "previous_balance": "0",
    }
    row.update(overrides)
    return row


def enrich(rows: list[dict[str, object]]):
    return enrich_kyberswap_attributed_holdings(
        rows,
        source_query_id=SOURCE_QUERY_ID,
        source_execution_id="execution-8199058-test",
        source_last_updated="2026-07-31T11:30:00Z",
        generated_at="2026-08-01T01:00:00+01:00",
        source_columns=SOURCE_REQUIRED_COLUMNS,
    )


def rows_for_strategy(result, strategy_symbol: str) -> list[dict]:
    return [
        row for row in result.rows if row["strategy_symbol"] == strategy_symbol
    ]


def balances_by_token(rows: list[dict]) -> dict[str, Decimal]:
    return {
        row["current_token"]: Decimal(row["attributed_balance"]) for row in rows
    }


def decimal_sum(values) -> Decimal:
    return sum((Decimal(value) for value in values), Decimal(0))


def test_basic_cap_uses_rule_c_largest_balance_first() -> None:
    result = enrich(
        [
            source_row(current_token="weETH", current_balance="200"),
            source_row(
                current_token="liquidETH",
                current_balance="150",
                current_token_category="Ether.fi product",
            ),
        ]
    )

    assert balances_by_token(result.rows) == {
        "weETH": Decimal("200"),
        "liquidETH": Decimal("50"),
    }
    assert [row["current_token"] for row in result.rows] == [
        "weETH",
        "liquidETH",
    ]
    assert [row["allocation_rank"] for row in result.rows] == [1, 2]
    assert {row["allocation_rule"] for row in result.rows} == {
        "rule_c_largest_balance_first"
    }
    assert result.rows[1]["unattributed_balance"] == "100"
    assert result.rows[0]["final_attributable_balance"] == "250"
    assert result.rows[0]["exited_balance"] == "0"
    assert result.summary["total_attributed_value_usd"] == "250"
    assert result.summary["total_exited_value_usd"] == "0"


@pytest.mark.parametrize(
    ("balances", "expected_exit"),
    [
        (("100", "150"), "0"),
        (("80", "120"), "50"),
    ],
    ids=["sum-equals-referral-cap", "sum-below-referral-cap"],
)
def test_current_positions_at_or_below_cap_use_rule_b_and_reconcile_exit(
    balances: tuple[str, str], expected_exit: str
) -> None:
    result = enrich(
        [
            source_row(current_token="weETH", current_balance=balances[0]),
            source_row(
                current_token="liquidETH",
                current_balance=balances[1],
                current_token_category="Ether.fi product",
            ),
        ]
    )

    active_rows = [row for row in result.rows if row["destination_status"] == "active"]
    exited_rows = [row for row in result.rows if row["destination_status"] == "exited"]
    assert decimal_sum(row["attributed_balance"] for row in active_rows) == Decimal(
        balances[0]
    ) + Decimal(balances[1])
    assert all(
        row["attributed_balance"] == row["current_balance"] for row in active_rows
    )
    assert {row["allocation_rule"] for row in result.rows} == {
        "rule_b_current_positions_fit"
    }
    assert decimal_sum(row["attributed_balance"] for row in exited_rows) == Decimal(
        expected_exit
    )
    assert (
        decimal_sum(row["attributed_balance"] for row in result.rows)
        == Decimal("250")
    )


def test_one_destination_above_cap_uses_rule_d_and_preserves_smaller_first() -> None:
    result = enrich(
        [
            source_row(current_token="weETH", current_balance="300"),
            source_row(
                current_token="liquidETH",
                current_balance="150",
                current_token_category="Ether.fi product",
            ),
        ]
    )

    assert balances_by_token(result.rows) == {
        "liquidETH": Decimal("150"),
        "weETH": Decimal("100"),
    }
    assert [row["current_token"] for row in result.rows] == [
        "liquidETH",
        "weETH",
    ]
    assert {row["allocation_rule"] for row in result.rows} == {
        "rule_d_preserve_smaller_then_oversized"
    }
    assert result.rows[1]["unattributed_balance"] == "200"


def test_multiple_destinations_above_cap_use_rule_e() -> None:
    result = enrich(
        [
            source_row(current_token="weETH", current_balance="300"),
            source_row(
                current_token="liquidETH",
                current_balance="280",
                current_token_category="Ether.fi product",
            ),
        ]
    )

    assert balances_by_token(result.rows) == {
        "weETH": Decimal("250"),
        "liquidETH": Decimal("0"),
    }
    assert {row["allocation_rule"] for row in result.rows} == {
        "rule_e_multiple_destinations_reach_cap"
    }
    assert result.rows[0]["allocation_rank"] == 1
    assert result.rows[0]["current_token"] == "weETH"


def test_existing_depositor_baseline_is_subtracted_once_when_fully_supported() -> None:
    result = enrich(
        [
            source_row(
                referral_balance="100",
                previous_balance="100",
                current_balance="200",
                depositor_type="Existing Depositor",
            )
        ]
    )

    row = result.rows[0]
    assert row["total_current_balance"] == "200"
    assert row["campaign_supported_balance"] == "100"
    assert row["final_attributable_balance"] == "100"
    assert row["attributed_balance"] == "100"
    assert row["exited_balance"] == "0"
    assert result.summary["existing_depositors"] == 1
    assert result.summary["new_depositors"] == 0


def test_dynamic_source_depositor_type_is_preserved_without_changing_attribution() -> None:
    result = enrich(
        [
            source_row(
                referral_balance="100",
                current_balance="100",
                depositor_type="Returning Depositor",
            )
        ]
    )

    assert result.rows[0]["depositor_type"] == "Returning Depositor"
    assert result.rows[0]["attributed_balance"] == "100"
    assert result.summary["depositor_types"] == ["Returning Depositor"]
    assert result.summary["unclassified_depositors"] == 1
    assert result.warnings == [
        {
            "code": "unexpected_depositor_type",
            "depositor_type": "Returning Depositor",
            "message": "Unexpected depositor type Returning Depositor was retained",
        }
    ]


def test_past_depositor_is_a_supported_source_classification() -> None:
    result = enrich([source_row(depositor_type="Past Depositor")])

    assert result.rows[0]["depositor_type"] == "Past Depositor"
    assert result.summary["past_depositors"] == 1
    assert result.summary["unclassified_depositors"] == 0
    assert not any(
        warning["code"] == "unexpected_depositor_type"
        for warning in result.warnings
    )


def test_existing_depositor_baseline_partial_retention_creates_partial_exit() -> None:
    result = enrich(
        [
            source_row(
                referral_balance="100",
                previous_balance="100",
                current_balance="150",
                depositor_type="Existing Depositor",
            )
        ]
    )

    assert balances_by_token(result.rows) == {
        "weETH": Decimal("50"),
        "Exited": Decimal("50"),
    }
    active, exited = result.rows
    assert active["campaign_supported_balance"] == "50"
    assert active["final_attributable_balance"] == "50"
    assert active["unattributed_balance"] == "100"
    assert exited["destination_status"] == "exited"
    assert exited["current_balance"] == "0"
    assert exited["current_token_category"] == "Exited"


def test_existing_depositor_below_baseline_uses_rule_a_and_fully_exits() -> None:
    result = enrich(
        [
            source_row(
                referral_balance="100",
                previous_balance="100",
                current_balance="80",
                depositor_type="Existing Depositor",
            )
        ]
    )

    assert balances_by_token(result.rows) == {
        "weETH": Decimal("0"),
        "Exited": Decimal("100"),
    }
    assert {row["allocation_rule"] for row in result.rows} == {
        "rule_a_no_current_attributable_balance"
    }
    assert result.rows[0]["campaign_supported_balance"] == "0"
    assert result.rows[0]["final_attributable_balance"] == "0"
    assert result.summary["total_attributed_value_usd"] == "0"
    assert result.summary["total_exited_value_usd"] == "100"


def test_empty_position_becomes_only_a_synthetic_exited_destination() -> None:
    result = enrich(
        [
            source_row(
                referral_balance="100",
                current_token="Empty",
                current_balance="0",
                current_token_category=None,
            )
        ]
    )

    assert len(result.rows) == 1
    exited = result.rows[0]
    assert exited["current_token"] == "Exited"
    assert exited["current_token_category"] == "Exited"
    assert exited["destination_status"] == "exited"
    assert exited["current_balance"] == "0"
    assert exited["attributed_balance"] == "100"
    assert exited["allocation_rank"] == 1
    assert result.summary["uncategorized_destination_count"] == 0
    assert result.warnings == []


def test_same_wallet_in_multiple_products_is_capped_independently() -> None:
    result = enrich(
        [
            source_row(
                referral_balance="100",
                current_balance="80",
                depositor_type="Existing Depositor",
            ),
            source_row(
                strategy_symbol="liquidETH",
                base_asset="WBTC",
                referral_balance="50",
                previous_balance="25",
                current_token="liquidETH",
                current_balance="100",
                current_token_category="Ether.fi product",
                depositor_type="Existing Depositor",
            ),
        ]
    )

    eeth_rows = rows_for_strategy(result, "eETH")
    liquid_eth_rows = rows_for_strategy(result, "liquidETH")
    assert balances_by_token(eeth_rows) == {
        "weETH": Decimal("80"),
        "Exited": Decimal("20"),
    }
    assert balances_by_token(liquid_eth_rows) == {"liquidETH": Decimal("50")}
    assert liquid_eth_rows[0]["campaign_supported_balance"] == "75"
    assert liquid_eth_rows[0]["final_attributable_balance"] == "50"
    assert result.summary["unique_addresses"] == 1
    assert result.summary["unique_address_product_groups"] == 2
    assert result.summary["total_referral_value_usd"] == "150"
    assert result.summary["total_attributed_value_usd"] == "130"
    assert result.summary["total_exited_value_usd"] == "20"


def test_rule_d_with_three_smaller_destinations_uses_balance_then_token_order() -> None:
    result = enrich(
        [
            source_row(current_token="weETH", current_balance="300"),
            source_row(
                current_token="Pendle",
                current_balance="80",
                current_token_category="DeFi",
            ),
            source_row(
                current_token="Spark",
                current_balance="90",
                current_token_category="DeFi",
            ),
            source_row(
                current_token="Aave",
                current_balance="80",
                current_token_category="DeFi",
            ),
        ]
    )

    assert [row["current_token"] for row in result.rows] == [
        "Spark",
        "Aave",
        "Pendle",
        "weETH",
    ]
    assert balances_by_token(result.rows) == {
        "Spark": Decimal("90"),
        "Aave": Decimal("80"),
        "Pendle": Decimal("80"),
        "weETH": Decimal("0"),
    }
    assert [row["allocation_rank"] for row in result.rows] == [1, 2, 3, 4]
    assert {row["allocation_rule"] for row in result.rows} == {
        "rule_d_preserve_smaller_then_oversized"
    }


def test_equal_rule_c_balances_and_reordered_rows_are_deterministic() -> None:
    rows = [
        source_row(
            referral_balance="150",
            current_token=token,
            current_balance="100",
            current_token_category="DeFi",
        )
        for token in ("Spark", "Aave", "Pendle")
    ]

    forward = enrich(rows)
    reverse = enrich(list(reversed(rows)))

    assert forward.rows == reverse.rows
    assert forward.summary == reverse.summary
    assert forward.warnings == reverse.warnings
    assert [row["current_token"] for row in forward.rows] == [
        "Aave",
        "Pendle",
        "Spark",
    ]
    assert balances_by_token(forward.rows) == {
        "Aave": Decimal("100"),
        "Pendle": Decimal("50"),
        "Spark": Decimal("0"),
    }


def test_equal_rule_e_balances_choose_token_ascending_independent_of_row_order() -> None:
    rows = [
        source_row(
            referral_balance="100",
            current_token="weETH",
            current_balance="150",
        ),
        source_row(
            referral_balance="100",
            current_token="Aave",
            current_balance="150",
            current_token_category="DeFi",
        ),
    ]

    forward = enrich(rows)
    reverse = enrich(list(reversed(rows)))

    assert forward.rows == reverse.rows
    assert [row["current_token"] for row in forward.rows] == ["Aave", "weETH"]
    assert balances_by_token(forward.rows) == {
        "Aave": Decimal("100"),
        "weETH": Decimal("0"),
    }
    assert {row["allocation_rule"] for row in forward.rows} == {
        "rule_e_multiple_destinations_reach_cap"
    }


@pytest.mark.parametrize(
    "field",
    [
        "referral_balance",
        "current_balance",
        "previous_balance",
    ],
)
def test_null_numeric_fields_are_rejected(field: str) -> None:
    with pytest.raises(
        KyberSwapAttributionError,
        match=rf"field {field} must be an exact decimal value",
    ):
        enrich([source_row(**{field: None})])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("referral_balance", "-1", "must not be negative"),
        ("previous_balance", "-1", "must not be negative"),
    ],
)
def test_negative_group_values_are_rejected(
    field: str, value: str, message: str
) -> None:
    with pytest.raises(
        KyberSwapAttributionError,
        match=rf"field {field} {message}",
    ):
        enrich([source_row(**{field: value})])


def test_negative_nonempty_balance_is_normalized_to_zero_with_warning() -> None:
    result = enrich(
        [
            source_row(
                referral_balance="50",
                current_token="Aave",
                current_balance="-5",
                current_token_category="DeFi",
            ),
            source_row(
                referral_balance="50",
                current_token="weETH",
                current_balance="20",
            ),
        ]
    )

    assert balances_by_token(result.rows) == {
        "weETH": Decimal("20"),
        "Aave": Decimal("0"),
        "Exited": Decimal("30"),
    }
    aave = next(row for row in result.rows if row["current_token"] == "Aave")
    assert aave["current_balance"] == "0"
    assert aave["unattributed_balance"] == "0"
    assert result.rows[0]["total_current_balance"] == "20"
    assert [warning["code"] for warning in result.warnings] == [
        "negative_current_balance_normalized"
    ]
    assert result.warnings[0]["current_token"] == "Aave"


def test_negative_empty_balance_is_ignored_with_warning_and_full_exit() -> None:
    result = enrich(
        [
            source_row(
                referral_balance="50",
                current_token="Empty",
                current_balance="-0.0001",
                current_token_category=None,
            )
        ]
    )

    assert len(result.rows) == 1
    assert result.rows[0]["current_token"] == "Exited"
    assert result.rows[0]["attributed_balance"] == "50"
    assert result.warnings == [
        {
            "code": "negative_current_balance_normalized",
            "group": (
                "day=2026-07-30, "
                f"address={ADDRESS_A}, strategy_symbol=eETH"
            ),
            "current_token": "Empty",
        }
    ]


def test_duplicate_source_grain_is_rejected() -> None:
    row = source_row()
    with pytest.raises(KyberSwapAttributionError, match="duplicate source grain"):
        enrich([row, dict(row)])


def test_conflicting_repeated_referral_balances_are_rejected() -> None:
    with pytest.raises(
        KyberSwapAttributionError,
        match="conflicting repeated referral_balance values",
    ):
        enrich(
            [
                source_row(referral_balance="100", current_token="weETH"),
                source_row(
                    referral_balance="101",
                    current_token="Aave",
                    current_token_category="DeFi",
                ),
            ]
        )


def test_conflicting_repeated_previous_balances_are_rejected() -> None:
    with pytest.raises(
        KyberSwapAttributionError,
        match="conflicting repeated previous_balance values",
    ):
        enrich(
            [
                source_row(previous_balance="10", current_token="weETH"),
                source_row(
                    previous_balance="11",
                    current_token="Aave",
                    current_token_category="DeFi",
                ),
            ]
        )


def test_equivalent_decimal_spellings_are_consistent_group_values() -> None:
    result = enrich(
        [
            source_row(
                referral_balance="100.0",
                previous_balance="10.00",
                current_token="weETH",
                current_balance="60",
            ),
            source_row(
                referral_balance="100.00",
                previous_balance="10.0",
                current_token="Aave",
                current_balance="50",
                current_token_category="DeFi",
            ),
        ]
    )

    assert all(row["referral_balance"] == "100" for row in result.rows)
    assert all(row["previous_balance"] == "10" for row in result.rows)
    assert decimal_sum(row["attributed_balance"] for row in result.rows) == Decimal(
        "100"
    )


def test_exact_source_schema_rejects_missing_and_unexpected_row_columns() -> None:
    row = source_row()
    del row["depositor_type"]

    with pytest.raises(
        KyberSwapAttributionError,
        match="schema mismatch: missing depositor_type",
    ):
        enrich([row])

    with pytest.raises(
        KyberSwapAttributionError,
        match="schema mismatch: unexpected base_asset_price",
    ):
        enrich([source_row(base_asset_price="2")])


def test_declared_latest_result_schema_must_be_exact() -> None:
    with pytest.raises(
        KyberSwapAttributionError,
        match="latest-result schema mismatch: missing depositor_type; unexpected old_type",
    ):
        enrich_kyberswap_attributed_holdings(
            [source_row()],
            source_query_id=SOURCE_QUERY_ID,
            source_execution_id="execution",
            source_last_updated="2026-07-31T11:30:00Z",
            generated_at="2026-08-01T00:00:00Z",
            source_columns=tuple(
                "old_type" if column == "depositor_type" else column
                for column in SOURCE_REQUIRED_COLUMNS
            ),
        )


def test_nonempty_destination_without_category_is_preserved_and_warned() -> None:
    result = enrich(
        [
            source_row(
                referral_balance="50",
                current_balance="50",
                current_token_category=None,
            )
        ]
    )

    assert result.rows[0]["current_token"] == "weETH"
    assert result.rows[0]["current_token_category"] == "Uncategorized"
    assert result.rows[0]["attributed_balance"] == "50"
    assert result.summary["uncategorized_destination_count"] == 1
    assert result.warnings == [
        {
            "code": "uncategorized_destination",
            "group": (
                "day=2026-07-30, "
                f"address={ADDRESS_A}, strategy_symbol=eETH"
            ),
            "current_token": "weETH",
        }
    ]


def test_empty_with_positive_balance_is_invalid() -> None:
    with pytest.raises(
        KyberSwapAttributionError,
        match="has Empty with a positive current_balance",
    ):
        enrich(
            [
                source_row(
                    current_token="Empty",
                    current_balance="0.000000000000000001",
                    current_token_category=None,
                )
            ]
        )


def test_very_large_decimal_values_remain_exact() -> None:
    referral = "9" * 120

    result = enrich(
        [
            source_row(
                referral_balance=referral,
                current_balance=referral,
            )
        ]
    )

    row = result.rows[0]
    assert row["referral_balance"] == referral
    assert row["current_balance"] == referral
    assert row["attributed_balance"] == referral
    assert result.summary["total_referral_value_usd"] == referral
    assert result.summary["total_attributed_value_usd"] == referral
    assert result.summary["reconciliation_delta_usd"] == "0"


def test_fractional_usd_values_reconcile_exactly_without_float_rounding() -> None:
    result = enrich(
        [
            source_row(
                referral_balance="0.3",
                previous_balance="0.1",
                current_balance="0.25",
                depositor_type="Existing Depositor",
            )
        ]
    )

    assert balances_by_token(result.rows) == {
        "weETH": Decimal("0.15"),
        "Exited": Decimal("0.15"),
    }
    active = next(row for row in result.rows if row["destination_status"] == "active")
    exited = next(row for row in result.rows if row["destination_status"] == "exited")
    assert active["attributed_balance"] == "0.15"
    assert active["unattributed_balance"] == "0.1"
    assert exited["attributed_balance"] == "0.15"
    assert result.summary["total_referral_value_usd"] == "0.3"
    assert result.summary["total_attributed_value_usd"] == "0.15"
    assert result.summary["total_exited_value_usd"] == "0.15"
    assert (
        Decimal(result.summary["total_referral_value_usd"])
        == Decimal(result.summary["total_attributed_value_usd"])
        + Decimal(result.summary["total_exited_value_usd"])
    )
    assert decimal_sum(row["attributed_balance"] for row in result.rows) == Decimal(
        "0.3"
    )


def test_enriched_rows_carry_exact_schema_provenance_and_conservative_freshness() -> None:
    result = enrich(
        [
            source_row(),
            source_row(
                current_token="Aave",
                current_balance="50",
                current_token_category="DeFi",
            ),
        ]
    )

    assert result.source_last_updated == "2026-07-31T11:30:00Z"
    assert result.summary["source_last_updated"] == "2026-07-31T11:30:00Z"
    assert result.summary["source_rows"] == 2
    assert result.summary["unique_addresses"] == 1
    assert result.summary["unique_address_product_groups"] == 1
    for row in result.rows:
        assert tuple(row) == ENRICHED_COLUMNS
        assert row["methodology_id"] == METHODOLOGY_ID
        assert row["source_query_id"] == SOURCE_QUERY_ID
        assert row["source_execution_id"] == "execution-8199058-test"
        assert row["source_last_updated"] == "2026-07-31T11:30:00Z"
        assert row["generated_at"] == "2026-08-01T00:00:00Z"
        assert not any(column.endswith("_usd") for column in row)
        assert "base_asset_price" not in row

    assert SOURCE_QUERY_ID == 8199058
    assert METHODOLOGY_VERSION == "2.0.0"


def test_two_and_three_stage_sankey_flows_conserve_enriched_row_values() -> None:
    result = enrich(
        [
            source_row(
                address=ADDRESS_A,
                strategy_symbol="eETH",
                referral_balance="250",
                current_token="weETH",
                current_balance="200",
                current_token_category="Ether.fi token",
            ),
            source_row(
                address=ADDRESS_A,
                strategy_symbol="eETH",
                referral_balance="250",
                current_token="liquidETH",
                current_balance="150",
                current_token_category="Ether.fi product",
            ),
            source_row(
                address=ADDRESS_B,
                strategy_symbol="eETH",
                referral_balance="100",
                previous_balance="100",
                current_token="Aave",
                current_balance="150",
                current_token_category="DeFi",
                depositor_type="Existing Depositor",
            ),
            source_row(
                address=ADDRESS_C,
                strategy_symbol="liquidBTC",
                base_asset="WBTC",
                referral_balance="2",
                current_token="weETHk",
                current_balance="1",
                current_token_category="Ether.fi token",
            ),
            source_row(
                address=ADDRESS_D,
                strategy_symbol="liquidUSD",
                base_asset="USD",
                referral_balance="100",
                current_token="USDe",
                current_balance="120",
                current_token_category="Stablecoin",
            ),
            source_row(
                address=ADDRESS_D,
                strategy_symbol="liquidUSD",
                base_asset="USD",
                referral_balance="100",
                current_token="sUSDe",
                current_balance="110",
                current_token_category="Stablecoin",
            ),
        ]
    )

    represented_rows: list[tuple[dict, Decimal]] = []
    for row in result.rows:
        value = Decimal(row["attributed_balance"])
        if value > 0:
            represented_rows.append((row, value))

    product_to_location: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)
    depositor_type_to_product: defaultdict[tuple[str, str], Decimal] = defaultdict(
        Decimal
    )
    product_to_category: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for row, value in represented_rows:
        product_to_location[(row["strategy_symbol"], row["current_token"])] += value
        depositor_type_to_product[
            (row["depositor_type"], row["strategy_symbol"])
        ] += value
        product_to_category[
            (row["strategy_symbol"], row["current_token_category"])
        ] += value

    assert all(value > 0 for value in product_to_location.values())
    assert all(value > 0 for value in depositor_type_to_product.values())
    assert all(value > 0 for value in product_to_category.values())
    assert ("liquidUSD", "sUSDe") not in product_to_location
    assert product_to_location[("eETH", "Exited")] == Decimal("50")
    assert product_to_location[("liquidBTC", "Exited")] == Decimal("1")
    assert product_to_category[("eETH", "Exited")] == Decimal("50")

    strategies = {row["strategy_symbol"] for row, _ in represented_rows}
    for strategy_symbol in strategies:
        location_total = sum(
            (
                value
                for (source, _), value in product_to_location.items()
                if source == strategy_symbol
            ),
            Decimal(0),
        )
        first_stage_total = sum(
            (
                value
                for (_, target), value in depositor_type_to_product.items()
                if target == strategy_symbol
            ),
            Decimal(0),
        )
        second_stage_total = sum(
            (
                value
                for (source, _), value in product_to_category.items()
                if source == strategy_symbol
            ),
            Decimal(0),
        )
        assert location_total == first_stage_total == second_stage_total

    represented_total = sum((value for _, value in represented_rows), Decimal(0))
    assert represented_total == Decimal(result.summary["total_referral_value_usd"])
    assert represented_total == sum(product_to_location.values(), Decimal(0))
    assert represented_total == sum(depositor_type_to_product.values(), Decimal(0))
    assert represented_total == sum(product_to_category.values(), Decimal(0))


def test_accepts_dune_utc_day_and_execution_timestamp_formats():
    row = source_row()
    row["day"] = "2026-08-01 00:00:00.000 UTC"

    result = enrich_kyberswap_attributed_holdings(
        [row],
        source_query_id=SOURCE_QUERY_ID,
        source_execution_id="execution",
        source_last_updated="2026-08-01 00:55:09.186611 UTC",
        generated_at="2026-08-01T01:00:00Z",
        source_columns=SOURCE_REQUIRED_COLUMNS,
    )

    assert {item["day"] for item in result.rows} == {"2026-08-01"}
    assert result.source_last_updated == "2026-08-01T00:55:09.186611Z"


def test_execution_source_last_updated_requires_a_timezone():
    with pytest.raises(
        KyberSwapAttributionError,
        match="source_last_updated must include a timezone",
    ):
        enrich_kyberswap_attributed_holdings(
            [source_row()],
            source_query_id=SOURCE_QUERY_ID,
            source_execution_id="execution",
            source_last_updated="2026-08-01 00:55:09.186611",
            generated_at="2026-08-01T01:00:00Z",
            source_columns=SOURCE_REQUIRED_COLUMNS,
        )
