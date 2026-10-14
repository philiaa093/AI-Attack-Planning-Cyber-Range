"""Provider-reported token accounting; no SDK, network or inference dispatch.

Prices are dated text-token snapshots, not invoices. Unknown usage, rate/tier,
region or cache-write TTL never becomes a zero-dollar observation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from pathlib import Path


LIMIT = 16 * 1024 * 1024
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")


def identifier(value):
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError("bounded accounting identifier required")
    return value


def count(value):
    if type(value) is not int or not 0 <= value <= 10**9:
        raise ValueError("bounded integer token count required")
    return value


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_timestamp(value):
    if type(value) is not str:
        raise ValueError("UTC timestamp required")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
        raise ValueError("UTC timestamp required")
    return value


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def no_links(path):
    for parent in (path, *path.parents):
        if parent.is_symlink() or parent.is_junction():
            raise ValueError("accounting path must not contain links/junctions")


def load_json_bytes(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate accounting JSON key")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def read_verified(path, expected_sha256):
    path = Path(path).absolute()
    no_links(path)
    if type(expected_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("expected SHA-256 required")
    with path.open("rb") as stream:
        data = stream.read(LIMIT + 1)
    if len(data) > LIMIT or sha(data) != expected_sha256:
        raise ValueError("accounting artifact size/hash mismatch")
    return load_json_bytes(data)


@dataclass(frozen=True)
class TokenUsage:
    provider: str
    api: str
    response_id: str
    model: str
    service_tier: str
    region: str
    input_uncached: int
    output_tokens: int
    cached_read: int = 0
    cache_write: int = 0
    cache_write_1h: int = 0
    cache_write_unknown_ttl: int = 0
    reasoning_tokens: int = 0

    def __post_init__(self):
        if type(self.provider) is not str or type(self.api) is not str:
            raise ValueError("typed provider/API required")
        if (self.provider, self.api) not in {
            ("openai", "responses"), ("openai", "chat_completions"), ("anthropic", "messages")
        }:
            raise ValueError("supported provider/API required")
        for value in (self.response_id, self.model, self.service_tier, self.region):
            identifier(value)
        for value in (self.input_uncached, self.output_tokens, self.cached_read, self.cache_write,
                      self.cache_write_1h, self.cache_write_unknown_ttl, self.reasoning_tokens):
            count(value)
        if self.reasoning_tokens > self.output_tokens:
            raise ValueError("reasoning tokens must be included in output total")


class UsageExtractor:
    @staticmethod
    def from_sdk(response, **context):
        """Use the SDK's authoritative usage, not a local tokenizer estimate."""
        if type(response) is dict:
            payload = response
        else:
            dump = getattr(response, "model_dump", None)
            if not callable(dump):
                raise ValueError("SDK response supporting model_dump required")
            payload = dump(mode="json")
        return UsageExtractor.extract(payload, **context)

    @staticmethod
    def extract(response, *, provider, api, resolved_tier=None, region="global"):
        """Accept a detached SDK model_dump(mode='json') or a response dictionary.

        Capture after the final response; streaming deltas are not added together.
        If the API omits tier, a trusted adapter supplies its resolved billing tier.
        Missing usage returns None; malformed numeric metadata raises.
        """
        if type(response) is not dict:
            raise ValueError("detached provider response dictionary required")
        usage = response.get("usage")
        if usage is None:
            return None
        if type(usage) is not dict:
            raise ValueError("provider usage object required")
        tier = response.get("service_tier") or usage.get("service_tier") or resolved_tier
        if tier in (None, "auto"):
            raise ValueError("resolved service tier required")
        reported_region = response.get("inference_geo") or usage.get("inference_geo")
        if reported_region is not None:
            region = reported_region
        common = dict(provider=provider, api=api, response_id=response.get("id"),
                      model=response.get("model"), service_tier=tier, region=region)
        if provider == "openai" and api in ("responses", "chat_completions"):
            chat = api == "chat_completions"
            incoming = count(usage.get("prompt_tokens" if chat else "input_tokens"))
            outgoing = count(usage.get("completion_tokens" if chat else "output_tokens"))
            details = usage.get("prompt_tokens_details" if chat else "input_tokens_details")
            if type(details) is not dict or "cached_tokens" not in details:
                raise ValueError("cache usage breakdown required for pricing")
            cached = count(details["cached_tokens"])
            written = count(details.get("cache_write_tokens", 0))
            output_details = usage.get("completion_tokens_details" if chat else "output_tokens_details") or {}
            if type(output_details) is not dict:
                raise ValueError("output token details object required")
            if count(details.get("audio_tokens", 0)) or count(output_details.get("audio_tokens", 0)):
                raise ValueError("audio billing requires a separate rate card and token buckets")
            if cached + written > incoming:
                raise ValueError("cache buckets exceed inclusive input total")
            if "total_tokens" in usage and count(usage["total_tokens"]) != incoming + outgoing:
                raise ValueError("provider total token mismatch")
            return TokenUsage(**common, input_uncached=incoming - cached - written,
                              cached_read=cached, cache_write=written, output_tokens=outgoing,
                              reasoning_tokens=count(output_details.get("reasoning_tokens", 0)))
        if provider == "anthropic" and api == "messages":
            # Anthropic input_tokens EXCLUDES cache reads/writes; do not subtract them.
            written = count(usage.get("cache_creation_input_tokens", 0))
            details = usage.get("cache_creation")
            short, long, unknown = 0, 0, written
            if details is not None:
                if type(details) is not dict:
                    raise ValueError("cache creation breakdown required")
                short = count(details.get("ephemeral_5m_input_tokens", 0))
                long = count(details.get("ephemeral_1h_input_tokens", 0))
                if short + long != written:
                    raise ValueError("cache creation TTL buckets mismatch")
                unknown = 0
            output_details = usage.get("output_tokens_details") or {}
            if type(output_details) is not dict:
                raise ValueError("output token details object required")
            return TokenUsage(**common, input_uncached=count(usage.get("input_tokens")),
                              output_tokens=count(usage.get("output_tokens")),
                              cached_read=count(usage.get("cache_read_input_tokens", 0)),
                              cache_write=short, cache_write_1h=long, cache_write_unknown_ttl=unknown,
                              reasoning_tokens=count(output_details.get("thinking_tokens", 0)))
        raise ValueError("unsupported usage endpoint")


