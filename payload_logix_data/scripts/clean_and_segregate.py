"""Clean and segregate SOA-2026 component data for later analysis.

This script intentionally avoids imputation, external data, ML models, and
copula fitting. It preserves the raw CSV, standardizes obvious missing values,
adds conservative engineering parses, writes category CSVs, and creates reports
that document what was done.
"""

from __future__ import annotations

import json
import re
import shutil
from itertools import combinations
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "soa-2026_components_clean.csv"
OUT = ROOT / "payload_logix_data"
RAW = OUT / "raw"
PROCESSED = OUT / "processed"
CATEGORIES = OUT / "categories"
REPORTS = OUT / "reports"
SCHEMAS = OUT / "schemas"

MISSING_MARKERS = {"", "-", "--", "n/a", "na", "nan", "none"}
IMPORTANT_RAW_FIELDS = [
    "mass",
    "power",
    "dimensions",
    "volume",
    "performance_or_capacity",
    "frequency_or_band",
    "voltage_or_energy",
    "accuracy_or_pointing",
]
NUMERIC_FEATURES = [
    "mass_kg",
    "mass_min_kg",
    "mass_max_kg",
    "power_w",
    "power_min_w",
    "power_max_w",
    "volume_cm3",
    "volume_min_cm3",
    "volume_max_cm3",
    "dimension_length_cm",
    "dimension_width_cm",
    "dimension_height_cm",
    "dimension_volume_cm3",
]


def snake_case(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return re.sub(r"_+", "_", name).strip("_")


def standardize_missing(value):
    if pd.isna(value):
        return pd.NA
    text = str(value).strip()
    if text.lower() in MISSING_MARKERS:
        return pd.NA
    return text


def normalize_category(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value).strip())
    obvious = {
        "gps receivers for small spacecraft": "GPS Receivers For Small Spacecraft",
        "radios": "Radios",
        "antennas": "Antennas",
    }
    return obvious.get(text.lower(), text)


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
    return slug[:90] or "uncategorized"


def parse_engineering_value(value, default_unit: str | None = None):
    """Conservatively parse one numeric engineering cell.

    Returns parsed fields plus a status. Ambiguous multi-measurement strings are
    not collapsed to one value because that would hide engineering context.
    """
    result = {"value": pd.NA, "min": pd.NA, "max": pd.NA, "unit": pd.NA, "relation": pd.NA, "status": "missing"}
    if pd.isna(value):
        return result
    text = str(value).strip()
    numeric_text = re.sub(r"(?<=\d)\s*[-–—]\s*(?=\d)", " to ", text)
    low = text.lower()
    numeric_low = numeric_text.lower()
    if low in MISSING_MARKERS:
        return result
    if ";" in text or "@" in text or len(re.findall(r"[-+]?\d*\.?\d+", numeric_text)) > 3:
        result["status"] = "review_multiple_measurements"
        return result

    relation = "="
    if re.search(r"(^|\s)(<|>|≤|≥)", text):
        symbol = re.search(r"(<|>|≤|≥)", text).group(1)
        relation = {"≤": "<=", "≥": ">="}.get(symbol, symbol)

    unit_match = re.search(r"\b(kg|g|mg|w|kw|mw|cm3|cm\^3|cm³|m3|m\^3|m³|l|liter|litre)\b", low)
    unit = unit_match.group(1) if unit_match else default_unit

    nums = [float(x) for x in re.findall(r"[-+]?\d*\.?\d+", numeric_text.replace(",", ""))]
    if not nums:
        result["status"] = "review_no_numeric_value"
        return result
    if unit is None:
        result["status"] = "review_unknown_unit"
        return result
    if len(nums) == 1:
        result.update({"value": nums[0], "unit": unit, "relation": relation, "status": "parsed"})
    elif len(nums) == 2 and re.search(r"\b(to|through)\b", numeric_low):
        result.update({"min": nums[0], "max": nums[1], "unit": unit, "relation": "range", "status": "parsed_range"})
    else:
        result["status"] = "review_multiple_numbers"
    return result


def convert_mass(parsed):
    unit = parsed["unit"]
    factors = {"kg": 1, "g": 0.001, "mg": 0.000001}
    return convert_unit(parsed, factors.get(unit))


def convert_power(parsed):
    unit = parsed["unit"]
    factors = {"w": 1, "kw": 1000, "mw": 0.001}
    return convert_unit(parsed, factors.get(unit))


def convert_volume(parsed):
    unit = parsed["unit"]
    factors = {"cm3": 1, "cm^3": 1, "cm³": 1, "l": 1000, "liter": 1000, "litre": 1000, "m3": 1_000_000, "m^3": 1_000_000, "m³": 1_000_000}
    return convert_unit(parsed, factors.get(unit))


def convert_unit(parsed, factor):
    out = dict(parsed)
    if out["status"] == "missing":
        return out
    if factor is None:
        out["status"] = "review_unsupported_unit"
        return out
    for key in ["value", "min", "max"]:
        if not pd.isna(out[key]):
            out[key] = out[key] * factor
    return out


