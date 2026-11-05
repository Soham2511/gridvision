"""LLM providers exposed through the shared app namespace."""

from app import _RESIDENTIAL_APP_ROOT, _extend_residential_package_path

_extend_residential_package_path(__path__, "providers/llm")
_residential_llm_path = str(_RESIDENTIAL_APP_ROOT / "providers" / "llm")
if _residential_llm_path in __path__:
    __path__.remove(_residential_llm_path)
    __path__.insert(0, _residential_llm_path)

from app.providers.llm.base import BaseLLMProvider, LLMInferenceError
from app.providers.llm.groq_adapter import GroqLLMAdapter
from app.providers.llm.mock_adapter import MockLLMAdapter
from app.providers.llm.ollama_adapter import OllamaLLMAdapter

__all__ = [
    "BaseLLMProvider",
    "GroqLLMAdapter",
    "MockLLMAdapter",
    "OllamaLLMAdapter",
    "LLMInferenceError",
]
