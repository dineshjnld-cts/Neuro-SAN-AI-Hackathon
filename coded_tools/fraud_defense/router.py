"""Risk-aware provider router with explicit offline and fallback behavior."""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.parse import urlunparse
from urllib.request import Request
from urllib.request import urlopen

from coded_tools.fraud_defense.models import RiskLevel


@dataclass
class ProviderConfig:
    """Environment-backed provider configuration; blank model means disabled."""

    name: str
    api_key_env: str
    model_env: str
    base_url_env: str
    role: str
    model: str = ""
    base_url: str = ""
    timeout_seconds: float = 8.0

    @property
    def enabled(self) -> bool:
        """Only attempt a live provider when all values are explicit."""
        return bool(self.model and self.base_url and self.api_key_value)

    @property
    def api_key_value(self) -> str:
        """Read the conventional provider key, with Google's alias supported."""
        return os.getenv(self.api_key_env, "") or (os.getenv("GOOGLE_API_KEY", "") if self.name == "gemini" else "")


@dataclass
class ModelAssessment:
    """A concise, auditable opinion without hidden reasoning trace."""

    provider: str
    model: str
    hypothesis: str
    confidence: float
    rationale_summary: str
    source: str = "offline"
    latency_ms: int = 0
    error: str | None = None

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-compatible assessment."""
        return {
            "provider": self.provider,
            "model": self.model,
            "hypothesis": self.hypothesis,
            "confidence": round(self.confidence, 3),
            "rationale_summary": self.rationale_summary,
            "source": self.source,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


@dataclass
class RoutingDecision:
    """The router's selected tier, providers, and disagreement outcome."""

    risk_level: str
    providers: List[str]
    fallback_used: bool
    disagreement: Dict[str, Any] = field(default_factory=dict)
    assessments: List[Dict[str, Any]] = field(default_factory=list)
    provider_errors: List[Dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-compatible routing record."""
        return {
            "risk_level": self.risk_level,
            "providers": self.providers,
            "fallback_used": self.fallback_used,
            "disagreement": self.disagreement,
            "assessments": self.assessments,
            "provider_errors": self.provider_errors,
        }


class ModelRouter:
    """Route optional provider-backed judgments and retain safe local opinions.

    The generic HTTP adapter is intentionally opt-in: a provider needs a key.
    Cerebras has a verified model and API default; other providers need their
    model and endpoint configured explicitly. This avoids silently sending
    synthetic case data to an unconfigured service.
    """

    def __init__(self, disagreement_threshold: float | None = None):
        configured_threshold = (
            disagreement_threshold
            if disagreement_threshold is not None
            else os.getenv("FRAUD_MODEL_DISAGREEMENT_THRESHOLD", "0.18")
        )
        self.disagreement_threshold = self._bounded_float(configured_threshold, 0.18, 0.0, 1.0)
        self.configs = self._load_configs()

    @staticmethod
    def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
        """Parse a finite float and keep operator configuration within safe bounds."""
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        if not math.isfinite(parsed):
            return default
        return max(minimum, min(maximum, parsed))

    @staticmethod
    def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
        """Parse an integer and keep request/resource limits bounded."""
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, parsed))

    @staticmethod
    def _env_or_default(name: str, default: str) -> str:
        """Use an explicit environment value, including blank as an opt-out."""
        value = os.getenv(name)
        return default if value is None else value.strip()

    @staticmethod
    def _load_configs() -> List[ProviderConfig]:
        """Load provider role configuration without putting it in agent HOCON.

        The JSON file owns provider roles and environment-variable names. Runtime
        model IDs, endpoints, and keys remain operator configuration, so this
        loader never requires a secret or guesses a provider model.
        """
        definitions = [
            ("nvidia", "NVIDIA_API_KEY", "FRAUD_NVIDIA_MODEL", "FRAUD_NVIDIA_BASE_URL", "high-volume worker"),
            ("cerebras", "CEREBRAS_API_KEY", "FRAUD_CEREBRAS_MODEL", "FRAUD_CEREBRAS_BASE_URL", "deep reasoning"),
            ("gemini", "GEMINI_API_KEY", "FRAUD_GEMINI_MODEL", "FRAUD_GEMINI_BASE_URL", "independent review"),
            (
                "sarvam",
                "SARVAM_API_KEY",
                "FRAUD_SARVAM_MODEL",
                "FRAUD_SARVAM_BASE_URL",
                "language and voice extension",
            ),
        ]
        config_path = Path(os.getenv("FRAUD_MODEL_CONFIG_PATH", "config/fraud_defense_models.json"))
        if not config_path.is_absolute():
            config_path = Path(__file__).resolve().parents[2] / config_path
        try:
            file_config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            file_config = {}
        providers = file_config.get("providers", {}) if isinstance(file_config, dict) else {}
        default_timeout = ModelRouter._bounded_float(
            file_config.get("provider_timeout_seconds", 8) if isinstance(file_config, dict) else 8,
            8.0,
            1.0,
            60.0,
        )
        configured_timeout = ModelRouter._bounded_float(
            os.getenv("FRAUD_PROVIDER_TIMEOUT_SECONDS", default_timeout), default_timeout, 1.0, 60.0
        )
        configs = []
        for name, default_key_env, default_model_env, default_url_env, default_role in definitions:
            override = providers.get(name, {}) if isinstance(providers, dict) else {}
            override = override if isinstance(override, dict) else {}
            key_env = str(override.get("api_key_env", default_key_env))
            model_env = str(override.get("model_env", default_model_env))
            url_env = str(override.get("base_url_env", default_url_env))
            role = str(override.get("role", default_role))
            default_model = str(override.get("default_model", ""))
            default_base_url = str(override.get("default_base_url", ""))
            timeout_seconds = ModelRouter._bounded_float(
                override.get("timeout_seconds", configured_timeout), configured_timeout, 1.0, 60.0
            )
            configs.append(
                ProviderConfig(
                    name,
                    key_env,
                    model_env,
                    url_env,
                    role,
                    ModelRouter._env_or_default(model_env, default_model),
                    ModelRouter._env_or_default(url_env, default_base_url),
                    timeout_seconds,
                )
            )
        return configs

    def route(self, level: RiskLevel) -> List[ProviderConfig]:
        """Select providers according to the investigation tier."""
        configured = [config for config in self.configs if config.enabled]
        if level == RiskLevel.LOW:
            return configured[:1]
        if level == RiskLevel.MEDIUM:
            return configured[:1]
        return configured[:3]

    @staticmethod
    def _offline_opinions(signals: Dict[str, Any], graph: Dict[str, Any], level: RiskLevel) -> List[ModelAssessment]:
        """Use independent transparent heuristics when no provider is configured."""
        behavioral = min(0.99, 0.18 + 0.34 * signals.get("sequence_score", 0) + 0.18 * bool(signals.get("new_beneficiary")) + 0.18 * bool(signals.get("new_device")) + 0.12 * min(1, signals.get("amount_anomaly", 0)))
        network = min(0.99, 0.26 + 0.24 * bool(graph.get("campaign_signal")) + 0.16 * min(1, graph.get("component_size", 0) / 20) + 0.16 * bool(signals.get("new_beneficiary")) + 0.12 * bool(signals.get("has_test_then_transfer")))
        conservative = min(0.99, 0.12 + 0.48 * signals.get("risk_score", 0) + 0.08 * bool(signals.get("new_location")))
        hypothesis = "suspected coordinated fraud" if level in {RiskLevel.HIGH, RiskLevel.CRITICAL} else "unusual activity requiring review"
        return [
            ModelAssessment("local_behavioral", "rules-v1", hypothesis, behavioral, "Sequence, novelty, and amount signals."),
            ModelAssessment("local_graph", "graph-v1", hypothesis, network, "Connected entities and campaign structure."),
            ModelAssessment("local_conservative", "risk-v1", hypothesis, conservative, "Risk score with conservative escalation bias."),
        ]

    @staticmethod
    def _prompt(signals: Dict[str, Any], graph: Dict[str, Any], level: RiskLevel) -> str:
        """Create a minimal provider prompt containing no hidden ground truth."""
        payload = {
            "risk_level": level.value,
            "signals": {key: value for key, value in signals.items() if key != "baseline"},
            "graph": {
                key: value
                for key, value in graph.items()
                if key in {"component_size", "linked_accounts", "campaign_signal", "central_entities"}
            },
            "output": "Return JSON with hypothesis, confidence, rationale_summary. Do not include hidden reasoning.",
        }
        return json.dumps(payload, separators=(",", ":"))

    @staticmethod
    def _completion_url(base_url: str) -> str:
        """Normalize an operator-supplied API base URL to chat completions."""
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("Invalid provider endpoint")
        path = parsed.path.rstrip("/")
        if not path.endswith("/chat/completions"):
            path = f"{path}/chat/completions"
        return urlunparse(parsed._replace(path=path))

    @staticmethod
    def _parse_content(content: Any) -> Dict[str, Any]:
        """Parse JSON mode output while tolerating a fenced response from a proxy."""
        if not isinstance(content, str):
            raise ValueError("Provider returned no textual assessment")
        normalized = content.strip()
        if normalized.startswith("```") and normalized.endswith("```"):
            normalized = normalized[3:-3].strip()
            if normalized.lower().startswith("json"):
                normalized = normalized[4:].lstrip()
        parsed = json.loads(normalized)
        if not isinstance(parsed, dict):
            raise ValueError("Provider assessment must be a JSON object")
        return parsed

    @staticmethod
    def _call_provider(config: ProviderConfig, prompt: str) -> ModelAssessment:
        """Call an explicitly configured OpenAI-compatible endpoint safely."""
        started = time.perf_counter()
        payload: Dict[str, Any] = {
            "model": config.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return only a JSON object with hypothesis, confidence, and "
                        "rationale_summary. Do not reveal chain of thought."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_completion_tokens": ModelRouter._bounded_int(
                os.getenv("FRAUD_PROVIDER_MAX_COMPLETION_TOKENS", "256"), 256, 32, 1024
            ),
        }
        if config.name == "cerebras":
            # Cerebras documents these parameters for qwen-3.8-27b. JSON mode
            # keeps the provider response inside the validated assessment schema.
            payload["reasoning_effort"] = "none"
            payload["response_format"] = {"type": "json_object"}
        try:
            request = Request(
                ModelRouter._completion_url(config.base_url),
                data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {config.api_key_value}",
                    "User-Agent": "neuro-san-studio/fraud-war-room",
                },
                method="POST",
            )
            max_response_bytes = ModelRouter._bounded_int(
                os.getenv("FRAUD_PROVIDER_MAX_RESPONSE_BYTES", "65536"), 65536, 1024, 1048576
            )
            with urlopen(  # nosec B310 - endpoint is explicit operator configuration
                request, timeout=config.timeout_seconds
            ) as response:
                raw_response = response.read(max_response_bytes + 1)
            if len(raw_response) > max_response_bytes:
                raise ValueError("Provider response too large")
            response_payload = json.loads(raw_response.decode("utf-8"))
            content = response_payload.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content and response_payload.get("candidates"):
                content = response_payload["candidates"][0].get("content", {}).get("parts", [{}])[0].get("text", "")
            parsed = ModelRouter._parse_content(content)
            hypothesis = str(parsed.get("hypothesis", "")).strip()
            if not hypothesis:
                raise ValueError("Malformed provider assessment")
            if not isinstance(parsed.get("confidence"), (int, float)) or isinstance(parsed["confidence"], bool) or not math.isfinite(parsed["confidence"]) or not 0 <= parsed["confidence"] <= 1:
                raise ValueError("Invalid provider confidence")
            confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.5))))
            rationale = str(parsed.get("rationale_summary", "Provider returned a concise assessment."))[:400]
            return ModelAssessment(
                config.name,
                config.model,
                hypothesis[:200],
                confidence,
                rationale,
                "provider",
                int((time.perf_counter() - started) * 1000),
            )
        except HTTPError as exc:
            return ModelAssessment(
                config.name,
                config.model,
                "provider unavailable",
                0.0,
                "Provider call failed; fallback was used.",
                "error",
                int((time.perf_counter() - started) * 1000),
                f"http_{exc.code}",
            )
        except (
            URLError,
            TimeoutError,
            OSError,
            UnicodeError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
            IndexError,
        ) as exc:
            return ModelAssessment(
                config.name,
                config.model,
                "provider unavailable",
                0.0,
                "Provider call failed; fallback was used.",
                "error",
                int((time.perf_counter() - started) * 1000),
                type(exc).__name__,
            )

    def assess(self, signals: Dict[str, Any], graph: Dict[str, Any], level: RiskLevel) -> RoutingDecision:
        """Produce one or more independent assessments and trigger disagreement."""
        selected = [config for config in self.configs if config.enabled]
        target_count = 3 if level in {RiskLevel.HIGH, RiskLevel.CRITICAL} else 1
        assessments: List[ModelAssessment] = []
        provider_errors: List[Dict[str, Any]] = []
        if selected:
            prompt = self._prompt(signals, graph, level)
            for config in selected:
                assessment = self._call_provider(config, prompt)
                if assessment.source != "error":
                    assessments.append(assessment)
                    if len(assessments) >= target_count:
                        break
                else:
                    provider_errors.append({"provider": assessment.provider, "model": assessment.model, "error": assessment.error})
        if not assessments:
            assessments = self._offline_opinions(signals, graph, level) if level in {RiskLevel.HIGH, RiskLevel.CRITICAL} else self._offline_opinions(signals, graph, level)[:1]
        confidences = [assessment.confidence for assessment in assessments]
        spread = round(max(confidences) - min(confidences), 3) if confidences else 0.0
        hypotheses_differ = len({a.hypothesis.strip().lower() for a in assessments}) > 1
        insufficient = level in {RiskLevel.HIGH, RiskLevel.CRITICAL} and len({a.provider for a in assessments if a.source == "provider"}) < 2
        triggered = level in {RiskLevel.HIGH, RiskLevel.CRITICAL} and (spread >= self.disagreement_threshold or hypotheses_differ or insufficient)
        disagreement = {
            "triggered": triggered,
            "hypothesis_conflict": hypotheses_differ,
            "insufficient_live_providers": insufficient,
            "threshold": self.disagreement_threshold,
            "confidence_spread": spread,
            "independent_opinions": len(assessments),
            "action": "retrieve_additional_evidence_and_rechallenge" if triggered else "no_extra_review",
        }
        return RoutingDecision(level.value, [assessment.provider for assessment in assessments], bool(provider_errors or (selected and not any(assessment.source == "provider" for assessment in assessments))), disagreement, [assessment.as_dict() for assessment in assessments], provider_errors)
