from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TuningParameter:
    key: str
    group: str
    label: str
    description: str
    default: float
    minimum: float
    maximum: float
    step: float
    decimals: int
    kind: str = "spin"


# Every value below is used by the live tracking pipeline. The controls are
# deliberately bounded: developer mode is for calibration, not for allowing a
# setting that can destabilize the pointer or gesture state machine.
DEVELOPER_PARAMETERS = (
    TuningParameter("pointer_min_cutoff", "Pointer", "Rest smoothing", "One Euro base cutoff (Hz). Lower is steadier; higher is more immediate.", 0.90, 0.10, 3.00, 0.05, 2),
    TuningParameter("inference_clahe_clip", "Camera tracking", "Low-light enhancement", "Local contrast enhancement applied only to the inference image. Zero disables it.", 1.60, 0.00, 4.00, 0.10, 2),
    TuningParameter("pointer_beta", "Pointer", "Motion response", "One Euro speed response. Higher reduces lag while moving.", 1.15, 0.10, 3.00, 0.05, 2),
    TuningParameter("pointer_dead_zone", "Pointer", "Tremor dead zone", "Normalized movement ignored near rest. Higher removes more micro-jitter.", 0.0031, 0.0005, 0.0200, 0.0005, 4),
    TuningParameter("prediction_frames", "Pointer", "Prediction lookahead", "Constant-velocity cursor lookahead in frames. Zero disables prediction.", 1.00, 0.00, 1.00, 0.10, 2),
    TuningParameter("prediction_cap", "Pointer", "Prediction cap", "Maximum normalized cursor extrapolation per frame.", 0.018, 0.002, 0.040, 0.001, 3),
    TuningParameter("pointer_confidence_floor", "Pointer", "Confidence floor", "Hand confidence below this level receives extra smoothing to resist landmark noise.", 0.45, 0.10, 0.90, 0.05, 2),
    TuningParameter("pointer_jump_threshold", "Pointer", "Jump rejection", "Maximum normalized one-frame innovation before a low-quality landmark jump is ignored.", 0.095, 0.030, 0.250, 0.005, 3),
    TuningParameter("workspace_base_gain", "Pointer", "Workspace base gain", "Pointer mapping gain before the sensitivity slider is applied.", 0.84, 0.40, 1.40, 0.02, 2),
    TuningParameter("workspace_sensitivity_gain", "Pointer", "Sensitivity gain", "Extra workspace gain added by the main sensitivity slider.", 0.48, 0.10, 1.00, 0.02, 2),
    TuningParameter("workspace_margin", "Pointer", "Workspace margin", "Camera edge margin mapped to screen edges. Lower needs less arm travel.", 0.14, 0.02, 0.30, 0.01, 2),
    TuningParameter("precision_enabled", "Pointer", "Near-pinch slowdown", "Enable the slow, controlled final pointer approach when index and thumb come close.", 1.00, 0.00, 1.00, 1.00, 0, "toggle"),
    TuningParameter("precision_ratio", "Pointer", "Precision-zone distance", "Pinch ratio that enters slow final-approach pointer control.", 0.62, 0.35, 1.20, 0.01, 2),
    TuningParameter("precision_step", "Pointer", "Precision speed cap", "Maximum normalized pointer movement per frame near a pinch. Higher is faster; the minimum keeps the cursor from freezing.", 0.012, 0.006, 0.030, 0.001, 3),
    TuningParameter("precision_speed_floor", "Pointer", "Precision minimum speed", "Slowest fraction of precision speed at the pinch edge. Higher prevents the pointer from stalling.", 0.65, 0.35, 1.00, 0.05, 2),
    TuningParameter("pinch_deep_contact", "Pinch", "Immediate contact", "Very close thumb-to-finger ratio accepted without confirmation.", 0.30, 0.12, 0.45, 0.01, 2),
    TuningParameter("pinch_contact", "Pinch", "Contact radius", "Normal pinch detection threshold. Higher recognizes a wider pinch.", 0.34, 0.18, 0.60, 0.01, 2),
    TuningParameter("pinch_3d_blend", "Pinch", "3D pinch blend", "Weight given to world-depth distance. Higher rejects edge-on false pinches; lower favors reliable front-facing contact.", 0.15, 0.00, 0.80, 0.05, 2),
    TuningParameter("pinch_confirm", "Pinch", "Confirmed contact", "Filtered ratio that confirms a shallow pinch.", 0.32, 0.12, 0.55, 0.01, 2),
    TuningParameter("pinch_hold_release", "Pinch", "Hold-release threshold", "Filtered ratio below which a held pinch remains active.", 0.50, 0.25, 0.90, 0.01, 2),
    TuningParameter("pinch_clear_release", "Pinch", "Clear-release threshold", "Raw ratio that immediately ends a pinch.", 0.75, 0.35, 1.40, 0.01, 2),
    TuningParameter("pinch_alpha_contact", "Pinch", "Contact smoothing", "Low-pass blend for closing a pinch. Higher responds faster.", 0.78, 0.30, 1.00, 0.02, 2),
    TuningParameter("pinch_alpha_release", "Pinch", "Release smoothing", "Low-pass blend for opening a pinch. Higher responds faster.", 0.72, 0.30, 1.00, 0.02, 2),
    TuningParameter("pinch_release_grace", "Pinch", "Release grace", "Seconds of ambiguous release tolerated before ending a pinch.", 0.075, 0.00, 0.25, 0.005, 3),
    TuningParameter("click_settle_delay", "Timing", "Click settle delay", "Seconds pointer movement stays paused after a pinch release.", 0.050, 0.00, 0.25, 0.005, 3),
    TuningParameter("gesture_settle_delay", "Timing", "Gesture settle delay", "Seconds pointer movement waits after a mode gesture.", 0.10, 0.00, 0.40, 0.01, 2),
    TuningParameter("pause_hold_seconds", "Timing", "Pause hold", "Seconds fists must be held to pause or resume.", 0.70, 0.20, 2.00, 0.05, 2),
    TuningParameter("double_click_window", "Timing", "Double-click window", "Maximum seconds between index pinches to enter drag/double-click mode.", 0.50, 0.20, 1.20, 0.05, 2),
    TuningParameter("right_click_cooldown", "Timing", "Right-click cooldown", "Minimum seconds before another middle-thumb right click.", 0.32, 0.10, 1.00, 0.02, 2),
    TuningParameter("drag_start_distance", "Timing", "Drag start distance", "Normalized fingertip travel required to turn a hold into a drag.", 0.018, 0.005, 0.080, 0.001, 3),
    TuningParameter("scroll_step", "Modes", "Fist-scroll step", "Normalized vertical distance per scroll step; lower scrolls faster.", 0.026, 0.008, 0.080, 0.001, 3),
    TuningParameter("volume_step", "Modes", "Volume step", "Normalized vertical distance per volume step; lower changes volume faster.", 0.027, 0.008, 0.080, 0.001, 3),
    TuningParameter("two_finger_dead_zone", "Modes", "Two-finger dead zone", "Normalized movement ignored before two-finger scrolling begins.", 0.024, 0.005, 0.080, 0.001, 3),
    TuningParameter("zoom_smoothing", "Modes", "Zoom smoothing", "Blend for the two-hand zoom distance. Higher is more responsive.", 0.55, 0.20, 0.90, 0.05, 2),
    TuningParameter("zoom_step_factor", "Modes", "Zoom step factor", "Fraction of starting hand spacing required per zoom step.", 0.055, 0.020, 0.120, 0.005, 3),
    TuningParameter("zoom_emit_interval", "Modes", "Zoom interval", "Minimum seconds between zoom steps.", 0.09, 0.03, 0.30, 0.01, 2),
    TuningParameter("swipe_enabled", "Swipes", "Enable three-finger swipes", "Enable either hand's three-finger swipes for app switching, Task View, and Show Desktop. Off by default to preserve normal pointer tracking.", 0.00, 0.00, 1.00, 1.00, 0, "toggle"),
    TuningParameter("swipe_min_hold_frames", "Swipes", "Arm hold frames", "Consecutive qualifying three-finger frames required before tracking arms.", 3.00, 2.00, 12.00, 1.00, 0),
    TuningParameter("swipe_window_seconds", "Swipes", "Motion window", "Rolling raw three-fingertip sample window used for displacement and velocity.", 0.20, 0.10, 0.40, 0.01, 2),
    TuningParameter("swipe_arm_distance", "Swipes", "Arm distance", "Raw three-fingertip distance that enters directional swipe tracking.", 0.040, 0.020, 0.150, 0.005, 3),
    TuningParameter("swipe_fire_distance", "Swipes", "Fire distance", "Raw three-fingertip distance required to fire a gesture.", 0.100, 0.050, 0.300, 0.005, 3),
    TuningParameter("swipe_min_velocity", "Swipes", "Minimum velocity", "Normalized three-fingertip velocity required to fire a swipe.", 0.40, 0.15, 2.00, 0.05, 2),
    TuningParameter("swipe_vertical_tolerance", "Swipes", "Vertical tolerance", "Maximum vertical movement allowed during a left/right three-finger swipe.", 0.075, 0.020, 0.180, 0.005, 3),
    TuningParameter("swipe_horizontal_tolerance", "Swipes", "Horizontal tolerance", "Maximum horizontal movement allowed during an up/down three-finger swipe.", 0.075, 0.020, 0.180, 0.005, 3),
    TuningParameter("swipe_extension_angle", "Swipes", "Finger extension", "Minimum main-joint angle for each raised swipe finger. Lower accepts naturally curved fingers.", 118.0, 95.0, 150.0, 1.0, 0),
    TuningParameter("swipe_thumb_fold_limit", "Swipes", "Thumb fold limit", "Maximum thumb-to-wrist distance, in palm widths, while arming the three-finger pose.", 1.45, 0.80, 2.20, 0.05, 2),
    TuningParameter("swipe_cooldown_seconds", "Swipes", "Cooldown", "Seconds after a fired swipe before another action can occur.", 0.50, 0.20, 1.20, 0.05, 2),
    TuningParameter("swipe_min_spread", "Swipes", "Three-finger spread", "Minimum index-to-ring-finger spread, relative to palm width, to arm swiping.", 0.85, 0.60, 2.00, 0.05, 2),
    TuningParameter("swipe_debug", "Swipes", "Show swipe debug", "Show state, raw displacement, velocity, and arm frame count in the status pill.", 0.00, 0.00, 1.00, 1.00, 0, "toggle"),
)

PARAMETERS_BY_KEY = {parameter.key: parameter for parameter in DEVELOPER_PARAMETERS}
DEFAULT_TUNING = {parameter.key: parameter.default for parameter in DEVELOPER_PARAMETERS}


def normalized_tuning(values: dict[str, float] | None = None) -> dict[str, float]:
    result = dict(DEFAULT_TUNING)
    for key, value in (values or {}).items():
        parameter = PARAMETERS_BY_KEY.get(key)
        if parameter is not None:
            result[key] = max(parameter.minimum, min(parameter.maximum, float(value)))
    return result
