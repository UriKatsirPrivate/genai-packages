import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    """Runtime configuration, read from the environment.

    GEMINI_API_KEY is consumed implicitly by google-genai's Client();
    GOOGLE_GENAI_USE_VERTEXAI=true switches the SDK to Vertex AI.
    """

    model: str = field(
        default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    )
    temperature: float = field(
        default_factory=lambda: float(os.environ.get("GEMINI_TEMPERATURE", "0.2"))
    )
    max_critic_revisions: int = 1


def get_settings() -> Settings:
    return Settings()
