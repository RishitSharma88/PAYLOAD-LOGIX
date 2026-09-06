# Copula Candidate Analysis

No copulas are fitted here. This only checks data availability for later modeling.

## Active Thermal Systems Cryocoolers
Records: 7
- mass_kg: usable=6, missing=14.29%, unique=5, appears_continuous=True
- power_w: usable=7, missing=0.0%, unique=7, appears_continuous=True
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Active Thermal Systems Electrical Heaters
Records: 10
- power_w: usable=2, missing=80.0%, unique=1, appears_continuous=False
- power_min_w: usable=7, missing=30.0%, unique=3, appears_continuous=True
- power_max_w: usable=7, missing=30.0%, unique=5, appears_continuous=True
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Active Thermal Systems Fluid Loops
Records: 2
- mass_kg: usable=1, missing=50.0%, unique=1, appears_continuous=False
- volume_cm3: usable=2, missing=0.0%, unique=1, appears_continuous=False
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Alternative Monopropellant And Bipropellant Propulsion
Records: 18
- mass_kg: usable=7, missing=61.11%, unique=7, appears_continuous=True
- power_w: usable=5, missing=72.22%, unique=5, appears_continuous=True
- power_min_w: usable=2, missing=88.89%, unique=2, appears_continuous=False
- power_max_w: usable=2, missing=88.89%, unique=2, appears_continuous=False
- dimension_length_cm: usable=1, missing=94.44%, unique=1, appears_continuous=False
- dimension_width_cm: usable=1, missing=94.44%, unique=1, appears_continuous=False
- dimension_height_cm: usable=1, missing=94.44%, unique=1, appears_continuous=False
- dimension_volume_cm3: usable=1, missing=94.44%, unique=1, appears_continuous=False
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Ambipolar Electric Propulsion
Records: 7
- mass_kg: usable=4, missing=42.86%, unique=4, appears_continuous=True
- power_w: usable=6, missing=14.29%, unique=5, appears_continuous=True
- dimension_length_cm: usable=4, missing=42.86%, unique=4, appears_continuous=True
- dimension_width_cm: usable=4, missing=42.86%, unique=3, appears_continuous=True
- dimension_height_cm: usable=4, missing=42.86%, unique=4, appears_continuous=True
- dimension_volume_cm3: usable=4, missing=42.86%, unique=4, appears_continuous=True
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Antennas
Records: 92
- mass_kg: usable=87, missing=5.43%, unique=67, appears_continuous=True
- mass_min_kg: usable=3, missing=96.74%, unique=3, appears_continuous=True
- mass_max_kg: usable=3, missing=96.74%, unique=3, appears_continuous=True
- dimension_length_cm: usable=74, missing=19.57%, unique=42, appears_continuous=True
- dimension_width_cm: usable=74, missing=19.57%, unique=39, appears_continuous=True
- dimension_height_cm: usable=74, missing=19.57%, unique=47, appears_continuous=True
- dimension_volume_cm3: usable=74, missing=19.57%, unique=61, appears_continuous=True
Potential later copula variable pairs: mass_kg + dimension_length_cm (72 joint observations); mass_kg + dimension_width_cm (72 joint observations); mass_kg + dimension_height_cm (72 joint observations); mass_kg + dimension_volume_cm3 (72 joint observations); dimension_length_cm + dimension_width_cm (74 joint observations); dimension_length_cm + dimension_height_cm (74 joint observations); dimension_length_cm + dimension_volume_cm3 (74 joint observations); dimension_width_cm + dimension_height_cm (74 joint observations); dimension_width_cm + dimension_volume_cm3 (74 joint observations); dimension_height_cm + dimension_volume_cm3 (74 joint observations)

