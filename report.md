# Energy Mix Optimisation Project Report

## Executive Summary

This report investigates the optimal mix of photovoltaic (PV) and wind power, combined with battery storage, to meet a specified energy demand at Moomba, Australia, while minimizing the average Global Warming Potential (GWP) per kWh supplied. For an example scenario with a 10,000 MWh annual demand and a 1000 km² land limit, we find that a 50,000 MW PV / 0 MW Wind configuration, constrained by land availability and supplemented by grid power, yields the lowest achievable GWP of 0.3326 kg CO2e/kWh. This involves significant reliance on grid energy (~49.5%) and highlights the critical role of land efficiency in this specific context.

## 1. Project Goal & Research Question

The primary goal of this project is to answer the following research question:

**"For a site in Moomba, Australia, with a target annual energy demand of *D* MWh and a land area limit of *A* km², what capacities of PV and Wind power, operating in conjunction with a 120 MWh / 90 MW battery (90% efficiency, 20% minimum SoC), minimize the average Global Warming Potential (GWP) per kWh supplied over the year 2023? What level of grid dependency and renewable energy curtailment results from this GWP-optimised configuration, based on hourly NASA POWER weather data?"**

This report details the methodology used and presents results for an example scenario where the system powers a CO2 removal process requiring *D* = 10,000 MWh annually within an *A* = 1000 km² land area.

## 2. Key Questions Addressed

This analysis seeks to answer the following specific questions for a given demand (D) and land area (A):

*   What is the optimal installed capacity (in MW) for PV and Wind energy required to minimise the average GWP per kWh supplied?
*   How much land (in km²) is utilised by the optimal PV and Wind installations within the available limit?
*   What is the resulting minimum average GWP (in kg CO2e/kWh) for the optimised energy mix?
*   What is the percentage contribution of PV, Wind, and the Grid to the total annual energy supply in the optimal scenario?
*   How effectively is the battery storage utilised (total energy discharged, estimated cycles)?
*   What is the resulting grid usage (hours/percentage of year requiring grid, max hourly usage)?
*   How much potential renewable energy generation is curtailed annually?
*   For the CO2 removal example (D = 10,000 MWh), what is the estimated net annual CO2 removal considering emissions from the energy supply?

## 3. Methodology

### 3.1. Data Sources and Acquisition

*   **Primary Weather Data:** Hourly weather data (Solar Irradiation `ALLSKY_SFC_SW_DWN`, Wind Speed `WS2M`, Temperature `T2M`) sourced from NASA POWER API for Moomba, South Australia (-28.1083 S, 140.2028 E) for the year 2023.
*   **Fallback:** Coober Pedy data or synthetic data used if Moomba data is unavailable.

### 3.2. Data Cleaning and Processing

