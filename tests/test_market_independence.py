import ast
from dataclasses import fields
from pathlib import Path

import pytest

import pitchvalue.markets as markets
from pitchvalue.markets.contracts import (
    BookmakerPrice,
    MarketNormalizationResult,
    MarketStatus,
)

MARKETS_ROOT = Path(__file__).parents[1] / "src" / "pitchvalue" / "markets"
SOURCE_FILES = tuple(sorted(MARKETS_ROOT.glob("*.py")))


def imported_modules() -> set[str]:
    modules: set[str] = set()
    for path in SOURCE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
    return modules


def package_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8").lower() for path in SOURCE_FILES)


@pytest.mark.parametrize(
    "forbidden_root",
    [
        "sqlalchemy",
        "psycopg",
        "fastapi",
        "httpx",
        "requests",
        "urllib",
    ],
)
def test_market_math_has_no_database_http_or_api_dependency(
    forbidden_root: str,
) -> None:
    assert all(
        module != forbidden_root and not module.startswith(f"{forbidden_root}.")
        for module in imported_modules()
    )


@pytest.mark.parametrize(
    "forbidden_module",
    [
        "pitchvalue.models.poisson",
        "pitchvalue.models.elo",
        "pitchvalue.models.form",
        "pitchvalue.models.signals",
    ],
)
def test_market_math_has_no_model_or_agreement_dependency(
    forbidden_module: str,
) -> None:
    assert all(not module.startswith(forbidden_module) for module in imported_modules())


@pytest.mark.parametrize(
    "provider_name",
    [
        "bet365",
        "pinnacle",
        "william hill",
        "betfair",
        "football-data.co.uk",
    ],
)
def test_no_provider_specific_implementation(provider_name: str) -> None:
    assert provider_name not in package_source()


def test_no_runtime_clock_or_randomness() -> None:
    source = package_source()
    assert "datetime.now" not in source
    assert "datetime.utcnow" not in source
    assert "import random" not in source


def test_no_edge_or_publication_fields_in_normalization_result() -> None:
    names = {field.name for field in fields(MarketNormalizationResult)}
    assert (
        not {
            "edge",
            "expected_value",
            "bet_score",
            "publication_eligible",
            "pick",
            "watchlist",
        }
        & names
    )


def test_no_sportsbook_outbound_contract_fields() -> None:
    names = {field.name for field in fields(BookmakerPrice)}
    assert (
        not {
            "affiliate_link",
            "bonus_code",
            "redirect_url",
            "bet_now",
            "acquisition_tracking",
        }
        & names
    )


def test_no_bookmaker_aggregation_api_is_exported() -> None:
    exported = set(markets.__all__)
    assert (
        not {
            "best_price",
            "consensus_price",
            "average_odds",
            "median_odds",
            "closing_price",
            "opening_price",
        }
        & exported
    )


def test_required_market_statuses_are_explicit() -> None:
    assert {
        MarketStatus.READY,
        MarketStatus.INCOMPLETE_MARKET,
        MarketStatus.NON_EXCLUSIVE_MARKET,
        MarketStatus.INVALID_ODDS,
        MarketStatus.INVALID_MARKET_GROUP,
        MarketStatus.UNSUPPORTED_MARKET,
        MarketStatus.UNSUPPORTED_NORMALIZATION_METHOD,
    } == set(MarketStatus)
