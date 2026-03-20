"""
Machine learning models module.
Provides:
    1. ``calculate_indicators``       — legacy-compatible RSI / MACD helper used
       by the Momentum tab in the Streamlit dashboard.
    2. ``DirectionPredictor``         — loads a single pre-trained XGBoost model
       (used internally by FourModelPredictor).
    3. ``FourModelPredictor``         — loads exactly four targeted strategy
       models and runs multi-model inference in a single pass.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from common.config import settings

import numpy as np
import pandas as pd
import xgboost as xgb

from models.features import (
    FEATURE_COLUMNS,
    engineer_features,
)

logger = logging.getLogger(__name__)

# Default paths for trained artefacts — stored in model_artifacts/, NOT in
# the models/ Python package (which gets shadowed by Docker volume mounts).
_ARTIFACTS_DIR = Path(settings.model_artifacts_dir)

# ---------------------------------------------------------------------------
# The four targeted models that run in the single container.
# Each key becomes a DB column (prob_<key>) and maps to a JSON artefact.
# ---------------------------------------------------------------------------
MODEL_REGISTRY: Dict[str, str] = {
    "active_1w":         "xgboost_active_1w.json",
    "conservative_1mo":  "xgboost_conservative_1mo.json",
    "conservative_6mo":  "xgboost_conservative_6mo.json",
    "experimental":      "xgboost_experimental.json",
}

# Kept for backward compat with train_local.py imports
STRATEGY_KEYS: List[str] = ["conservative", "active", "experimental"]


def _detect_device() -> str:
    """Return 'cuda' if a usable CUDA GPU is available, else 'cpu'."""
    try:
        _dmat = xgb.DMatrix(np.zeros((2, 2)), label=[0, 1])
        xgb.train({"tree_method": "hist", "device": "cuda"}, _dmat, num_boost_round=1)
        return "cuda"
    except xgb.core.XGBoostError:
        return "cpu"


# ---------------------------------------------------------------------------
# Legacy indicator helper (kept for the Momentum tab)
# ---------------------------------------------------------------------------

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate RSI and MACD via the shared feature-engineering module.

    Returns a DataFrame with columns: RSI, MACD, MACD_signal, MACD_hist.
    Columns are named to match the existing dashboard expectations.
    """
    try:
        if len(df) < 26:
            logger.warning("Insufficient data for indicators. Need >= 26 rows, got %d", len(df))

        features = engineer_features(df)

        indicators = pd.DataFrame(index=df.index)
        indicators["RSI"] = features["rsi_14"]
        indicators["MACD"] = features["macd_line"]
        indicators["MACD_signal"] = features["macd_signal"]
        indicators["MACD_hist"] = features["macd_hist"]

        logger.info("Technical indicators calculated successfully")
        return indicators

    except Exception as e:
        logger.error("Failed to calculate indicators: %s", e)
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# XGBoost directional-probability predictor (single horizon — kept for compat)
# ---------------------------------------------------------------------------

class DirectionPredictor:
    """
    Loads a pre-trained XGBoost model from disk and predicts the probability
    of a positive return over the given horizon.

    Usage
    -----
    >>> predictor = DirectionPredictor()              # loads default model
    >>> proba = predictor.predict_proba(latest_row)   # single-row DataFrame
    """

    def __init__(self, model_path: str | Path | None = None):
        self.model_path = Path(model_path) if model_path else _ARTIFACTS_DIR / "xgboost_direction_1w.json"
        self._model: Optional[xgb.XGBClassifier] = None
        self._threshold: float = 0.5

    @property
    def model(self) -> xgb.XGBClassifier:
        if self._model is None:
            self._load()
        return self._model

    def _load(self) -> None:
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"XGBoost model not found at {self.model_path}. "
                "Run `python scripts/train_local.py` first."
            )
        device = _detect_device()
        self._model = xgb.XGBClassifier()
        self._model.load_model(str(self.model_path))
        self._model.set_params(device=device)

        # Load optimal threshold from sidecar if available
        # Supports both old naming (xgboost_direction_*) and new (xgboost_*)
        name = self.model_path.name
        if name.startswith("xgboost_direction_"):
            thr_name = name.replace("xgboost_direction_", "xgboost_threshold_")
        else:
            thr_name = "xgboost_threshold_" + name.removeprefix("xgboost_")
        threshold_path = self.model_path.with_name(thr_name)
        if threshold_path.exists():
            try:
                meta = json.loads(threshold_path.read_text())
                self._threshold = float(meta.get("threshold", 0.5))
                logger.info("Loaded optimal threshold %.3f from %s", self._threshold, threshold_path)
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning("Could not parse threshold sidecar: %s — using 0.5", exc)
        else:
            logger.info("No threshold sidecar found at %s — using default 0.5", threshold_path)

        logger.info("Loaded XGBoost model from %s (inference device: %s)", self.model_path, device)

    @property
    def threshold(self) -> float:
        _ = self.model
        return self._threshold

    def predict_proba(self, feature_row: pd.DataFrame) -> float:
        row = feature_row[FEATURE_COLUMNS]
        proba = self.model.predict_proba(row)[:, 1]
        return float(proba[0])

    def local_contributions(
        self, feature_row: pd.DataFrame, top_n: int = 3
    ) -> dict[str, float]:
        """
        Compute local (TreeSHAP) feature contributions for a single row.

        Uses XGBoost's native ``pred_contribs=True`` which runs the exact
        TreeSHAP algorithm inside the C++ core — no extra Python dependency.

        Returns a dict of the *top_n* features sorted by absolute impact,
        e.g. ``{"rsi_14": 0.045, "macd_hist": -0.021, "bb_pctb": 0.012}``.
        """
        row = feature_row[FEATURE_COLUMNS]
        booster = self.model.get_booster()
        dmatrix = xgb.DMatrix(row, feature_names=FEATURE_COLUMNS)
        # Shape: (1, n_features + 1) — last element is the bias term
        contribs = booster.predict(dmatrix, pred_contribs=True)
        shap_values = contribs[0, :-1]  # exclude bias

        paired = list(zip(FEATURE_COLUMNS, shap_values.tolist()))
        paired.sort(key=lambda x: abs(x[1]), reverse=True)
        return {name: round(val, 6) for name, val in paired[:top_n]}

    def predict_from_ohlcv(self, df: pd.DataFrame) -> Optional[float]:
        features = engineer_features(df)
        last_valid = features.dropna()
        if last_valid.empty:
            logger.warning("Cannot compute features — not enough history")
            return None
        return self.predict_proba(last_valid.tail(1))