## Atomic Clocks And Oscillators For Small Spacecraft
Records: 8
- mass_kg: usable=6, missing=25.0%, unique=6, appears_continuous=True
- power_w: usable=5, missing=37.5%, unique=5, appears_continuous=True
- dimension_length_cm: usable=7, missing=12.5%, unique=7, appears_continuous=True
- dimension_width_cm: usable=7, missing=12.5%, unique=7, appears_continuous=True
- dimension_height_cm: usable=7, missing=12.5%, unique=7, appears_continuous=True
- dimension_volume_cm3: usable=7, missing=12.5%, unique=7, appears_continuous=True
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Battery Pack Product Table
Records: 24
- volume_cm3: usable=23, missing=4.17%, unique=22, appears_continuous=True
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Battery Vs Supercapacitor Specifications
Records: 15
- power_w: usable=1, missing=93.33%, unique=1, appears_continuous=False
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Cold Gas Propulsion
Records: 21
- mass_kg: usable=17, missing=19.05%, unique=16, appears_continuous=True
- mass_min_kg: usable=1, missing=95.24%, unique=1, appears_continuous=False
- mass_max_kg: usable=1, missing=95.24%, unique=1, appears_continuous=False
- power_w: usable=14, missing=33.33%, unique=11, appears_continuous=True
- dimension_length_cm: usable=4, missing=80.95%, unique=4, appears_continuous=True
- dimension_width_cm: usable=4, missing=80.95%, unique=2, appears_continuous=False
- dimension_height_cm: usable=4, missing=80.95%, unique=2, appears_continuous=False
- dimension_volume_cm3: usable=4, missing=80.95%, unique=4, appears_continuous=True
Potential later copula variable pairs: mass_kg + power_w (13 joint observations)

## Commercial Actuator Mechanisms
Records: 30
- mass_kg: usable=29, missing=3.33%, unique=28, appears_continuous=True
- mass_min_kg: usable=1, missing=96.67%, unique=1, appears_continuous=False
- mass_max_kg: usable=1, missing=96.67%, unique=1, appears_continuous=False
- power_w: usable=11, missing=63.33%, unique=11, appears_continuous=True
- power_min_w: usable=3, missing=90.0%, unique=3, appears_continuous=True
- power_max_w: usable=3, missing=90.0%, unique=3, appears_continuous=True
Potential later copula variable pairs: mass_kg + power_w (11 joint observations)

## Commercial Sun Sensors
Records: 36
- mass_kg: usable=30, missing=16.67%, unique=22, appears_continuous=True
- power_w: usable=34, missing=5.56%, unique=18, appears_continuous=True
Potential later copula variable pairs: mass_kg + power_w (29 joint observations)

## Commercially Available Horizon Sensors
Records: 4
- mass_kg: usable=4, missing=0.0%, unique=4, appears_continuous=True
- power_w: usable=3, missing=25.0%, unique=3, appears_continuous=True
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Cont Hall Effect Electric Propulsion Thrusters
Records: 14
- mass_kg: usable=7, missing=50.0%, unique=6, appears_continuous=True
- dimension_length_cm: usable=4, missing=71.43%, unique=4, appears_continuous=True
- dimension_width_cm: usable=4, missing=71.43%, unique=4, appears_continuous=True
- dimension_height_cm: usable=4, missing=71.43%, unique=4, appears_continuous=True
- dimension_volume_cm3: usable=4, missing=71.43%, unique=4, appears_continuous=True
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Cont Other Monopropellant And Bipropellant Propulsion
Records: 21
- mass_kg: usable=15, missing=28.57%, unique=14, appears_continuous=True
- power_w: usable=6, missing=71.43%, unique=6, appears_continuous=True
- power_min_w: usable=7, missing=66.67%, unique=6, appears_continuous=True
- power_max_w: usable=7, missing=66.67%, unique=5, appears_continuous=True
- dimension_length_cm: usable=3, missing=85.71%, unique=3, appears_continuous=True
- dimension_width_cm: usable=3, missing=85.71%, unique=3, appears_continuous=True
- dimension_height_cm: usable=3, missing=85.71%, unique=3, appears_continuous=True
- dimension_volume_cm3: usable=3, missing=85.71%, unique=3, appears_continuous=True
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Cubesat Standard Structure Dimensions
Records: 6
- mass_kg: usable=4, missing=33.33%, unique=4, appears_continuous=True
- mass_min_kg: usable=2, missing=66.67%, unique=2, appears_continuous=False
- mass_max_kg: usable=2, missing=66.67%, unique=2, appears_continuous=False
- dimension_length_cm: usable=6, missing=0.0%, unique=2, appears_continuous=False
- dimension_width_cm: usable=6, missing=0.0%, unique=2, appears_continuous=False
- dimension_height_cm: usable=6, missing=0.0%, unique=5, appears_continuous=True
- dimension_volume_cm3: usable=6, missing=0.0%, unique=6, appears_continuous=True
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Currently Available Integrated Systems
Records: 9
- mass_kg: usable=8, missing=11.11%, unique=8, appears_continuous=True
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Deep Space Transponders For Small Spacecraft
Records: 3
- mass_kg: usable=3, missing=0.0%, unique=3, appears_continuous=True
- power_w: usable=3, missing=0.0%, unique=3, appears_continuous=True
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Electrospray Electric Propulsion
Records: 10
- mass_kg: usable=9, missing=10.0%, unique=8, appears_continuous=True
- power_w: usable=9, missing=10.0%, unique=9, appears_continuous=True
- dimension_length_cm: usable=6, missing=40.0%, unique=5, appears_continuous=True
- dimension_width_cm: usable=6, missing=40.0%, unique=6, appears_continuous=True
- dimension_height_cm: usable=6, missing=40.0%, unique=6, appears_continuous=True
- dimension_volume_cm3: usable=6, missing=40.0%, unique=6, appears_continuous=True
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Electrothermal Electric Propulsion
Records: 24
- mass_kg: usable=22, missing=8.33%, unique=20, appears_continuous=True
- power_w: usable=22, missing=8.33%, unique=17, appears_continuous=True
- power_min_w: usable=1, missing=95.83%, unique=1, appears_continuous=False
- power_max_w: usable=1, missing=95.83%, unique=1, appears_continuous=False
- dimension_length_cm: usable=3, missing=87.5%, unique=2, appears_continuous=False
- dimension_width_cm: usable=3, missing=87.5%, unique=2, appears_continuous=False
- dimension_height_cm: usable=3, missing=87.5%, unique=1, appears_continuous=False
- dimension_volume_cm3: usable=3, missing=87.5%, unique=3, appears_continuous=True
Potential later copula variable pairs: mass_kg + power_w (21 joint observations)

