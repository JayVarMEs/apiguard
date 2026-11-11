"""APIGUARD shared core: S0 normaliser (+ S2a feature builder, S3 gate), imported by both the runtime lane and the offline training lane (T3)."""
from .normalizer import (  # noqa: F401
    EndpointRecord,
    NormalisedSpec,
    Normaliser,
    ParseFailure,
    SpecParseError,
    normalise_corpus,
    normalise_file,
    normalise_text,
)
from .features import (  # noqa: E402,F401
    FEATURE_NAMES,
    GROUPS,
    N_FEATURES,
    build_feature_dict,
    build_features,
    build_matrix,
    columns_without_groups,
)
from .gate import (  # noqa: E402,F401
    changed_endpoints,
    endpoint_fingerprint,
    endpoint_key,
    gate_decision,
    ranked_report,
)
