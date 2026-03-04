from dataclasses import dataclass, field


@dataclass
class MultilingualConfig:
    """Runtime settings for multilingual question/answer handling."""

    enabled: bool = False
    default_language: str = "en"
    translation_provider: str = "google"


@dataclass
class AgentRuntimeConfig:
    """Feature flags and runtime knobs for agent instances."""

    enable_advanced_retrieval: bool = True
    enable_specialized_tools: bool = True
    retrieval_confidence_threshold: float = 0.35
    multilingual: MultilingualConfig = field(default_factory=MultilingualConfig)