## GPS Receivers For Small Spacecraft
Records: 16
- mass_kg: usable=16, missing=0.0%, unique=16, appears_continuous=True
- power_w: usable=15, missing=6.25%, unique=14, appears_continuous=True
Potential later copula variable pairs: mass_kg + power_w (15 joint observations)

## Gridded Ion Electric Propulsion
Records: 8
- mass_kg: usable=6, missing=25.0%, unique=6, appears_continuous=True
- power_w: usable=7, missing=12.5%, unique=7, appears_continuous=True
- dimension_length_cm: usable=5, missing=37.5%, unique=5, appears_continuous=True
- dimension_width_cm: usable=5, missing=37.5%, unique=5, appears_continuous=True
- dimension_height_cm: usable=5, missing=37.5%, unique=5, appears_continuous=True
- dimension_volume_cm3: usable=5, missing=37.5%, unique=5, appears_continuous=True
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Gyros Available For Small Spacecraft
Records: 24
- mass_kg: usable=24, missing=0.0%, unique=18, appears_continuous=True
- power_w: usable=23, missing=4.17%, unique=12, appears_continuous=True
Potential later copula variable pairs: mass_kg + power_w (23 joint observations)

## Hall Effect Electric Propulsion Thrusters
Records: 23
- mass_kg: usable=17, missing=26.09%, unique=9, appears_continuous=True
Potential later copula variable pairs: none with at least 10 jointly observed rows

## High Heritage Magnetic Torquers
Records: 38
- mass_kg: usable=31, missing=18.42%, unique=26, appears_continuous=True
- mass_min_kg: usable=6, missing=84.21%, unique=6, appears_continuous=True
- mass_max_kg: usable=6, missing=84.21%, unique=5, appears_continuous=True
- power_w: usable=28, missing=26.32%, unique=22, appears_continuous=True
- power_min_w: usable=6, missing=84.21%, unique=6, appears_continuous=True
- power_max_w: usable=6, missing=84.21%, unique=6, appears_continuous=True
Potential later copula variable pairs: mass_kg + power_w (28 joint observations)

