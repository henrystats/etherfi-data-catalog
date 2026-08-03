from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import random


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "studio" / "data"
DEFAULT_REFRESHED_AT = datetime(2026, 7, 29, 18, 40, tzinfo=timezone.utc)
TOKENS = ("weETH", "WETH", "USDC", "USDT")
PRODUCTS = ("Kyber LP", "Liquid ETH", "Liquid USD", "Pendle PT", "Aave")


def wallet(index: int) -> str:
    return "0x" + f"{index * 7919 + 17:040x}"


def tx_hash(index: int) -> str:
    return "0x" + f"{index * 104729 + 97:064x}"


def daily_series(days: int, end: datetime, *, seed: int, base: float) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    level = base
    for offset in range(days):
        day = end - timedelta(days=days - 1 - offset)
        seasonal = math.sin(offset / 17) * base * 0.004
        deposits = max(28_000, rng.lognormvariate(12.0, 0.43))
        withdrawals = max(18_000, rng.lognormvariate(11.72, 0.46))
        level = max(base * 0.72, level + deposits - withdrawals + seasonal)
        active_users = int(150 + offset * 0.72 + rng.randint(-22, 28))
        rows.append(
            {
                "day": day.date().isoformat(),
                "tvl_usd": round(level, 2),
                "deposits_usd": round(deposits, 2),
                "withdrawals_usd": round(withdrawals, 2),
                "fees_usd": round(deposits * rng.uniform(0.0007, 0.0018), 2),
                "active_users": max(20, active_users),
                "total_value_usd": round(level * 18.4, 2),
            }
        )
    return rows


def top_users(count: int, *, seed: int, value_scale: float) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for index in range(1, count + 1):
        value = value_scale / (index ** 0.72) * rng.uniform(0.92, 1.08)
        deposits = value * rng.uniform(1.02, 1.8)
        rows.append(
            {
                "rank": index,
                "wallet": wallet(index + seed * 100),
                "attributed_tvl_usd": round(value, 2),
                "value_usd": round(value, 2),
                "total_deposits_usd": round(deposits, 2),
                "products": rng.randint(1, 4),
                "retained": index % 7 != 0,
            }
        )
    return rows


def recent_events(
    count: int,
    *,
    seed: int,
    refreshed_at: datetime,
    event_type: str,
) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for index in range(count):
        timestamp = refreshed_at - timedelta(hours=index * rng.uniform(2.3, 8.1))
        amount_usd = rng.lognormvariate(10.65, 0.74)
        base = {
            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "wallet": wallet(seed * 200 + index),
            "amount_usd": round(amount_usd, 2),
        }
        if event_type == "deposit":
            token = rng.choice(TOKENS)
            token_price = 3_650 if token in {"weETH", "WETH"} else 1
            base.update(
                {
                    "product": rng.choice(PRODUCTS),
                    "token": token,
                    "amount_token": round(amount_usd / token_price, 4),
                    "tx_hash": tx_hash(seed * 200 + index),
                }
            )
        else:
            base.update(
                {
                    "previous_location": rng.choice(PRODUCTS),
                    "destination": rng.choice(("Wallet", "Aave", "Pendle", "Exited")),
                    "exit_type": "Full" if index % 4 == 0 else "Partial",
                }
            )
        rows.append(base)
    return rows