def parse_dimensions(value):
    result = {"length": pd.NA, "width": pd.NA, "height": pd.NA, "volume": pd.NA, "unit": pd.NA, "status": "missing"}
    if pd.isna(value):
        return result
    text = str(value).strip().lower().replace("×", "x")
    if text in MISSING_MARKERS:
        return result
    unit_match = re.search(r"\b(mm|cm|m)\b", text)
    unit = unit_match.group(1) if unit_match else None
    nums = [float(x) for x in re.findall(r"[-+]?\d*\.?\d+", text.replace(",", ""))]
    has_x = "x" in text
    if not has_x or len(nums) != 3:
        result["status"] = "review_unparsed_dimensions"
        return result
    if unit is None:
        unit = "cm"  # The extracted SOA table headers state dimensions in cm for these product tables.
    factors = {"mm": 0.1, "cm": 1, "m": 100}
    vals = [n * factors[unit] for n in nums]
    result.update({"length": vals[0], "width": vals[1], "height": vals[2], "volume": vals[0] * vals[1] * vals[2], "unit": "cm", "status": "parsed"})
    return result


def write_profile(df_raw: pd.DataFrame, df: pd.DataFrame, path: Path):
    missing = df.isna().sum().to_frame("missing_count")
    missing["missing_percent"] = (missing["missing_count"] / len(df) * 100).round(2)
    cat_counts = df["category"].value_counts()
    categorical_cols = [c for c in df.columns if df[c].dtype == "object" or str(df[c].dtype) == "string"]
    lines = ["# Data Profile", "", f"Rows: {len(df)}", f"Columns: {df.shape[1]}", "", "## Column Names", ", ".join(df.columns), "", "## Data Types", simple_markdown_table(df.dtypes.astype(str).reset_index().rename(columns={"index": "column", 0: "dtype"})), "", "## Missing Values", simple_markdown_table(missing.reset_index().rename(columns={"index": "column"})), "", f"Duplicate rows: {int(df.duplicated().sum())}", "", "## Component Categories", simple_markdown_table(cat_counts.reset_index().rename(columns={"index": "category", "category": "number_of_records"})), "", "## Representative Examples"]
    for col in df.columns:
        examples = df[col].dropna().astype(str).drop_duplicates().head(5).tolist()
        lines.append(f"- {col}: {examples}")
    lines += ["", "## Categorical Unique Values"]
    for col in categorical_cols:
        vals = df[col].dropna().astype(str).drop_duplicates().head(30).tolist()
        lines.append(f"- {col} ({df[col].nunique(dropna=True)} unique): {vals}")
    lines += ["", "## Engineering Text Patterns"]
    for col in IMPORTANT_RAW_FIELDS:
        s = df[col].dropna().astype(str)
        mixed_units = int(s.str.contains(r"\d.*[a-zA-Z°]", regex=True).sum())
        ranges = int(s.str.contains(r"\bto\b|[-–—]\s*\d", case=False, regex=True).sum())
        multiple = int(s.str.contains(r";|@|/", regex=True).sum())
        lines.append(f"- {col}: numeric-with-text/units={mixed_units}, ranges={ranges}, multiple-measurement-patterns={multiple}")
    path.write_text("\n".join(lines), encoding="utf-8")


