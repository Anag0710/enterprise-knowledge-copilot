"""Minimal A/B testing framework for comparing agent configurations."""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Dict, List, Tuple

from src.agent.config import AgentRuntimeConfig, MultilingualConfig


logger = logging.getLogger(__name__)

Assignment = Tuple[str, str]


@dataclass
class VariantDefinition:
    label: str
    config: Dict[str, object]


@dataclass
class ExperimentDefinition:
    name: str
    description: str
    variant_a: VariantDefinition
    variant_b: VariantDefinition
    traffic_split: float = 0.5
    metrics: List[str] = field(default_factory=lambda: ["confidence", "latency_seconds"])


def _hash_to_fraction(identifier: str) -> float:
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
    as_int = int(digest, 16)
    return as_int / float(2 ** (len(digest) * 4))


def load_experiments(path: Path) -> List[ExperimentDefinition]:
    if not path.exists():
        return []

    payload = json.loads(path.read_text(encoding="utf-8"))
    experiments = []
    for entry in payload:
        experiments.append(
            ExperimentDefinition(
                name=entry["name"],
                description=entry.get("description", ""),
                traffic_split=float(entry.get("traffic_split", 0.5)),
                variant_a=VariantDefinition(**entry["variant_a"]),
                variant_b=VariantDefinition(**entry["variant_b"]),
                metrics=entry.get("metrics", ["confidence", "latency_seconds"])
            )
        )
    return experiments


class ABTestManager:
    def __init__(
        self,
        experiments: List[ExperimentDefinition],
        agent_factory: Callable[[AgentRuntimeConfig], Any]
    ):
        self.experiments = {exp.name: exp for exp in experiments}
        self.agent_factory = agent_factory
        self._agents: Dict[Assignment, Any] = {}
        self._metrics: Dict[Assignment, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

    def assign(self, experiment_name: str, user_identifier: str) -> Assignment:
        experiment = self._get_experiment(experiment_name)
        roll = _hash_to_fraction(user_identifier)
        variant = experiment.variant_a if roll <= experiment.traffic_split else experiment.variant_b
        assignment = (experiment.name, variant.label)
        logger.debug("User %s assigned to %s/%s", user_identifier, experiment.name, variant.label)
        return assignment

    def get_agent(self, assignment: Assignment):
        if assignment not in self._agents:
            experiment_name, variant_label = assignment
            experiment = self._get_experiment(experiment_name)
            variant_def = self._get_variant(experiment, variant_label)
            config = self._build_config(variant_def.config)
            self._agents[assignment] = self.agent_factory(config)
        return self._agents[assignment]

    def record_metrics(self, assignment: Assignment, metrics: Dict[str, float]) -> None:
        store = self._metrics[assignment]
        for key, value in metrics.items():
            if value is None:
                continue
            store[key].append(float(value))

    def summarize(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        summary = {}
        for (experiment, variant), metrics in self._metrics.items():
            summary.setdefault(experiment, {})[variant] = {
                metric: mean(values) for metric, values in metrics.items() if values
            }
        return summary

    def _get_experiment(self, name: str) -> ExperimentDefinition:
        if name not in self.experiments:
            raise ValueError(f"Experiment '{name}' not registered")
        return self.experiments[name]

    @staticmethod
    def _get_variant(experiment: ExperimentDefinition, label: str) -> VariantDefinition:
        for variant in (experiment.variant_a, experiment.variant_b):
            if variant.label == label:
                return variant
        raise ValueError(f"Variant '{label}' not defined for experiment '{experiment.name}'")

    @staticmethod
    def _build_config(payload: Dict[str, object]) -> AgentRuntimeConfig:
        multilingual_payload = payload.get("multilingual", {}) if isinstance(payload, dict) else {}
        multilingual_cfg = MultilingualConfig(
            enabled=multilingual_payload.get("enabled", False),
            default_language=multilingual_payload.get("default_language", "en"),
            translation_provider=multilingual_payload.get("translation_provider", "google")
        )
        return AgentRuntimeConfig(
            enable_advanced_retrieval=payload.get("enable_advanced_retrieval", True),
            enable_specialized_tools=payload.get("enable_specialized_tools", True),
            retrieval_confidence_threshold=float(payload.get("retrieval_confidence_threshold", 0.35)),
            multilingual=multilingual_cfg
        )
