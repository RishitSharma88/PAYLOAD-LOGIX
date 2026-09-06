"""Fit simple category-specific Gaussian copulas.

A copula separates two ideas:
1. Marginals: the one-variable distribution of mass, power, volume, etc.
2. Dependence: how variables move together after each marginal is transformed
   to a common uniform scale.

This baseline uses empirical marginals and a Gaussian copula because it is easy
to explain: transform ranks to U(0,1), transform U values to normal scores,
then estimate a correlation matrix.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd


SEED = 42
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "payload_logix_data"
MASTER = DATA / "processed" / "components_master_clean.csv"
COPULA = DATA / "copula"
MODELS = COPULA / "models"
MODELING_DATA = COPULA / "modeling_data"
REPORT = DATA / "reports" / "copula_results.md"

INITIAL_CATEGORIES = [
    "Radios",
    "High Heritage Miniature Reaction Wheels",
    "Power Management And Distribution System Products",
]
PREFERRED_VARIABLES = ["mass_kg", "power_w", "volume_cm3", "dimension_volume_cm3"]
MIN_JOINT_OBSERVATIONS = 10
MIN_UNIQUE_VALUES = 5
normal = NormalDist()


def markdown_table(frame: pd.DataFrame) -> str:
    cols = list(frame.columns)
    lines = ["| " + " | ".join([""] + cols) + " |", "| " + " | ".join(["---"] * (len(cols) + 1)) + " |"]
    for idx, row in frame.iterrows():
        vals = [str(idx)] + [str(row[c]) for c in cols]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def safe_slug(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_")


def choose_variables(part: pd.DataFrame) -> list[str]:
    usable = []
    for col in PREFERRED_VARIABLES:
        if col in part.columns:
            observed = part[col].dropna()
            if "power" in col and (observed < 0).any():
                continue
            if ("mass" in col or "volume" in col or "dimension" in col) and (observed <= 0).any():
                continue
            if len(observed) >= MIN_JOINT_OBSERVATIONS and observed.nunique() >= MIN_UNIQUE_VALUES:
                usable.append(col)
    # Keep the model interpretable. Three variables is enough for this stage.
    for k in range(min(3, len(usable)), 1, -1):
        subset = usable[:k]
        if len(part[subset].dropna()) >= MIN_JOINT_OBSERVATIONS:
            return subset
    return []


def empirical_uniforms(frame: pd.DataFrame) -> pd.DataFrame:
    # Rank transformation estimates each marginal CDF without assuming normal,
    # lognormal, etc. Dividing by n+1 avoids exact 0 and 1 values.
    n = len(frame)
    return frame.rank(method="average") / (n + 1)


def normal_scores(uniforms: pd.DataFrame) -> pd.DataFrame:
    return uniforms.map(lambda u: normal.inv_cdf(float(u)))


def nearest_valid_correlation(corr: np.ndarray) -> np.ndarray:
    corr = np.nan_to_num(corr, nan=0.0)
    corr = (corr + corr.T) / 2
    eigvals, eigvecs = np.linalg.eigh(corr)
    eigvals[eigvals < 1e-6] = 1e-6
    fixed = eigvecs @ np.diag(eigvals) @ eigvecs.T
    scale = np.sqrt(np.diag(fixed))
    return fixed / np.outer(scale, scale)


def fit_category(df: pd.DataFrame, category: str) -> dict | None:
    part = df[df["category"] == category].copy()
    variables = choose_variables(part)
    if len(variables) < 2:
        return None

    model_data = part[variables].dropna().copy()
    n_total = len(part)
    n_used = len(model_data)
    if n_used < MIN_JOINT_OBSERVATIONS:
        return None

    uniforms = empirical_uniforms(model_data)
    z = normal_scores(uniforms)
    corr = nearest_valid_correlation(z.corr().to_numpy())

    slug = safe_slug(category)
    model_data.to_csv(MODELING_DATA / f"{slug}_modeling_data.csv", index=False)
    model = {
        "category": category,
        "copula": "Gaussian copula",
        "seed": SEED,
        "variables": variables,
        "records_in_category": int(n_total),
        "usable_observations": int(n_used),
        "discarded_for_joint_missingness": int(n_total - n_used),
        "marginals": {col: sorted(model_data[col].astype(float).tolist()) for col in variables},
        "correlation_matrix": corr.tolist(),
    }
    with (MODELS / f"{slug}_gaussian_copula.json").open("w", encoding="utf-8") as f:
        json.dump(model, f, indent=2)
    return model


def main():
    MODELS.mkdir(parents=True, exist_ok=True)
    MODELING_DATA.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(MASTER)
    models = []
    for category in INITIAL_CATEGORIES:
        model = fit_category(df, category)
        if model is not None:
            models.append(model)

    lines = [
        "# Copula Results",
        "",
        "Baseline model: category-specific Gaussian copula with empirical marginals.",
        "",
        "Why this model: it is mathematically simple, reproducible, and separates each engineering variable's marginal distribution from cross-variable dependence.",
        "",
    ]
    for model in models:
        lines += [
            f"## {model['category']}",
            f"Copula: {model['copula']}",
            f"Variables: {', '.join(model['variables'])}",
            f"Records in category: {model['records_in_category']}",
            f"Usable complete observations: {model['usable_observations']}",
            f"Discarded only for copula fitting because of joint missingness: {model['discarded_for_joint_missingness']}",
            "Marginals: empirical distributions from observed cleaned NASA-derived values; no engineering values were imputed.",
            "Correlation matrix:",
            markdown_table(pd.DataFrame(model["correlation_matrix"], index=model["variables"], columns=model["variables"]).round(3)),
            "",
        ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Fitted {len(models)} Gaussian copula models")
    for model in models:
        print(model["category"], model["variables"], model["usable_observations"])


if __name__ == "__main__":
    main()
