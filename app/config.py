# app/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Mistral API
    mistral_api_key: str = ""
    mistral_model: str = "mistral-small-2503"
    llm_temperature: float = 0.4

    # Tavily
    tavily_api_key: str = ""
    tavily_max_results: int = 10

    # Cohere (optional reranking)
    cohere_api_key: str = ""

    # Search panel
    search_max_chars: int = 8000

    def validate_required(self) -> None:
        missing = []
        if not self.mistral_api_key: missing.append("MISTRAL_API_KEY")
        if not self.tavily_api_key:  missing.append("TAVILY_API_KEY")
        if missing:
            raise ValueError(f"Missing required env vars: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    return Settings()