@dataclass(frozen=True)
class RateCard:
    provider: str
    model: str
    service_tier: str
    region: str
    input_per_million: str
    output_per_million: str
    cached_per_million: str
    write_per_million: str | None
    write_1h_per_million: str | None
    version: str
    source_url: str
    checked_at_utc: str

    def __post_init__(self):
        for value in (self.provider, self.model, self.service_tier, self.region, self.version):
            identifier(value)
        for value in (self.input_per_million, self.output_per_million, self.cached_per_million,
                      self.write_per_million, self.write_1h_per_million):
            if value is not None and (type(value) is not str or not re.fullmatch(r"\d{1,5}(?:\.\d{1,9})?", value)):
                raise ValueError("exact bounded decimal rate string required")
        if any(value is None for value in (self.input_per_million, self.output_per_million, self.cached_per_million)):
            raise ValueError("base rates cannot be unknown")
        utc_timestamp(self.checked_at_utc)
        if type(self.source_url) is not str or len(self.source_url) > 1024 or not self.source_url.startswith("https://"):
            raise ValueError("rate source HTTPS URL required")


def official_rate_cards():
    """Examples verified 2026-10-12; unsupported model/tier/region needs a new card.

    Exact response model strings are matched; no inferred prefix aliases. These
    are standard first-party text rates, excluding tool fees, taxes and discounts.
    """
    return (
        RateCard("openai", "gpt-4.1-mini", "default", "global", "0.40", "1.60", "0.10", None, None,
                 "public-text-20261012", "https://developers.openai.com/api/docs/pricing",
                 "2026-10-12T10:36:01Z"),
        RateCard("anthropic", "claude-sonnet-4-6", "standard", "global", "3", "15", "0.30", "3.75", "6",
                 "public-text-20261012", "https://platform.claude.com/docs/en/about-claude/pricing",
                 "2026-10-12T10:36:01Z"),
        # Explicit snapshot listed on the official GPT-4.1 Mini model page.
        RateCard("openai", "gpt-4.1-mini-2025-04-14", "default", "global", "0.40", "1.60", "0.10", None, None,
                 "public-text-20261012", "https://developers.openai.com/api/docs/models/gpt-4.1-mini",
                 "2026-10-12T10:36:01Z"),
    )


