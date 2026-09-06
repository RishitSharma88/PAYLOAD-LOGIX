"""Generate synthetic component rows from fitted Gaussian copulas."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd


SEED = 42
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "payload_logix_data"
MODELS = DATA / "copula" / "models"
SYNTHETIC = DATA / "data" / "synthetic"
normal = NormalDist()


def safe_slug(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_")


def normal_cdf_array(values: np.ndarray) -> np.ndarray:
    return np.vectorize(normal.cdf)(values)


def empirical_inverse(u_values: np.ndarray, observed_values: list[float]) -> np.ndarray:
    # Inverse empirical CDF via quantiles. This preserves the observed marginal
    # scale instead of assuming a parametric engineering distribution.
    observed = np.array(observed_values, dtype=float)
    return np.quantile(observed, u_values, method="linear")


def generate_for_model(model_path: Path, rng: np.random.Generator) -> pd.DataFrame:
    with model_path.open(encoding="utf-8") as f:
        model = json.load(f)
    category = model["category"]
    variables = model["variables"]
    n_real = int(model["usable_observations"])
    n_synth = n_real * 5

    corr = np.array(model["correlation_matrix"], dtype=float)
    z = rng.multivariate_normal(mean=np.zeros(len(variables)), cov=corr, size=n_synth)
    uniforms = np.clip(normal_cdf_array(z), 1e-6, 1 - 1e-6)

    rows = {
        "synthetic_component_id": [f"SYN-{safe_slug(category).upper()}-{i + 1:04d}" for i in range(n_synth)],
        "category": category,
        "synthetic": True,
    }
    for j, col in enumerate(variables):
        rows[col] = empirical_inverse(uniforms[:, j], model["marginals"][col])
    return pd.DataFrame(rows)


def main():
    SYNTHETIC.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    count = 0
    for model_path in sorted(MODELS.glob("*_gaussian_copula.json")):
        synthetic = generate_for_model(model_path, rng)
        category = synthetic["category"].iloc[0]
        out = SYNTHETIC / f"{safe_slug(category)}_synthetic.csv"
        synthetic.to_csv(out, index=False)
        print(f"Wrote {len(synthetic)} synthetic rows: {out}")
        count += 1
    print(f"Generated synthetic data for {count} categories")


if __name__ == "__main__":
    main()
