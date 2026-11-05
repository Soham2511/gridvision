"""Assistant services exposed through the shared app namespace."""

from app import _RESIDENTIAL_APP_ROOT, _extend_residential_package_path

_extend_residential_package_path(__path__, "services/assistant")
_residential_assistant_path = str(_RESIDENTIAL_APP_ROOT / "services" / "assistant")
if _residential_assistant_path in __path__:
    __path__.remove(_residential_assistant_path)
    __path__.insert(0, _residential_assistant_path)

from app.services.assistant.context_builder import HouseholdContextBuilder
from app.services.assistant.orchestrator import ResidentialAssistantOrchestrator
from app.services.assistant.prompts import build_system_prompt

__all__ = [
    "HouseholdContextBuilder",
    "ResidentialAssistantOrchestrator",
    "build_system_prompt",
]
