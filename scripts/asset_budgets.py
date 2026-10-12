"""Absolute download limits shared by scoped publishing and runtime validation."""
MODEL_BYTE_LIMITS = {'detail': 26_000_000, 'smooth': 18_000_000}


def validate_model_bytes(profile, size):
    assert size < MODEL_BYTE_LIMITS[profile], f'{profile} model exceeds absolute loading budget'
