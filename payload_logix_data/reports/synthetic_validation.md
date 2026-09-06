# Synthetic Validation

Synthetic rows are marked synthetic=true and are not NASA observations.

## High Heritage Miniature Reaction Wheels
Real usable observations: 53
Synthetic observations: 265

### Marginal Summary
| variable | dataset | mean | median | std | min | q05 | q25 | q75 | q95 | max | ks_distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mass_kg | real | 1.3307 | 0.94 | 1.4428 | 0.012 | 0.093 | 0.24 | 1.9 | 3.86 | 7.5 |  |
| mass_kg | synthetic | 1.3074 | 0.8988 | 1.4158 | 0.0129 | 0.1159 | 0.2381 | 1.8783 | 4.6919 | 7.3068 | 0.0491 |
| power_w | real | 48.2722 | 24.0 | 60.1153 | 0.3 | 0.39 | 2.8 | 65.0 | 201.6 | 204.0 |  |
| power_w | synthetic | 43.5133 | 25.0 | 52.1402 | 0.3 | 0.4438 | 2.8975 | 65.0 | 180.7921 | 204.0 | 0.0604 |

### Correlations
Real:
|  | mass_kg | power_w |
| --- | --- | --- |
| mass_kg | 1.0 | 0.78 |
| power_w | 0.78 | 1.0 |
Synthetic:
|  | mass_kg | power_w |
| --- | --- | --- |
| mass_kg | 1.0 | 0.773 |
| power_w | 0.773 | 1.0 |

### Engineering Plausibility
| variable | sanity_rule | invalid_count | invalid_percent | outside_observed_range_count | outside_observed_range_percent | synthetic_min | synthetic_max | observed_min | observed_max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mass_kg | > 0 | 0 | 0.0 | 0 | 0.0 | 0.0128847990008767 | 7.306813997883594 | 0.012 | 7.5 |
| power_w | >= 0 | 0 | 0.0 | 0 | 0.0 | 0.3 | 204.0 | 0.3 | 204.0 |

### Plots
- payload_logix_data/plots/high_heritage_miniature_reaction_wheels_mass_kg_hist.png
- payload_logix_data/plots/high_heritage_miniature_reaction_wheels_power_w_hist.png
- payload_logix_data/plots/high_heritage_miniature_reaction_wheels_mass_kg_vs_power_w.png

## Power Management And Distribution System Products
Real usable observations: 38
Synthetic observations: 190

### Marginal Summary
| variable | dataset | mean | median | std | min | q05 | q25 | q75 | q95 | max | ks_distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mass_kg | real | 1.5461 | 0.615 | 2.2521 | 0.098 | 0.1034 | 0.2 | 1.5 | 6.065 | 10.0 |  |
| mass_kg | synthetic | 1.5488 | 0.7271 | 2.0037 | 0.0993 | 0.104 | 0.3005 | 1.5903 | 6.1603 | 9.9754 | 0.0947 |
| power_w | real | 771.8526 | 170.0 | 1703.2754 | 2.0 | 28.5 | 80.0 | 297.5 | 4650.0 | 7200.0 |  |
| power_w | synthetic | 834.4288 | 195.8918 | 1653.8701 | 2.9328 | 29.1841 | 79.8859 | 939.8181 | 5631.2336 | 7200.0 | 0.0737 |
| volume_cm3 | real | 1914.5638 | 480.0 | 3314.6565 | 69.0 | 69.0 | 188.75 | 1636.625 | 10322.55 | 13133.0 |  |
| volume_cm3 | synthetic | 2015.5469 | 522.2384 | 3161.4955 | 69.0 | 69.8063 | 253.0029 | 1820.303 | 10462.5852 | 13077.9734 | 0.1211 |

