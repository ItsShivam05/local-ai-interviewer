"""What a cloud call costs. Groq meters tokens per model (prices per million tokens).
The app is built around two models, and these are their rates from Groq's own model table (console.groq.com/docs/models, read
18 Nov 2026): openai/gpt-oss-120b $0.15 in / $0.60 out; openai/gpt-oss-20b $0.075 in / $0.30 out. On Groq's Free plan requests
are not billed at all (they are rate-limited instead), so on that plan these figures only show what the same use WOULD cost.
Cached input may be cheaper; replies do not say how much was cached, so estimates use the full input price (an upper bound).
Prices change: every value is a default and can be edited in Settings -> AI models (edits are kept, defaults update with the app).
The off-peak fields are kept for custom price entries (no default model uses them).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class ModelPrice(BaseModel):
    """US dollars per million tokens. The off-peak fields apply only to models that have an off-peak rate."""

    input_per_m: float = Field(ge=0, le=10_000)
    output_per_m: float = Field(ge=0, le=10_000)
    offpeak_input_per_m: Optional[float] = Field(default=None, ge=0, le=10_000)
    offpeak_output_per_m: Optional[float] = Field(default=None, ge=0, le=10_000)


GRADER_MODEL, SMALL_MODEL = "openai/gpt-oss-120b", "openai/gpt-oss-20b"
DEFAULT_PRICES: dict[str, ModelPrice] = {
    GRADER_MODEL: ModelPrice(input_per_m=0.15, output_per_m=0.6),
    SMALL_MODEL: ModelPrice(input_per_m=0.075, output_per_m=0.3),
}


def is_peak(at: datetime) -> bool:
    """Peak = 12:00-18:00 UTC on Monday-Friday."""
    u = at.astimezone(timezone.utc)
    return u.weekday() < 5 and 12 <= u.hour < 18


def normalise(model: str) -> str:
    """One spelling per model, for comparing names and finding prices: lower case, and the short form 'gpt-oss-120b' is the same
    model as Groq's full id 'openai/gpt-oss-120b'. Other ids (including custom ones) are only lower-cased."""
    m = model.strip().lower()
    return f"openai/{m}" if re.fullmatch(r"gpt-oss-[a-z0-9.\-]+", m) else m


def find_price(model: str, prices: dict[str, ModelPrice]) -> Optional[ModelPrice]:
    wanted = normalise(model)
    for name, price in prices.items():
        if normalise(name) == wanted:
            return price
    return None


def cost_usd(price: Optional[ModelPrice], prompt_tokens: Optional[int], output_tokens: Optional[int], at: datetime) -> Optional[float]:
    """Estimated cost in dollars, or None when the model has no price (so it is reported as unknown, not as free)."""
    if price is None:
        return None
    off = not is_peak(at) and price.offpeak_input_per_m is not None and price.offpeak_output_per_m is not None
    rate_in = price.offpeak_input_per_m if off else price.input_per_m
    rate_out = price.offpeak_output_per_m if off else price.output_per_m
    return round(((prompt_tokens or 0) * float(rate_in) + (output_tokens or 0) * float(rate_out)) / 1_000_000, 6)
