import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    """Runtime configuration, read from the environment.

    Auth is always Vertex AI (GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION +
    ADC or service identity) — the client is constructed with vertexai=True.
    """

    model: str = field(
        default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    )
    temperature: float = field(
        default_factory=lambda: float(os.environ.get("GEMINI_TEMPERATURE", "0.2"))
    )
    max_critic_revisions: int = 1


def get_settings() -> Settings:
    return Settings()
