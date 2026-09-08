"""Pure baseline Poisson goal-model signal; not publication logic."""

from pitchvalue.models.poisson.config import DEFAULT_POISSON_CONFIG, PoissonConfig
from pitchvalue.models.poisson.contracts import PoissonAnalysis, PoissonModelInput
from pitchvalue.models.poisson.model import analyze_poisson, input_from_match_features

__all__ = [
    "DEFAULT_POISSON_CONFIG",
    "PoissonAnalysis",
    "PoissonConfig",
    "PoissonModelInput",
    "analyze_poisson",
    "input_from_match_features",
]
