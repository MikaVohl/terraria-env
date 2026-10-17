"""Reject policies trained against another environment or schema."""
from terraria_lite import SPEC


def validate_checkpoint(raw):
    if not isinstance(raw, dict) or raw.get("environment_version", 1) != SPEC.version:
        version=raw.get("environment_version",1) if isinstance(raw,dict) else "unknown"
        raise ValueError(f"Checkpoint belongs to environment v{version}; running v{SPEC.version}. Use its matching frozen checkout.")
    if raw.get("obs_size") != SPEC.obs_size or raw.get("n_actions") != SPEC.n_actions:
        raise ValueError(
            f"Checkpoint schema mismatch: expected obs_size={SPEC.obs_size}, "
            f"n_actions={SPEC.n_actions}; got obs_size={raw.get('obs_size')}, "
            f"n_actions={raw.get('n_actions')}. Retrain against the current schema.")
