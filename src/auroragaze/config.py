from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", frozen=True, extra="ignore")

    llm_provider: str = "deepseek"
    deepseek_api_key: str = ""
    minimax_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    chroma_dir: Path = Path("data/chroma")
    corpus_dir: Path = Path("data/corpus")


settings = Settings()
