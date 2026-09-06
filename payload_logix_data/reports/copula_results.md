# Copula Results

Baseline model: category-specific Gaussian copula with empirical marginals.

Why this model: it is mathematically simple, reproducible, and separates each engineering variable's marginal distribution from cross-variable dependence.

## Radios
Copula: Gaussian copula
Variables: mass_kg, dimension_volume_cm3
Records in category: 117
Usable complete observations: 97
Discarded only for copula fitting because of joint missingness: 20
Marginals: empirical distributions from observed cleaned NASA-derived values; no engineering values were imputed.
Correlation matrix:
|  | mass_kg | dimension_volume_cm3 |
| --- | --- | --- |
| mass_kg | 1.0 | 0.792 |
| dimension_volume_cm3 | 0.792 | 1.0 |

## High Heritage Miniature Reaction Wheels
Copula: Gaussian copula
Variables: mass_kg, power_w
Records in category: 66
Usable complete observations: 53
Discarded only for copula fitting because of joint missingness: 13
Marginals: empirical distributions from observed cleaned NASA-derived values; no engineering values were imputed.
Correlation matrix:
|  | mass_kg | power_w |
| --- | --- | --- |
| mass_kg | 1.0 | 0.763 |
| power_w | 0.763 | 1.0 |

## Power Management And Distribution System Products
Copula: Gaussian copula
Variables: mass_kg, power_w, volume_cm3
Records in category: 49
Usable complete observations: 38
Discarded only for copula fitting because of joint missingness: 11
Marginals: empirical distributions from observed cleaned NASA-derived values; no engineering values were imputed.
Correlation matrix:
|  | mass_kg | power_w | volume_cm3 |
| --- | --- | --- | --- |
| mass_kg | 1.0 | 0.483 | 0.941 |
| power_w | 0.483 | 1.0 | 0.384 |
| volume_cm3 | 0.941 | 0.384 | 1.0 |