### Correlations
Real:
|  | mass_kg | power_w | volume_cm3 |
| --- | --- | --- | --- |
| mass_kg | 1.0 | 0.766 | 0.945 |
| power_w | 0.766 | 1.0 | 0.699 |
| volume_cm3 | 0.945 | 0.699 | 1.0 |
Synthetic:
|  | mass_kg | power_w | volume_cm3 |
| --- | --- | --- | --- |
| mass_kg | 1.0 | 0.3 | 0.896 |
| power_w | 0.3 | 1.0 | 0.13 |
| volume_cm3 | 0.896 | 0.13 | 1.0 |

### Engineering Plausibility
| variable | sanity_rule | invalid_count | invalid_percent | outside_observed_range_count | outside_observed_range_percent | synthetic_min | synthetic_max | observed_min | observed_max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mass_kg | > 0 | 0 | 0.0 | 0 | 0.0 | 0.0993358122232773 | 9.975383470606587 | 0.098 | 10.0 |
| power_w | >= 0 | 0 | 0.0 | 0 | 0.0 | 2.9328370519198987 | 7200.0 | 2.0 | 7200.0 |
| volume_cm3 | > 0 | 0 | 0.0 | 0 | 0.0 | 69.0 | 13077.97343301655 | 69.0 | 13133.0 |

### Plots
- payload_logix_data/plots/power_management_and_distribution_system_products_mass_kg_hist.png
- payload_logix_data/plots/power_management_and_distribution_system_products_power_w_hist.png
- payload_logix_data/plots/power_management_and_distribution_system_products_mass_kg_vs_power_w.png

## Radios
Real usable observations: 97
Synthetic observations: 485

### Marginal Summary
| variable | dataset | mean | median | std | min | q05 | q25 | q75 | q95 | max | ks_distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mass_kg | real | 643.9794 | 300.0 | 1161.0143 | 7.5 | 28.2 | 132.0 | 615.0 | 2640.0 | 7400.0 |  |
| mass_kg | synthetic | 715.3483 | 319.9559 | 1167.3169 | 10.0373 | 48.0 | 146.5776 | 692.2084 | 3549.1276 | 7039.214 | 0.068 |
| dimension_volume_cm3 | real | 31858.0927 | 230.4 | 128310.4263 | 9.0 | 21.288 | 121.968 | 606.096 | 257657.988 | 672000.0 |  |
| dimension_volume_cm3 | synthetic | 38145.182 | 269.435 | 134745.2182 | 9.2486 | 21.2429 | 130.74 | 723.8664 | 493161.025 | 669306.7484 | 0.0433 |

### Correlations
Real:
|  | mass_kg | dimension_volume_cm3 |
| --- | --- | --- |
| mass_kg | 1.0 | 0.036 |
| dimension_volume_cm3 | 0.036 | 1.0 |
Synthetic:
|  | mass_kg | dimension_volume_cm3 |
| --- | --- | --- |
| mass_kg | 1.0 | 0.523 |
| dimension_volume_cm3 | 0.523 | 1.0 |

### Engineering Plausibility
| variable | sanity_rule | invalid_count | invalid_percent | outside_observed_range_count | outside_observed_range_percent | synthetic_min | synthetic_max | observed_min | observed_max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mass_kg | > 0 | 0 | 0.0 | 0 | 0.0 | 10.03731308944757 | 7039.213959752704 | 7.5 | 7400.0 |
| dimension_volume_cm3 | > 0 | 0 | 0.0 | 0 | 0.0 | 9.24858297904709 | 669306.7484068695 | 9.0 | 672000.0 |

### Plots
- payload_logix_data/plots/radios_mass_kg_hist.png
- payload_logix_data/plots/radios_dimension_volume_cm3_hist.png
- payload_logix_data/plots/radios_mass_kg_vs_dimension_volume_cm3.png

## Limitations
- This is a baseline Gaussian copula, so dependence is represented by linear correlation after normal-score transformation.
- Missing engineering values were not imputed; only complete rows for selected variables were used for fitting.
- Empirical marginals preserve observed ranges closely, but generated combinations still require engineering review.
- Synthetic components are suitable for testing Payload-Logix workflow logic, not for claiming new NASA-certified hardware data.