## High Heritage Miniature Reaction Wheels
Records: 66
- mass_kg: usable=66, missing=0.0%, unique=59, appears_continuous=True
- power_w: usable=53, missing=19.7%, unique=38, appears_continuous=True
Potential later copula variable pairs: mass_kg + power_w (53 joint observations)

## Hybrid Chemical Propulsion
Records: 8
- mass_kg: usable=1, missing=87.5%, unique=1, appears_continuous=False
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Hydrazine Chemical Propulsion
Records: 24
- mass_kg: usable=15, missing=37.5%, unique=12, appears_continuous=True
- mass_min_kg: usable=1, missing=95.83%, unique=1, appears_continuous=False
- mass_max_kg: usable=1, missing=95.83%, unique=1, appears_continuous=False
- power_w: usable=13, missing=45.83%, unique=6, appears_continuous=True
Potential later copula variable pairs: mass_kg + power_w (12 joint observations)

## Lct Technologies
Records: 14
- mass_kg: usable=14, missing=0.0%, unique=12, appears_continuous=True
- power_w: usable=14, missing=0.0%, unique=12, appears_continuous=True
Potential later copula variable pairs: mass_kg + power_w (14 joint observations)

## Lidar For Small Spacecraft
Records: 2
- mass_kg: usable=2, missing=0.0%, unique=2, appears_continuous=False
- power_w: usable=2, missing=0.0%, unique=2, appears_continuous=False
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Power Management And Distribution System Products
Records: 49
- mass_kg: usable=40, missing=18.37%, unique=32, appears_continuous=True
- mass_min_kg: usable=2, missing=95.92%, unique=2, appears_continuous=False
- mass_max_kg: usable=2, missing=95.92%, unique=2, appears_continuous=False
- power_w: usable=44, missing=10.2%, unique=32, appears_continuous=True
- power_min_w: usable=1, missing=97.96%, unique=1, appears_continuous=False
- power_max_w: usable=1, missing=97.96%, unique=1, appears_continuous=False
- volume_cm3: usable=40, missing=18.37%, unique=36, appears_continuous=True
- volume_min_cm3: usable=2, missing=95.92%, unique=2, appears_continuous=False
- volume_max_cm3: usable=2, missing=95.92%, unique=2, appears_continuous=False
Potential later copula variable pairs: mass_kg + power_w (38 joint observations); mass_kg + volume_cm3 (40 joint observations); power_w + volume_cm3 (38 joint observations)

## Propellant Less Propulsion
Records: 3
- mass_kg: usable=2, missing=33.33%, unique=2, appears_continuous=False
- power_w: usable=1, missing=66.67%, unique=1, appears_continuous=False
- dimension_length_cm: usable=1, missing=66.67%, unique=1, appears_continuous=False
- dimension_width_cm: usable=1, missing=66.67%, unique=1, appears_continuous=False
- dimension_height_cm: usable=1, missing=66.67%, unique=1, appears_continuous=False
- dimension_volume_cm3: usable=1, missing=66.67%, unique=1, appears_continuous=False
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Pulsed Plasma And Vacuum Arc Electric Propulsion
Records: 11
- mass_kg: usable=10, missing=9.09%, unique=9, appears_continuous=True
- power_w: usable=10, missing=9.09%, unique=9, appears_continuous=True
Potential later copula variable pairs: mass_kg + power_w (10 joint observations)

