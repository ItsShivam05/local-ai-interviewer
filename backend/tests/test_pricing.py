"""What a cloud call costs. Prices verified against Groq's model table; custom price entries may carry an off-peak rate."""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.pricing import DEFAULT_PRICES, ModelPrice, cost_usd, find_price, is_peak, normalise

UTC = timezone.utc
WED_NOON = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)      # a Wednesday


# Groq's model table (console.groq.com/docs/models; USD per 1M tokens: input, output), copied on 18 Nov 2026, for the two models the app uses.
PUBLISHED = {"openai/gpt-oss-120b": (0.15, 0.60), "openai/gpt-oss-20b": (0.075, 0.30)}
GRADER, SMALL = "openai/gpt-oss-120b", "openai/gpt-oss-20b"
# A user-added price with an off-peak rate (no default model has one, but the price editor still supports it).
OFFPEAK = ModelPrice(input_per_m=0.30, output_per_m=1.20, offpeak_input_per_m=0.15, offpeak_output_per_m=0.60)


def test_the_two_models_have_exactly_the_published_prices():
    assert set(DEFAULT_PRICES) == set(PUBLISHED)
    for name, row in PUBLISHED.items():
        p = DEFAULT_PRICES[name]
        assert (p.input_per_m, p.output_per_m) == row[:2], name
        assert (p.offpeak_input_per_m, p.offpeak_output_per_m) == (row[2:] if len(row) == 4 else (None, None)), name


def test_no_default_model_has_an_off_peak_rate_and_nothing_of_the_old_provider_remains():
    assert all(p.offpeak_input_per_m is None and p.offpeak_output_per_m is None for p in DEFAULT_PRICES.values())
    assert not any(":" in name or "deepseek" in name or "gemma" in name for name in DEFAULT_PRICES)


def test_cost_is_tokens_times_the_per_million_price():
    assert cost_usd(DEFAULT_PRICES[GRADER], 900, 450, WED_NOON) == 0.000405
    assert cost_usd(DEFAULT_PRICES[SMALL], 1000, 1000, WED_NOON) == 0.000375        # 0.000075 + 0.0003
    assert cost_usd(DEFAULT_PRICES[GRADER], 1_000_000, 1_000_000, WED_NOON) == 0.75
    assert cost_usd(DEFAULT_PRICES[GRADER], None, None, WED_NOON) == 0.0


@pytest.mark.parametrize("when, peak", [
    (datetime(2026, 11, 4, 11, 59, tzinfo=UTC), False), (datetime(2026, 11, 4, 12, 0, tzinfo=UTC), True), (datetime(2026, 11, 4, 17, 59, tzinfo=UTC), True),
    (datetime(2026, 11, 4, 18, 0, tzinfo=UTC), False),                                        # Wednesday boundaries
    (datetime(2026, 11, 7, 14, 0, tzinfo=UTC), False), (datetime(2026, 11, 8, 14, 0, tzinfo=UTC), False),   # Saturday / Sunday afternoon
    (datetime(2026, 11, 6, 17, 0, tzinfo=UTC), True), (datetime(2026, 11, 9, 12, 0, tzinfo=UTC), True),     # Friday / Monday
])
def test_peak_is_weekdays_12_to_18_utc(when, peak):
    assert is_peak(when) is peak


def test_peak_is_decided_in_utc_whatever_the_local_timezone():
    india = timezone(timedelta(hours=5, minutes=30))
    assert is_peak(datetime(2026, 11, 4, 17, 30, tzinfo=india)) is True       # 12:00 UTC
    assert is_peak(datetime(2026, 11, 4, 17, 29, tzinfo=india)) is False      # 11:59 UTC


def test_a_price_with_an_off_peak_rate_costs_double_at_peak_and_models_without_one_never_change():
    ds, gpt = OFFPEAK, DEFAULT_PRICES[GRADER]
    peak, off = WED_NOON, datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    assert cost_usd(ds, 1000, 1000, peak) == 0.0015 and cost_usd(ds, 1000, 1000, off) == 0.00075
    assert cost_usd(gpt, 1000, 1000, peak) == cost_usd(gpt, 1000, 1000, off)


def test_a_model_without_a_price_is_unknown_not_free():
    assert find_price("acme-future-1", DEFAULT_PRICES) is None
    assert cost_usd(None, 1000, 1000, WED_NOON) is None


@pytest.mark.parametrize("name", ["openai/gpt-oss-120b", "OpenAI/GPT-OSS-120B", "gpt-oss-120b", " gpt-oss-120b ", "GPT-OSS-120b"])
def test_the_full_and_short_spellings_find_the_same_price(name):
    assert find_price(name, DEFAULT_PRICES) is DEFAULT_PRICES[GRADER]
    assert normalise(name) == GRADER


@pytest.mark.parametrize("name, same", [("qwen/qwen3.8-27b", "qwen/qwen3.8-27b"), ("My-Org/Custom", "my-org/custom"), ("llama-3.3-70b-versatile", "llama-3.3-70b-versatile"),
                                        ("gpt-oss:120b", "gpt-oss:120b")])
def test_other_and_custom_ids_are_only_lower_cased(name, same):
    """Including the old Ollama spelling: it is NOT silently mapped to a Groq model (the migration resets model names instead)."""
    assert normalise(name) == same


def test_prices_are_validated():
    with pytest.raises(ValueError):
        ModelPrice(input_per_m=-1, output_per_m=1)
    with pytest.raises(ValueError):
        ModelPrice(input_per_m=1, output_per_m=1e9)
