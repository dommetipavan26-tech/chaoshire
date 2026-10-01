"""One strict boundary for decision labels consumed by adapters and fairness metrics.

Never infer a truth label with Python's truthiness: the string ``false``, NaN,
missing labels, and arbitrary nonzero numbers must not become qualified people.
Providers retain ownership of their frames; normalization always returns a copy.
"""

from math import isfinite
from numbers import Real
from typing import Any

import numpy as np
import pandas as pd

TRUE_LABELS = frozenset({"1", "true", "yes", "y", "accept", "accepted"})
FALSE_LABELS = frozenset({"0", "false", "no", "n", "reject", "rejected"})
DEFAULT_ATTRIBUTES = ("gender", "ethnicity", "age_band")


def boolean_label(value: Any, column: str) -> bool:
    """Accept explicit booleans, 0/1, and documented tokens; reject everything else."""
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, Real) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        label = value.strip().lower()
        if label in TRUE_LABELS:
            return True
        if label in FALSE_LABELS:
            return False
    # Do not echo an external row/value, which might contain private information.
    raise ValueError(f"Column '{column}' requires explicit boolean or 0/1 labels.")


def _group_label(value: Any) -> str:
    if value is None or value is pd.NA or (isinstance(value, Real) and pd.isna(value)):
        return "(missing)"
    if not isinstance(value, (str, Real, np.bool_)):
        raise ValueError("Protected attributes require scalar string/numeric group labels.")
    if isinstance(value, Real) and not isfinite(value):
        raise ValueError("Protected attributes must not contain infinite group labels.")
    label = str(value).strip() or "(missing)"
    try:
        label.encode("utf-8")
    except UnicodeError as error:
        raise ValueError("Protected attributes require valid UTF-8 group labels.") from error
    return label


def normalise_decisions(
    frame: pd.DataFrame,
    attributes: list[str] | None = None,
    *,
    require_groups: bool = False,
) -> pd.DataFrame:
    """Validate labels, finite scores, and requested groups before computing a score.

    Empty frames are permitted for the existing explicit not-assessable verdict.
    Qualification is optional, but every value must be valid when it is present.
    Missing group values are retained as a visible category, never dropped.
    """
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("Decision provider must return a pandas DataFrame.")
    if not frame.columns.is_unique or not all(isinstance(c, str) for c in frame.columns):
        raise ValueError("Decision columns must have unique string names.")
    if "accepted" not in frame.columns:
        raise ValueError("Adapter output is missing required columns: accepted.")
    selected = (
        [name for name in DEFAULT_ATTRIBUTES if name in frame.columns]
        if attributes is None
        else attributes
    )
    if any(not isinstance(c, str) for c in selected) or len(selected) != len(set(selected)):
        raise ValueError("Protected attribute names must be unique strings.")
    if any(name in {"accepted", "qualified", "score"} for name in selected):
        raise ValueError("Decision/truth/score columns cannot be protected attributes.")
    if any(name not in frame.columns for name in selected):
        raise ValueError("Decision output is missing a requested protected attribute.")
    if require_groups and not selected:
        raise ValueError("Decision output requires at least one protected attribute.")
    normalised = frame.copy()
    for column in ("accepted", "qualified"):
        if column in normalised:
            normalised[column] = (
                normalised[column]
                .map(lambda value, column=column: boolean_label(value, column))
                .astype(bool)
            )
    if "score" in normalised:
        scores = normalised["score"]
        if any(
            isinstance(value, (bool, np.bool_))
            or not isinstance(value, Real)
            or not isfinite(value)
            for value in scores
        ):
            raise ValueError("Score values must be finite numeric values.")
    for attribute in selected:
        normalised[attribute] = normalised[attribute].map(_group_label)
    return normalised