def simple_markdown_table(frame: pd.DataFrame) -> str:
    """Write a small Markdown table without requiring pandas optional packages."""
    cols = list(frame.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in frame.iterrows():
        values = [str(row[c]).replace("\n", " ") for c in cols]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def main():
    for d in [RAW, PROCESSED, CATEGORIES, REPORTS, SCHEMAS]:
        d.mkdir(parents=True, exist_ok=True)

    df_original = pd.read_csv(SOURCE, dtype="string")
    shutil.copy2(SOURCE, RAW / "soa-2026_components_raw.csv")

    mapping = {col: snake_case(col) for col in df_original.columns}
    df = df_original.rename(columns=mapping).copy()
    for col in df.columns:
        df[col] = df[col].map(standardize_missing).astype("string")
    df["category"] = df["category"].map(lambda x: normalize_category(x) if not pd.isna(x) else x).astype("string")

    for field in IMPORTANT_RAW_FIELDS:
        df[f"{field}_raw"] = df[field]

    mass_parsed = df["mass"].map(lambda x: convert_mass(parse_engineering_value(x, "kg")))
    power_parsed = df["power"].map(lambda x: convert_power(parse_engineering_value(x, "w")))
    volume_parsed = df["volume"].map(lambda x: convert_volume(parse_engineering_value(x, "cm3")))
    dims = df["dimensions"].map(parse_dimensions)

    for prefix, parsed in [("mass", mass_parsed), ("power", power_parsed), ("volume", volume_parsed)]:
        df[f"{prefix}_relation"] = parsed.map(lambda x: x["relation"])
        df[f"{prefix}_parse_status"] = parsed.map(lambda x: x["status"])
        df[f"{prefix}_{'kg' if prefix == 'mass' else 'w' if prefix == 'power' else 'cm3'}"] = parsed.map(lambda x: x["value"])
        df[f"{prefix}_min_{'kg' if prefix == 'mass' else 'w' if prefix == 'power' else 'cm3'}"] = parsed.map(lambda x: x["min"])
        df[f"{prefix}_max_{'kg' if prefix == 'mass' else 'w' if prefix == 'power' else 'cm3'}"] = parsed.map(lambda x: x["max"])

    df["dimension_length_cm"] = dims.map(lambda x: x["length"])
    df["dimension_width_cm"] = dims.map(lambda x: x["width"])
    df["dimension_height_cm"] = dims.map(lambda x: x["height"])
    df["dimension_volume_cm3"] = dims.map(lambda x: x["volume"])
    df["dimensions_parse_status"] = dims.map(lambda x: x["status"])

    df["mass_available"] = df[["mass_kg", "mass_min_kg", "mass_max_kg"]].notna().any(axis=1)
    df["power_available"] = df[["power_w", "power_min_w", "power_max_w"]].notna().any(axis=1)
    df["volume_available"] = df[["volume_cm3", "volume_min_cm3", "volume_max_cm3", "dimension_volume_cm3"]].notna().any(axis=1)
    df["dimensions_available"] = df["dimensions"].notna()
    df["performance_available"] = df["performance_or_capacity"].notna()

    numeric_cols = NUMERIC_FEATURES
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    flags = []
    for idx, row in df.iterrows():
        for col in numeric_cols:
            if pd.notna(row[col]) and row[col] < 0:
                flags.append({"row_index": idx, "category": row["category"], "component_name": row["component_name"], "field": col, "value": row[col], "reason": "negative_engineering_value"})
        for raw_field in ["mass", "power", "volume", "dimensions"]:
            status_col = f"{raw_field}_parse_status"
            if status_col in df.columns and isinstance(row[status_col], str) and row[status_col].startswith("review"):
                flags.append({"row_index": idx, "category": row["category"], "component_name": row["component_name"], "field": raw_field, "value": row[raw_field], "reason": row[status_col]})
    for col in numeric_cols:
        s = df[col].dropna()
        if len(s) >= 10:
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            iqr = q3 - q1
            if iqr > 0:
                mask = (df[col] < q1 - 3 * iqr) | (df[col] > q3 + 3 * iqr)
                for idx, row in df[mask].iterrows():
                    flags.append({"row_index": idx, "category": row["category"], "component_name": row["component_name"], "field": col, "value": row[col], "reason": "statistically_extreme_iqr_3x"})

    df.to_csv(PROCESSED / "components_master_clean.csv", index=False)
    with (SCHEMAS / "column_mapping.json").open("w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)
    categories = sorted(df["category"].dropna().unique())
    category_mapping = {cat: normalize_category(cat) for cat in categories}
    with (SCHEMAS / "category_mapping.json").open("w", encoding="utf-8") as f:
        json.dump(category_mapping, f, indent=2)

    for cat, part in df.groupby("category", dropna=False):
        part.to_csv(CATEGORIES / f"{safe_slug(cat)}.csv", index=False)

    summary = df["category"].value_counts(dropna=False).rename_axis("category").reset_index(name="number_of_records")
    summary["percentage_of_dataset"] = (summary["number_of_records"] / len(df) * 100).round(2)
    summary.to_csv(REPORTS / "category_summary.csv", index=False)

    missing = df.isna().sum().rename_axis("column").reset_index(name="missing_count")
    missing["missing_percent"] = (missing["missing_count"] / len(df) * 100).round(2)
    (REPORTS / "missingness_report.md").write_text("# Missingness Report\n\n" + simple_markdown_table(missing), encoding="utf-8")
    pd.DataFrame(flags).to_csv(REPORTS / "review_flags.csv", index=False)

    write_profile(df_original, df, REPORTS / "data_profile.md")

    lines = ["# Copula Candidate Analysis", "", "No copulas are fitted here. This only checks data availability for later modeling."]
    for cat, part in df.groupby("category"):
        lines += ["", f"## {cat}", f"Records: {len(part)}"]
        candidates = []
        for col in numeric_cols:
            usable = int(part[col].notna().sum())
            if usable:
                unique = int(part[col].nunique(dropna=True))
                miss = round((1 - usable / len(part)) * 100, 2)
                continuous = unique >= min(10, max(3, usable // 3))
                candidates.append(col)
                lines.append(f"- {col}: usable={usable}, missing={miss}%, unique={unique}, appears_continuous={continuous}")
        enough_pairs = []
        for a, b in combinations(candidates, 2):
            joint = int(part[[a, b]].dropna().shape[0])
            if joint >= 10:
                enough_pairs.append(f"{a} + {b} ({joint} joint observations)")
        if enough_pairs:
            lines.append("Potential later copula variable pairs: " + "; ".join(enough_pairs))
        else:
            lines.append("Potential later copula variable pairs: none with at least 10 jointly observed rows")
    (REPORTS / "copula_candidate_analysis.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"Original records: {len(df_original)}")
    print(f"Cleaned records: {len(df)}")
    print(f"Categories: {df['category'].nunique(dropna=True)}")
    print(f"Review flags: {len(flags)}")
    print(f"Outputs written under: {OUT}")


if __name__ == "__main__":
    main()
