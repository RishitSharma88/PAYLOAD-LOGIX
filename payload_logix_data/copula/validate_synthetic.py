"""Validate real vs synthetic component distributions and correlations."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "payload_logix_data"
MODELS = DATA / "copula" / "models"
MODELING_DATA = DATA / "copula" / "modeling_data"
SYNTHETIC = DATA / "data" / "synthetic"
REPORT = DATA / "reports" / "synthetic_validation.md"
PLOTS = DATA / "plots"


def markdown_table(frame: pd.DataFrame, include_index: bool = False) -> str:
    cols = list(frame.columns)
    header = ([""] if include_index else []) + cols
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    for idx, row in frame.iterrows():
        vals = ([str(idx)] if include_index else []) + [str(row[c]) for c in cols]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def safe_slug(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_")


def summary_stats(series: pd.Series) -> dict:
    q = series.quantile([0.05, 0.25, 0.5, 0.75, 0.95])
    return {
        "mean": series.mean(),
        "median": series.median(),
        "std": series.std(),
        "min": series.min(),
        "q05": q.loc[0.05],
        "q25": q.loc[0.25],
        "q75": q.loc[0.75],
        "q95": q.loc[0.95],
        "max": series.max(),
    }


def ks_distance(real: pd.Series, synthetic: pd.Series) -> float:
    # Simple Kolmogorov-Smirnov distance implemented directly: maximum gap
    # between empirical CDFs. Lower is closer.
    values = np.sort(np.unique(np.concatenate([real.to_numpy(), synthetic.to_numpy()])))
    real_cdf = np.searchsorted(np.sort(real), values, side="right") / len(real)
    synth_cdf = np.searchsorted(np.sort(synthetic), values, side="right") / len(synthetic)
    return float(np.max(np.abs(real_cdf - synth_cdf)))


def plausibility_checks(real: pd.DataFrame, synthetic: pd.DataFrame, variables: list[str]) -> pd.DataFrame:
    rows = []
    for col in variables:
        s = synthetic[col]
        r = real[col]
        if "mass" in col or "volume" in col or "dimension" in col:
            invalid = s <= 0
            rule = "> 0"
        elif "power" in col:
            invalid = s < 0
            rule = ">= 0"
        else:
            invalid = pd.Series(False, index=s.index)
            rule = "no simple sign rule"
        outside = (s < r.min()) | (s > r.max())
        rows.append({
            "variable": col,
            "sanity_rule": rule,
            "invalid_count": int(invalid.sum()),
            "invalid_percent": round(float(invalid.mean() * 100), 2),
            "outside_observed_range_count": int(outside.sum()),
            "outside_observed_range_percent": round(float(outside.mean() * 100), 2),
            "synthetic_min": float(s.min()),
            "synthetic_max": float(s.max()),
            "observed_min": float(r.min()),
            "observed_max": float(r.max()),
        })
    return pd.DataFrame(rows)


def write_basic_plots(category: str, real: pd.DataFrame, synthetic: pd.DataFrame, variables: list[str]):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    PLOTS.mkdir(parents=True, exist_ok=True)
    slug = safe_slug(category)
    paths = []
    for col in variables[:2]:
        plt.figure(figsize=(6, 4))
        plt.hist(real[col], bins=15, alpha=0.6, density=True, label="real")
        plt.hist(synthetic[col], bins=15, alpha=0.6, density=True, label="synthetic")
        plt.title(f"{category}: {col}")
        plt.legend()
        plt.tight_layout()
        path = PLOTS / f"{slug}_{col}_hist.png"
        plt.savefig(path)
        plt.close()
        paths.append(path)
    if len(variables) >= 2:
        x, y = variables[0], variables[1]
        plt.figure(figsize=(5, 5))
        plt.scatter(real[x], real[y], s=18, alpha=0.8, label="real")
        plt.scatter(synthetic[x], synthetic[y], s=8, alpha=0.35, label="synthetic")
        plt.xlabel(x)
        plt.ylabel(y)
        plt.title(category)
        plt.legend()
        plt.tight_layout()
        path = PLOTS / f"{slug}_{x}_vs_{y}.png"
        plt.savefig(path)
        plt.close()
        paths.append(path)
    return paths


def main():
    lines = ["# Synthetic Validation", "", "Synthetic rows are marked synthetic=true and are not NASA observations.", ""]
    any_plots = False
    for model_path in sorted(MODELS.glob("*_gaussian_copula.json")):
        with model_path.open(encoding="utf-8") as f:
            model = json.load(f)
        category = model["category"]
        slug = safe_slug(category)
        variables = model["variables"]
        real = pd.read_csv(MODELING_DATA / f"{slug}_modeling_data.csv")
        synthetic = pd.read_csv(SYNTHETIC / f"{slug}_synthetic.csv")

        lines += [f"## {category}", f"Real usable observations: {len(real)}", f"Synthetic observations: {len(synthetic)}", ""]
        rows = []
        for col in variables:
            real_stats = summary_stats(real[col])
            synth_stats = summary_stats(synthetic[col])
            rows.append({"variable": col, "dataset": "real", **real_stats, "ks_distance": ""})
            rows.append({"variable": col, "dataset": "synthetic", **synth_stats, "ks_distance": round(ks_distance(real[col], synthetic[col]), 4)})
        lines.append("### Marginal Summary")
        lines.append(markdown_table(pd.DataFrame(rows).round(4)))
        lines.append("")

        lines.append("### Correlations")
        lines.append("Real:")
        lines.append(markdown_table(real[variables].corr().round(3), include_index=True))
        lines.append("Synthetic:")
        lines.append(markdown_table(synthetic[variables].corr().round(3), include_index=True))
        lines.append("")

        checks = plausibility_checks(real, synthetic, variables)
        lines.append("### Engineering Plausibility")
        lines.append(markdown_table(checks))
        lines.append("")

        plot_paths = write_basic_plots(category, real, synthetic, variables)
        if plot_paths:
            any_plots = True
            lines.append("### Plots")
            for path in plot_paths:
                lines.append(f"- {path.relative_to(ROOT)}")
            lines.append("")

    if not any_plots:
        lines.append("Plot generation skipped because matplotlib is not installed in the active environment.")
    lines += [
        "## Limitations",
        "- This is a baseline Gaussian copula, so dependence is represented by linear correlation after normal-score transformation.",
        "- Missing engineering values were not imputed; only complete rows for selected variables were used for fitting.",
        "- Empirical marginals preserve observed ranges closely, but generated combinations still require engineering review.",
        "- Synthetic components are suitable for testing Payload-Logix workflow logic, not for claiming new NASA-certified hardware data.",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Validation report written: {REPORT}")


if __name__ == "__main__":
    main()
