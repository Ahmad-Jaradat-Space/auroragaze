from typing import cast

from langchain_core.language_models import BaseChatModel

from auroragaze.config import settings


def make_llm(temperature: float = 0.0) -> BaseChatModel:
    provider = settings.llm_provider.lower()
    if provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek

        return cast(
            BaseChatModel,
            ChatDeepSeek(
                model="deepseek-chat",  # type: ignore[call-arg]
                temperature=temperature,
                api_key=settings.deepseek_api_key,
            ),
        )
    if provider == "minimax":
        from langchain_openai import ChatOpenAI

        return cast(
            BaseChatModel,
            ChatOpenAI(
                model="MiniMax-M2",
                temperature=temperature,
                base_url="https://api.minimax.chat/v1",
                api_key=settings.minimax_api_key,
            ),
        )
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return cast(
            BaseChatModel,
            ChatOllama(
                model="qwen2.5:32b",
                temperature=temperature,
                base_url=settings.ollama_base_url,
            ),
        )
    raise ValueError(f"unknown llm provider: {provider}")