def build_kyberswap(refreshed_at: datetime) -> dict:
    timeseries = daily_series(420, refreshed_at, seed=41, base=24_800_000)
    users = top_users(100, seed=13, value_scale=2_850_000)
    total_tvl = timeseries[-1]["tvl_usd"]
    total_deposits = sum(row["deposits_usd"] for row in timeseries)
    return {
        "meta": {
            "dashboard_id": "kyberswap_campaign",
            "status": "demo",
            "last_refreshed": refreshed_at.isoformat().replace("+00:00", "Z"),
            "freshness_status": "current",
            "sample_data": True,
            "generator": "scripts/generate_studio_demo_data.py",
        },
        "datasets": {
            "campaign_summary": [
                {
                    "total_attributed_tvl_usd": round(total_tvl, 2),
                    "total_deposits_usd": round(total_deposits, 2),
                    "unique_users": 4_862,
                    "retention_rate": 0.683,
                    "tvl_change_30d_pct": 0.084,
                    "deposits_change_30d_pct": 0.112,
                    "users_change_30d_pct": 0.057,
                    "retention_change_30d_pp": 0.021,
                }
            ],
            "campaign_timeseries": timeseries,
            "product_breakdown": [
                {"product": "Kyber LP", "tvl_usd": round(total_tvl * 0.31, 2)},
                {"product": "Liquid ETH", "tvl_usd": round(total_tvl * 0.27, 2)},
                {"product": "Liquid USD", "tvl_usd": round(total_tvl * 0.18, 2)},
                {"product": "Pendle PT", "tvl_usd": round(total_tvl * 0.14, 2)},
                {"product": "Aave", "tvl_usd": round(total_tvl * 0.10, 2)},
            ],
            "top_users": users,
            "eligible_location": [
                {"location": "Kyber pools", "balance_usd": round(total_tvl * 0.34, 2)},
                {"location": "Liquid vaults", "balance_usd": round(total_tvl * 0.29, 2)},
                {"location": "Wallet", "balance_usd": round(total_tvl * 0.17, 2)},
                {"location": "Pendle", "balance_usd": round(total_tvl * 0.12, 2)},
                {"location": "Aave", "balance_usd": round(total_tvl * 0.08, 2)},
            ],
            "capital_journey": [
                {"source": "Kyber deposits", "target": "weETH", "value_usd": 16_800_000},
                {"source": "Kyber deposits", "target": "USDC", "value_usd": 9_700_000},
                {"source": "weETH", "target": "Liquid ETH", "value_usd": 9_900_000},
                {"source": "weETH", "target": "Wallet", "value_usd": 3_200_000},
                {"source": "weETH", "target": "Pendle", "value_usd": 3_700_000},
                {"source": "USDC", "target": "Liquid USD", "value_usd": 5_800_000},
                {"source": "USDC", "target": "Aave", "value_usd": 2_100_000},
                {"source": "USDC", "target": "Exited", "value_usd": 1_800_000},
                {"source": "Liquid ETH", "target": "Retained", "value_usd": 8_500_000},
                {"source": "Liquid ETH", "target": "Exited", "value_usd": 1_400_000},
                {"source": "Liquid USD", "target": "Retained", "value_usd": 4_900_000},
                {"source": "Liquid USD", "target": "Exited", "value_usd": 900_000},
            ],
            "product_adoption": [
                {"source": "New wallets", "target": "weETH", "users": 2_980},
                {"source": "New wallets", "target": "Stablecoins", "users": 1_882},
                {"source": "weETH", "target": "Kyber LP", "users": 1_490},
                {"source": "weETH", "target": "Liquid ETH", "users": 1_050},
                {"source": "weETH", "target": "Pendle", "users": 440},
                {"source": "Stablecoins", "target": "Liquid USD", "users": 1_040},
                {"source": "Stablecoins", "target": "Aave", "users": 542},
                {"source": "Stablecoins", "target": "Wallet", "users": 300},
            ],
            "recent_deposits": recent_events(
                44,
                seed=19,
                refreshed_at=refreshed_at,
                event_type="deposit",
            ),
            "recent_exits": recent_events(
                31,
                seed=23,
                refreshed_at=refreshed_at,
                event_type="exit",
            ),
        },
    }


def write_payload(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic Studio sample data.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--refreshed-at",
        default=DEFAULT_REFRESHED_AT.isoformat(),
        help="ISO timestamp embedded in generated metadata.",
    )
    args = parser.parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    refreshed_at = datetime.fromisoformat(args.refreshed_at.replace("Z", "+00:00"))
    if refreshed_at.tzinfo is None:
        refreshed_at = refreshed_at.replace(tzinfo=timezone.utc)

    write_payload(output_dir / "kyberswap.json", build_kyberswap(refreshed_at))
    print(f"Generated Studio sample data in {output_dir}")


if __name__ == "__main__":
    main()