class PricingCalculator:
    def __init__(self, rate_cards=None):
        self.cards = tuple(official_rate_cards() if rate_cards is None else rate_cards)
        if not self.cards or any(type(c) is not RateCard for c in self.cards):
            raise ValueError("immutable validated rate cards required")
        keys = [(c.provider, c.model, c.service_tier, c.region) for c in self.cards]
        if len(set(keys)) != len(keys):
            raise ValueError("ambiguous rate cards")

    def quote(self, usage):
        if type(usage) is not TokenUsage:
            raise ValueError("TokenUsage required")
        usage.__post_init__()
        key = usage.provider, usage.model, usage.service_tier, usage.region
        card = next((c for c in self.cards if (c.provider, c.model, c.service_tier, c.region) == key), None)
        if card is None or usage.cache_write_unknown_ttl:
            raise ValueError("rate/model/tier/region/cache TTL unresolved")
        card.__post_init__()
        buckets = ((usage.input_uncached, card.input_per_million), (usage.output_tokens, card.output_per_million),
                   (usage.cached_read, card.cached_per_million), (usage.cache_write, card.write_per_million),
                   (usage.cache_write_1h, card.write_1h_per_million))
        if any(tokens and rate is None for tokens, rate in buckets):
            raise ValueError("cache-write rate unresolved")
        with localcontext() as context:
            context.prec = 50
            total = sum((Decimal(tokens) * Decimal(rate or "0") for tokens, rate in buckets), Decimal(0)) / Decimal(10**6)
        return dict(token_cost_usd=format(total, "f"), currency="USD", basis="PROVIDER_USAGE_X_RATE_CARD",
                    actual_billed_usd=None, rate_card=asdict(card), rate_card_sha256=sha(canonical(asdict(card))))


@dataclass(frozen=True)
class MeteredReviewResponse:
    """Adapter keeps accounting metadata separate from the closed planner JSON."""
    review_json: str
    usage: TokenUsage | None

    def __post_init__(self):
        if type(self.review_json) is not str or len(self.review_json.encode()) > LIMIT:
            raise ValueError("bounded minimized planner JSON required")
        if self.usage is not None and type(self.usage) is not TokenUsage:
            raise ValueError("typed provider usage required")

    @classmethod
    def capture(cls, sdk_response, *, review_json, **billing_context):
        return cls(review_json, UsageExtractor.from_sdk(sdk_response, **billing_context))


class UsageLedger:
    """Single-writer, exclusive per-call files; seal once, no raw prompts/keys.

    Owner supplies episode/run identities and source. Hashes detect alteration,
    not provider authenticity. No hostile concurrent filesystem sandbox claimed.
    """
    def __init__(self, parent, *, run_id, source="PROVIDER_REPORTED"):
        self.run_id = identifier(run_id)
        if source not in ("PROVIDER_REPORTED", "SIMULATED_FIXTURE"):
            raise ValueError("explicit usage source required")
        self.source = source
        parent = Path(parent).absolute()
        no_links(parent)
        parent.mkdir(parents=True, exist_ok=True)
        self.root = parent.resolve() / ("USAGE-" + uuid.uuid4().hex)
        self.root.mkdir(exist_ok=False)
        self.refs, self.identities = [], {}
        self.sealed = False

    def _write(self, name, value):
        no_links(self.root)
        path = self.root / name
        no_links(path)
        data = canonical(value)
        if len(data) > LIMIT:
            raise ValueError("usage record too large")
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return dict(name=name, sha256=sha(data))

    def record(self, *, episode_id, usage):
        if self.sealed:
            raise ValueError("sealed usage ledger")
        identifier(episode_id)
        if usage is not None and type(usage) is not TokenUsage:
            raise ValueError("typed usage required")
        if usage is not None:
            usage.__post_init__()
        value = dict(schema_version=1, run_id=self.run_id, episode_id=episode_id,
                     source=self.source, redaction="TOKEN_METADATA_ONLY", created_at_utc=utc_now(),
                     usage=None if usage is None else asdict(usage))
        identity = uuid.uuid4().hex if usage is None else usage.provider + ":" + usage.response_id
        signature = sha(canonical(dict(episode_id=episode_id, usage=value["usage"])))
        if identity in self.identities:
            previous, ref = self.identities[identity]
            if previous != signature:
                raise ValueError("conflicting response identity/binding")
            return ref
        ref = self._write("call-" + sha(identity.encode()) + ".json", value)
        self.identities[identity] = signature, ref
        self.refs.append(ref)
        return ref

    def planner_sink(self, request, usage):
        if request.state.context.run_id != self.run_id:
            raise ValueError("usage run identity mismatch")
        return self.record(episode_id=request.state.context.episode_id, usage=usage)

    def seal(self):
        if self.sealed:
            raise ValueError("usage ledger already sealed")
        ref = self._write("ledger.json", dict(schema_version=1, run_id=self.run_id, source=self.source,
                                               created_at_utc=utc_now(), events=self.refs))
        self.sealed = True
        return self.root / ref["name"], ref["sha256"]