## Radios
Records: 117
- mass_kg: usable=111, missing=5.13%, unique=78, appears_continuous=True
- mass_min_kg: usable=3, missing=97.44%, unique=1, appears_continuous=False
- mass_max_kg: usable=3, missing=97.44%, unique=1, appears_continuous=False
- power_w: usable=82, missing=29.91%, unique=34, appears_continuous=True
- power_min_w: usable=24, missing=79.49%, unique=8, appears_continuous=True
- power_max_w: usable=24, missing=79.49%, unique=9, appears_continuous=True
- dimension_length_cm: usable=98, missing=16.24%, unique=36, appears_continuous=True
- dimension_width_cm: usable=98, missing=16.24%, unique=38, appears_continuous=True
- dimension_height_cm: usable=98, missing=16.24%, unique=56, appears_continuous=True
- dimension_volume_cm3: usable=98, missing=16.24%, unique=82, appears_continuous=True
Potential later copula variable pairs: mass_kg + power_w (81 joint observations); mass_kg + power_min_w (21 joint observations); mass_kg + power_max_w (21 joint observations); mass_kg + dimension_length_cm (97 joint observations); mass_kg + dimension_width_cm (97 joint observations); mass_kg + dimension_height_cm (97 joint observations); mass_kg + dimension_volume_cm3 (97 joint observations); power_w + dimension_length_cm (68 joint observations); power_w + dimension_width_cm (68 joint observations); power_w + dimension_height_cm (68 joint observations); power_w + dimension_volume_cm3 (68 joint observations); power_min_w + power_max_w (24 joint observations); power_min_w + dimension_length_cm (21 joint observations); power_min_w + dimension_width_cm (21 joint observations); power_min_w + dimension_height_cm (21 joint observations); power_min_w + dimension_volume_cm3 (21 joint observations); power_max_w + dimension_length_cm (21 joint observations); power_max_w + dimension_width_cm (21 joint observations); power_max_w + dimension_height_cm (21 joint observations); power_max_w + dimension_volume_cm3 (21 joint observations); dimension_length_cm + dimension_width_cm (98 joint observations); dimension_length_cm + dimension_height_cm (98 joint observations); dimension_length_cm + dimension_volume_cm3 (98 joint observations); dimension_width_cm + dimension_height_cm (98 joint observations); dimension_width_cm + dimension_volume_cm3 (98 joint observations); dimension_height_cm + dimension_volume_cm3 (98 joint observations)

## Robotic Arms For Small Spacecraft
Records: 3
- mass_kg: usable=1, missing=66.67%, unique=1, appears_continuous=False
- power_w: usable=1, missing=66.67%, unique=1, appears_continuous=False
- power_min_w: usable=1, missing=66.67%, unique=1, appears_continuous=False
- power_max_w: usable=1, missing=66.67%, unique=1, appears_continuous=False
- dimension_length_cm: usable=1, missing=66.67%, unique=1, appears_continuous=False
- dimension_width_cm: usable=1, missing=66.67%, unique=1, appears_continuous=False
- dimension_height_cm: usable=1, missing=66.67%, unique=1, appears_continuous=False
- dimension_volume_cm3: usable=1, missing=66.67%, unique=1, appears_continuous=False
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Smallsat Thermal Control Challenges
Records: 5
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Solar Array Panel Products
Records: 115
- power_w: usable=109, missing=5.22%, unique=57, appears_continuous=True
- power_min_w: usable=1, missing=99.13%, unique=1, appears_continuous=False
- power_max_w: usable=1, missing=99.13%, unique=1, appears_continuous=False
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Solar Cells
Records: 18
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Solid Motor Chemical Propulsion
Records: 5
- mass_kg: usable=3, missing=40.0%, unique=3, appears_continuous=True
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Star Trackers Suitable For Small Spacecraft
Records: 31
- mass_kg: usable=27, missing=12.9%, unique=25, appears_continuous=True
- mass_min_kg: usable=1, missing=96.77%, unique=1, appears_continuous=False
- mass_max_kg: usable=1, missing=96.77%, unique=1, appears_continuous=False
- power_w: usable=24, missing=22.58%, unique=20, appears_continuous=True
- power_min_w: usable=1, missing=96.77%, unique=1, appears_continuous=False
- power_max_w: usable=1, missing=96.77%, unique=1, appears_continuous=False
Potential later copula variable pairs: mass_kg + power_w (20 joint observations)

## Thermal Switches
Records: 4
- mass_kg: usable=1, missing=75.0%, unique=1, appears_continuous=False
- mass_min_kg: usable=1, missing=75.0%, unique=1, appears_continuous=False
- mass_max_kg: usable=1, missing=75.0%, unique=1, appears_continuous=False
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Thermoelectric Coolers
Records: 5
Potential later copula variable pairs: none with at least 10 jointly observed rows

## Three Axis Magnetometers For Small Spacecraft
Records: 11
- mass_kg: usable=11, missing=0.0%, unique=10, appears_continuous=True
- power_w: usable=8, missing=27.27%, unique=5, appears_continuous=True
Potential later copula variable pairs: none with at least 10 jointly observed rows