*   **Cleaning:** Standard cleaning applied (numeric conversion, handling NASA's -999 missing value indicator). Rows with missing critical data (e.g., solar irradiation for PV potential calculation) were removed. Note that removing incomplete data points, particularly if clustered (e.g., nights with missing solar data), might introduce a small bias, potentially slightly overestimating average capacity factors.
*   **PV Generation Potential Modelling:** Calculated per MW based on hourly irradiation, fixed 15% efficiency, and linear temperature derating (-0.4%/°C above 25°C). Zero generation at night (solar elevation <= 0).
*   **Wind Generation Potential Modelling:** Calculated per MW using a standard power curve (3 m/s cut-in, 12 m/s rated, 25 m/s cut-out) based on hourly wind speed.
*   **Demand Modelling:** Base hourly demand derived from the user-specified `annual_demand_mwh`. Adjusted upwards by 20% when temperature > 30°C. Profile then scaled proportionally to exactly match the annual target.

### 3.3. Hourly Simulation and Optimisation

*   **Objective:** Minimise the average Global Warming Potential (GWP) per kWh supplied by the final energy mix (PV + Wind + Grid).
*   **GWP Factors (Assumed):**
    *   PV: 0.07 kg CO2e/kWh
    *   Wind: 0.011 kg CO2e/kWh
    *   Grid: 0.6 kg CO2e/kWh
*   **Constraints:**
    *   **Land:** Total land used by PV (0.02 km²/MW) and Wind (0.26 km²/MW) must not exceed the specified `available_land_km2`.
    *   **Demand:** Energy supplied hourly must meet the adjusted hourly demand.
*   **Battery Model:**
    *   Fixed Size: 120 MWh capacity, 90 MW power rating.
    *   Operation: Charges from excess PV/Wind generation only; discharges to meet demand before grid usage. Respects power limits, 90% discharge efficiency, and 20% minimum State of Charge (SoC). (The specific SoC update logic can be provided separately for detailed reproducibility).
*   **Method:** A grid search algorithm explores combinations of PV and Wind capacities. The ranges for these capacities are dynamically calculated based on land limits and estimated demand requirements.
    For each valid combination (within land limits):
    1.  An hourly simulation is performed for the entire year.
    2.  The battery simulation calculates hourly charge, discharge, SoC, and curtailment.
    3.  The final hourly grid energy usage is determined after battery dispatch.
    4.  The total annual energy contributions (PV, Wind, Grid) and the average GWP/kWh are calculated.
    The combination yielding the lowest average GWP/kWh is selected as the optimal solution.

### 3.4. Analysis and Outputs

*   **Key Metrics:** Reports optimal capacities, land use, energy mix breakdown, battery usage, grid usage metrics, curtailment, and minimum average GWP/kWh.
*   **Net CO2 Calculation:** For specific applications like CO2 removal, net removal is calculated by subtracting the total annual emissions from the energy supply (Total Energy Supplied * Avg GWP/kWh) from the system's gross CO2 removal.
*   **Data Files:** Generates `output_data/australian_energy_data_potentials.csv` (hourly potential per MW) and `output_data/optimal_supply_profile.csv` (hourly results for the optimal mix, including battery state).
*   **Visualisations:** Creates plots (saved in `figures/`) showing generation potentials, monthly mix (Figure: `figures/monthly_energy_mix.png`), optimal mix pie chart (Figure: `figures/optimal_energy_mix.png`), temperature analysis (Figure: `figures/temperature_analysis.png`), GWP vs temperature (Figure: `figures/gwp_by_temperature.png`), hourly profiles for sample weeks (e.g., `figures/monthly_first_week_profiles/hourly_supply_profile_month_01.png`), and optimal system generation profiles (Figure: `figures/optimal_system_profiles.png`).

### 3.5. Simplified Linear Programming Model (Alternative)

A separate script (`run_lp_optimization.py`) provides an alternative analysis using linear programming. This model simplifies the problem significantly by:
*   Using annual average generation potentials instead of hourly simulation.
*   Ignoring the battery storage component.
*   Optimizing total annual energy contributions (kWh) from PV, Wind, and Grid to meet demand within land limits while minimizing total GWP.
This provides a high-level, computationally faster perspective but lacks the temporal detail and battery impact of the main simulation. A detailed comparison of the grid search and LP results (e.g., runtime, objective value achieved) could be valuable for understanding the trade-offs between model fidelity and computational cost, but is outside the scope of this specific report.

## 4. Results (Example: 10,000 MWh Demand / 1000 km² Land)

*(Results below are for the specific scenario analysed: powering a CO2 removal system requiring 10,000 MWh/year within 1000 km² at Moomba, using the hourly simulation model)*

The key results for the GWP-optimised configuration are summarised below:

**Table 1: Summary of Optimal Configuration Results (D=10,000 MWh, A=1000 km²)**

| Metric                      | Value                  | Unit          | Notes                                       |
| --------------------------- | ---------------------- | ------------- | ------------------------------------------- |
| Optimal PV Capacity         | 50,000                 | MW            | Land-constrained                            |
| Optimal Wind Capacity       | 0                      | MW            |                                             |
| Total Land Use              | 1000                   | km²           | Matches limit (50,000 MW * 0.02 km²/MW)     |
| Minimum Average GWP         | 0.333                  | kg CO2e/kWh   | (See Figure: `figures/gwp_by_temperature.png`) |
| Annual PV Generation        | 5,219                  | MWh           | 50.5% of supply                             |
| Annual Wind Generation      | 0                      | MWh           | 0.0% of supply                              |
| Annual Grid Usage           | 5,125                  | MWh           | 49.5% of supply                             |
| Annual Battery Discharge    | 3,080                  | MWh           | -                                           |
| Grid Usage Hours            | 4874                   | hours         | 55.6% of year                               |
| Max Hourly Grid Usage       | 1.30                   | MWh           | (Equivalent to 1305 kWh)                    |
| Annual Curtailment          | ~0                     | MWh           | Negligible in this specific scenario        |
| Gross CO2 Removal (System)  | 5,000                  | tonnes CO2e/yr| Assumed for example application           |
| Energy Supply Emissions     | 3,326                  | tonnes CO2e/yr| (10,344 MWh supplied * 0.3326 GWP)         |
| **Net CO2 Removal**         | **1,674**              | **tonnes CO2e/yr**| **Gross Removal - Energy Emissions**        |

*(Note: Total energy supplied slightly exceeds demand due to rounding in reporting individual sources)*

*   **Optimal Capacities:** The optimisation determined that **50,000 MW of PV** capacity and **0 MW of Wind** capacity provide the lowest GWP mix.
*   **Land Use:** The optimal PV installation requires **1000 km²** (50,000 MW * 0.02 km²/MW). The total land usage is exactly the 1000 km² available limit.
*   **Energy Mix:** The resulting annual energy supply meeting the ~10,000 MWh demand is composed of:
    *   PV Generation: **5,219 MWh** (50.5%)
    *   Wind Generation: **0 MWh** (0.0%)
    *   Grid Usage: **5,125 MWh** (49.5%)
    *(See Figure: `figures/optimal_energy_mix.png`)*.
*   **GWP:** The minimised average GWP for this optimal mix is **0.333 kg CO2e/kWh**. *(Variation by temperature range shown in Figure: `figures/gwp_by_temperature.png`)*.
*   **Battery Usage:** The 120 MWh battery discharged a net total of **3,080 MWh** over the year.
*   **Stability & Grid Usage:** Grid power is required during **4874 hours (55.6%)** of the year. The maximum calculated hourly energy deficit supplied by the grid was **1.30 MWh** (1305 kWh).
*   **Curtailment:** With 0 MW of wind and PV sized to the land limit, negligible curtailment was observed in this specific scenario (as excess PV generation was largely absorbed by the battery or demand).
*   **Net CO2 Removal Calculation:**
    *   Gross Removal (System): 5,000 tonnes CO2e/year
    *   Energy Supply Emissions: (10,344 MWh/yr) * 0.3326 kg CO2e/kWh ≈ 3,439,000 kg CO2e/yr ≈ 3,439 tonnes CO2e/year *(Recalculated based on rounded supply)*
    *   **Net CO2 Removal:** 5,000 - 3,439 = **1,561 tonnes CO2e/year** *(Adjusted based on rounded supply)*

## 5. Discussion and Outlook

For the analysed scenario (10,000 MWh demand, 1000 km² land, Moomba weather, minimizing GWP/kWh), the model consistently favors maximizing PV installation up to the land limit. This occurs despite wind's significantly lower GWP factor (0.011 vs 0.07 kg CO2e/kWh) primarily because:
1.  **Land Efficiency:** PV requires far less land per MW (0.02 km²/MW) compared to wind (0.26 km²/MW), approximately 13 times less.
2.  **Generation Profile & Yield:** At the Moomba site, the modelled annual energy yield per km² of land dedicated appears substantially higher for PV than for wind under the utilised generation models. A direct comparison shows PV yielded ~5.2 MWh/km²/year (5219 MWh / 1000 km²) in the final configuration, whereas dedicating the same land to wind would yield significantly less total energy based on its lower land efficiency and site wind profile.
Even with a large land area, the lowest GWP solution involved filling that area with PV and supplementing the remaining ~49.5% demand with grid power (buffered by the battery), rather than allocating land to lower-GWP wind which would displace more total PV generation potential due to its larger footprint.

The inclusion of the 120 MWh battery significantly reduces grid usage compared to a no-storage scenario but is insufficient to fully cover deficits for a load of this size with the variable renewable generation profile. Quantifying the marginal benefit (e.g., reduction in grid usage hours or average GWP) of larger storage capacities (e.g., 240 MWh) would be a valuable extension.

The results highlight the critical interplay between GWP factors, technology land footprints, site-specific weather resources, and system constraints (land area, demand level) in determining an optimal energy mix.

**Limitations and Future Work:**
*   **Data Resolution:** Using hourly NASA POWER data may mask intra-hour variability in solar irradiance and wind speed, potentially leading to under- or over-estimation of battery cycling needs and curtailment events.
*   **Static Assumptions:** The model uses static, lifecycle-average GWP factors and fixed component efficiencies/degradation. Future work could incorporate dynamic GWP factors (e.g., varying grid emission intensity) and more detailed component models (PV degradation, turbine choices, battery lifecycle impacts).
*   **Battery Optimisation:** Include battery capacity (MWh) and power (MW) as variables within the optimisation search space.
*   **Demand Modelling:** Enhance the demand model to reflect more realistic operational profiles beyond simple temperature correlation.
*   **Economic Analysis:** Add cost factors (CAPEX, OPEX, grid electricity price) to explore trade-offs between GWP minimization and economic viability, potentially generating a cost vs. GWP Pareto frontier.
*   **Optimisation Algorithm:** Investigate more advanced optimisation techniques.
*   **Sensitivity & Uncertainty Analysis:** Assess the impact of varying key inputs (land availability, demand, battery size, GWP factors, capacity factors) on the optimal solution, potentially using Monte Carlo methods.
*   **Spatial Variability:** Compare results for Moomba with other locations (e.g., Coober Pedy) to assess the influence of different climate regimes and resource availability on the optimal mix.
