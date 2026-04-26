import json
from typing import Any, Dict


def load_state(trader_data: str, default_iv: float) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "mid_ema": {},
        "spread_ema": {},
        "iv_ema": default_iv,
        "iv_offset_ema": {},
        "obs_count": {},
        "anchor_obs_count": 0,
    }
    if not trader_data:
        return state

    try:
        loaded = json.loads(trader_data)
    except Exception:
        return state

    if not isinstance(loaded, dict):
        return state

    for key in ("mid_ema", "spread_ema", "iv_offset_ema"):
        value = loaded.get(key, {})
        if isinstance(value, dict):
            state[key] = {str(k): float(v) for k, v in value.items()}

    obs_count = loaded.get("obs_count", {})
    if isinstance(obs_count, dict):
        state["obs_count"] = {str(k): int(v) for k, v in obs_count.items() if isinstance(v, (int, float))}

    iv_ema = loaded.get("iv_ema", default_iv)
    if isinstance(iv_ema, (int, float)):
        state["iv_ema"] = float(iv_ema)

    anchor_obs_count = loaded.get("anchor_obs_count", 0)
    if isinstance(anchor_obs_count, (int, float)):
        state["anchor_obs_count"] = int(anchor_obs_count)

    return state


def dump_state(state: Dict[str, Any]) -> str:
    return json.dumps(
        {
            "mid_ema": {k: round(v, 6) for k, v in state.get("mid_ema", {}).items()},
            "spread_ema": {k: round(v, 6) for k, v in state.get("spread_ema", {}).items()},
            "iv_ema": round(float(state.get("iv_ema", 0.0)), 6),
            "iv_offset_ema": {k: round(v, 6) for k, v in state.get("iv_offset_ema", {}).items()},
            "obs_count": {k: int(v) for k, v in state.get("obs_count", {}).items()},
            "anchor_obs_count": int(state.get("anchor_obs_count", 0)),
        },
        separators=(",", ":"),
    )