# ---------------------------------------------------------------------------
# Four-model targeted predictor
# ---------------------------------------------------------------------------

class FourModelPredictor:
    """
    Loads exactly four targeted XGBoost models and runs multi-model inference
    on the SAME feature row in a single pass.

    The four models are:
        active_1w         — high-risk short-term momentum
        conservative_1mo  — foundational mid-term
        conservative_6mo  — foundational long-term
        experimental      — next-business-day directional prediction

    Artifact files (in ``model_artifacts/``)::

        xgboost_active_1w.json
        xgboost_conservative_1mo.json
        xgboost_conservative_6mo.json
        xgboost_experimental.json

    Usage
    -----
    >>> predictor = FourModelPredictor()
    >>> result = predictor.predict_from_ohlcv(daily_ohlcv_df)
    >>> result
    {"active_1w": 0.82, "conservative_1mo": 0.51,
     "conservative_6mo": 0.48, "experimental": 0.61}
    """

    def __init__(self, artifacts_dir: str | Path | None = None):
        self._dir = Path(artifacts_dir) if artifacts_dir else _ARTIFACTS_DIR
        self._predictors: Dict[str, DirectionPredictor] = {}
        self._loaded = False

    def _discover(self) -> None:
        """Load available models from the registry."""
        if self._loaded:
            return

        for key, filename in MODEL_REGISTRY.items():
            model_file = self._dir / filename
            if model_file.exists():
                self._predictors[key] = DirectionPredictor(model_path=model_file)
                logger.info("Loaded model '%s' from %s", key, model_file.name)
            else:
                logger.warning("Model '%s' not found at %s — skipping", key, model_file)

        self._loaded = True
        logger.info(
            "FourModelPredictor ready: %d / %d models loaded",
            len(self._predictors), len(MODEL_REGISTRY),
        )

    @property
    def available_models(self) -> List[str]:
        """Return list of model keys that have an artefact on disk."""
        self._discover()
        return list(self._predictors.keys())

    def predict_from_ohlcv(
        self, df: pd.DataFrame
    ) -> tuple[Dict[str, Optional[float]], Dict[str, Optional[dict]]]:
        """
        Run ALL four models over the same feature row.

        Features are engineered ONCE via ``engineer_features(df)``, then
        the resulting row is passed to every loaded model.

        Parameters
        ----------
        df : pd.DataFrame
            Daily OHLCV DataFrame with at least ~30 rows.

        Returns
        -------
        (probabilities, contributions)
            probabilities : ``{"active_1w": 0.82, ...}`` — Missing → None.
            contributions : ``{"active_1w": {"rsi_14": 0.04, ...}, ...}``
                Top-3 TreeSHAP local feature contributions per model.
        """
        self._discover()

        empty_probs: Dict[str, Optional[float]] = {k: None for k in MODEL_REGISTRY}
        empty_contribs: Dict[str, Optional[dict]] = {k: None for k in MODEL_REGISTRY}

        # Feature engineering: ONCE
        features = engineer_features(df)
        last_valid = features.dropna()
        if last_valid.empty:
            logger.warning("Cannot compute features — not enough history")
            return empty_probs, empty_contribs

        row = last_valid.tail(1)

        results: Dict[str, Optional[float]] = {}
        contribs: Dict[str, Optional[dict]] = {}
        for key in MODEL_REGISTRY:
            predictor = self._predictors.get(key)
            if predictor is None:
                results[key] = None
                contribs[key] = None
                continue
            try:
                results[key] = predictor.predict_proba(row)
                contribs[key] = predictor.local_contributions(row)
                logger.debug("  %s  P(up) = %.4f", key, results[key])
            except Exception as exc:
                logger.error("Prediction failed for '%s': %s", key, exc)
                results[key] = None
                contribs[key] = None

        return results, contribs
