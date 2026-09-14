"""模型工厂、路由与能力探测。"""

from .factory import ModelBundle, ModelFactory, build_chat_model
from .probe import CANDIDATE_MODELS, ProbeSample, ProbeTestResult, probe_model
from .router import ROLE_SPECS, RoleSpec, invoke_with_fallback

__all__ = [
    "CANDIDATE_MODELS",
    "ROLE_SPECS",
    "ModelBundle",
    "ModelFactory",
    "ProbeSample",
    "ProbeTestResult",
    "RoleSpec",
    "build_chat_model",
    "invoke_with_fallback",
    "probe_model",
]