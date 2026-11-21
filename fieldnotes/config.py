"""All operational defaults; no credentials in configuration records."""
from dataclasses import asdict, dataclass
from datetime import date
import math
from pathlib import Path
import re
from .storage import read_json
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Config:
    model: str = "gemini-3.5-flash-lite"
    temperature: float = 1.0
    thinking_level: str = "high"
    max_output_tokens: int = 16384
    max_edge: int = 0
    apply_orientation: bool = False
    max_request_bytes: int = 19_000_000
    max_pages: int = 40
    timeout: float = 180
    attempts: int = 5
    rpm: float = 1
    daily_limit: int = 500
    quota_timezone: str = "America/Los_Angeles"
    quota_file: str = "local/fieldnotes-quota.json"
    retry_base: float = 60
    max_retry_wait: float = 600
    rates: dict | None = None

    def __post_init__(self):
        ZoneInfo(self.quota_timezone)
        if type(self.apply_orientation) is not bool:
            raise ValueError("apply_orientation must be boolean")
        if not re.fullmatch(r"gemini-[A-Za-z0-9._-]+", self.model):
            raise ValueError("Use an explicit Gemini model ID; no automatic provider fallback.")
        if self.thinking_level not in {"minimal", "low", "medium", "high"}:
            raise ValueError("Unsupported thinking level")
        if type(self.temperature) not in (float, int) or not math.isfinite(self.temperature) or not 0 <= self.temperature <= 2:
            raise ValueError("Temperature must be between 0 and 2")
        for name in ("max_output_tokens", "max_request_bytes", "max_pages", "attempts", "daily_limit"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.max_edge) is not int or self.max_edge < 0:
            raise ValueError("max_edge must be a nonnegative integer")
        for name in ("timeout", "rpm", "retry_base", "max_retry_wait"):
            value = getattr(self, name)
            if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")
        if self.max_retry_wait < 60:
            raise ValueError("max_retry_wait must be at least 60 seconds")
        if self.attempts > 10 or self.timeout > 900:
            raise ValueError("At most ten attempts and 900 seconds per attempt")
        if self.rates is not None:
            if not isinstance(self.rates, dict) or not all(isinstance(self.rates.get(k), str) and self.rates[k].strip()
                    for k in ("currency", "as_of", "source", "model")):
                raise ValueError("Rates need currency, as_of, source and model")
            if not re.fullmatch(r"[A-Z]{3}", self.rates["currency"]) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", self.rates["as_of"]):
                raise ValueError("Rates need a three-letter currency code and YYYY-MM-DD as_of date")
            date.fromisoformat(self.rates["as_of"])
            for key in ("input", "cached", "output"):
                value = self.rates.get(key)
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError("Rates must be nonnegative prices per million tokens")

    def generation(self):
        return dict(temperature=self.temperature, max_output_tokens=self.max_output_tokens,
                    thinking_config={"thinking_level": self.thinking_level.upper()},
                    response_mime_type="application/json",
                    automatic_function_calling={"disable": True})

    def public(self):
        return asdict(self)


def load_config(path=None):
    if path and not Path(path).is_file():
        raise ValueError(f"Configuration not found: {path}")
    return Config(**(read_json(path, {}) if path else {}))
