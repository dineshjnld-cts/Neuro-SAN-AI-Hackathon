"""Cerebras-backed ChatOpenAI adapter for the native Neuro SAN network."""

from __future__ import annotations

import os
from typing import Any

from langchain_openai import ChatOpenAI


DEFAULT_CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1"


class CerebrasChatOpenAI(ChatOpenAI):
    """Use Cerebras' OpenAI-compatible API without copying credentials into HOCON."""

    def __init__(self, **kwargs: Any) -> None:
        """Apply Cerebras environment defaults before creating the LangChain client."""
        if kwargs.get("api_key") is None and kwargs.get("openai_api_key") is None:
            api_key = os.getenv("CEREBRAS_API_KEY")
            if not api_key:
                raise ValueError("CEREBRAS_API_KEY is required for the Cerebras adapter")
            kwargs["api_key"] = api_key
        if kwargs.get("base_url") is None and kwargs.get("openai_api_base") is None:
            base_url = os.getenv("FRAUD_CEREBRAS_BASE_URL", DEFAULT_CEREBRAS_BASE_URL).strip()
            kwargs["base_url"] = base_url.removesuffix("/chat/completions")
        kwargs.setdefault("reasoning_effort", "none")
        super().__init__(**kwargs)