def summarize_ledger(path, expected_sha256, calculator=None):
    """Verify every log ref and price recorded calls, including refused output.

    Missing usage/unpriced calls keep the complete total null. Known subtotals
    remain visible. Duplicate response IDs cannot inflate or misattribute cost.
    """
    calculator = PricingCalculator() if calculator is None else calculator
    manifest = read_verified(path, expected_sha256)
    if type(manifest) is not dict or set(manifest) != {"schema_version", "run_id", "source", "created_at_utc", "events"}:
        raise ValueError("closed usage ledger manifest required")
    identifier(manifest["run_id"])
    utc_timestamp(manifest["created_at_utc"])
    if (type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1
            or manifest["source"] not in ("PROVIDER_REPORTED", "SIMULATED_FIXTURE")):
        raise ValueError("usage ledger provenance mismatch")
    events = manifest["events"]
    if type(events) is not list or len(events) > 100_000:
        raise ValueError("bounded usage events required")
    seen, identities, quotes = set(), set(), []
    unknown, subtotal = 0, Decimal(0)
    for ref in events:
        if (type(ref) is not dict or set(ref) != {"name", "sha256"}
                or type(ref["name"]) is not str or not re.fullmatch(r"call-[0-9a-f]{64}\.json", ref["name"])
                or ref["name"] in seen):
            raise ValueError("unique confined usage reference required")
        seen.add(ref["name"])
        event = read_verified(Path(path).parent / ref["name"], ref["sha256"])
        if (type(event) is not dict or set(event) != {"schema_version", "run_id", "episode_id", "source",
                                                    "redaction", "created_at_utc", "usage"}
                or type(event["schema_version"]) is not int or event["schema_version"] != 1
                or event["run_id"] != manifest["run_id"]
                or event["source"] != manifest["source"] or event["redaction"] != "TOKEN_METADATA_ONLY"):
            raise ValueError("usage event provenance mismatch")
        identifier(event["episode_id"])
        utc_timestamp(event["created_at_utc"])
        quote, reason = None, None
        if event["usage"] is None:
            reason = "MISSING_USAGE"
        else:
            if type(event["usage"]) is not dict or set(event["usage"]) != set(TokenUsage.__dataclass_fields__):
                raise ValueError("closed token metadata schema required")
            usage = TokenUsage(**event["usage"])
            identity = usage.provider, usage.response_id
            if identity in identities:
                raise ValueError("duplicate billed response")
            identities.add(identity)
            try:
                quote = calculator.quote(usage)
            except ValueError:
                reason = "UNRESOLVED_RATE_OR_CONTEXT"
        if quote is None:
            unknown += 1
        else:
            subtotal += Decimal(quote["token_cost_usd"])
        quotes.append(dict(episode_id=event["episode_id"], source_ref=ref, quote=quote, unresolved_reason=reason))
    return dict(run_id=manifest["run_id"], source=manifest["source"], calls=len(events), unknown_calls=unknown,
                currency="USD", known_token_subtotal_usd=format(subtotal, "f"),
                token_cost_usd=format(subtotal, "f") if events and not unknown else None,
                actual_billed_usd=None, cost_basis="PROVIDER_USAGE_X_RATE_CARD", calls_detail=quotes,
                source_ledger_sha256=expected_sha256)
