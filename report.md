# Energy Mix Optimisation Project Report

## 1. Project Goal & Research Question

The primary goal of this project is to answer the following research question:

**"For a site in Moomba, Australia, with a target annual energy demand of *D* MWh and a land area limit of *A* km², what capacities of PV and Wind power, operating in conjunction with a 120 MWh / 90 MW battery (90% efficiency, 20% minimum SoC), minimize the average Global Warming Potential (GWP) per kWh supplied over the year 2023? What level of grid dependency and renewable energy curtailment results from this GWP-optimized configuration, based on hourly NASA POWER weather data?"**

This report details the methodology used and presents results for an example scenario where the system powers a CO2 removal process requiring 10,000 MWh annually within a 1000 km² land area.

## 2. Key Questions Addressed

This analysis seeks to answer the following specific questions for a given demand (D) and land area (A):

*   What is the optimal installed capacity (in MW) for PV and Wind energy required to minimise the average GWP per kWh supplied?
*   How much land (in km²) is utilised by the optimal PV and Wind installations within the available limit?
*   What is the resulting minimum average GWP (in kg CO2e/kWh) for the optimised energy mix?
*   What is the percentage contribution of PV, Wind, and the Grid to the total annual energy supply in the optimal scenario?
*   How effectively is the battery storage utilised (total energy discharged, estimated cycles)?
*   What is the resulting grid dependency (hours/percentage of year requiring grid, max hourly requirement)?
*   How much potential renewable energy generation is curtailed annually?
*   For the CO2 removal example (D=10,000 MWh), what is the estimated net annual CO2 removal considering emissions from the energy supply?

## 3. Methodology

### 3.1. Data Sources and Acquisition

*   **Primary Weather Data:** Hourly weather data (Solar Irradiation `ALLSKY_SFC_SW_DWN`, Wind Speed `WS2M`, Temperature `T2M`) sourced from NASA POWER API for Moomba, South Australia (-28.1083 S, 140.2028 E) for the year 2023.
*   **Fallback:** Coober Pedy data or synthetic data used if Moomba data is unavailable.

### 3.2. Data Cleaning and Processing

*   **Cleaning:** Standard cleaning applied (numeric conversion, handling NASA's -999 missing value indicator, removing rows with missing data).
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
    *   Operation: Charges from excess PV/Wind generation only; discharges to meet demand before grid usage. Respects power limits, 90% discharge efficiency, and 20% minimum State of Charge (SoC).
*   **Method:** A grid search algorithm explores combinations of PV and Wind capacities. The ranges for these capacities are dynamically calculated based on land limits and estimated demand requirements.
    For each valid combination (within land limits):
    1.  An hourly simulation is performed for the entire year.
    2.  The battery simulation calculates hourly charge, discharge, SoC, and curtailment.
    3.  The final hourly grid energy requirement is determined after battery dispatch.
    4.  The total annual energy contributions (PV, Wind, Grid) and the average GWP/kWh are calculated.
    The combination yielding the lowest average GWP/kWh is selected as the optimal solution.

### 3.4. Analysis and Outputs

*   **Key Metrics:** Reports optimal capacities, land use, energy mix breakdown, battery usage, grid reliance metrics, curtailment, and minimum average GWP/kWh.
*   **Net CO2 Calculation:** For specific applications like CO2 removal, net removal is calculated by subtracting the total annual emissions from the energy supply (Total kWh * Avg GWP/kWh) from the system's gross CO2 removal.
*   **Data Files:** Generates `output_data/australian_energy_data_potentials.csv` (hourly potential per MW) and `output_data/optimal_supply_profile.csv` (hourly results for the optimal mix, including battery state).
*   **Visualisations:** Creates plots (saved in `figures/`) showing generation potentials, monthly mix, optimal mix pie chart, temperature analysis, GWP vs temperature, hourly profiles for sample weeks, and optimal system generation profiles.

### 3.5. Simplified Linear Programming Model (Optional)

A separate script (`run_lp_optimization.py`) provides an alternative analysis using linear programming. This model simplifies the problem significantly by:
*   Using annual average generation potentials instead of hourly simulation.
*   Ignoring the battery storage component.
*   Optimizing total annual energy contributions (kWh) from PV, Wind, and Grid to meet demand within land limits while minimizing total GWP.
This provides a high-level, computationally faster perspective but lacks the temporal detail and battery impact of the main simulation.

## 4. Results (Example: 10,000 MWh Demand / 1000 km² Land)

*(Results below are for the specific scenario analysed: powering a CO2 removal system requiring 10,000 MWh/year within 1000 km² at Moomba, using the hourly simulation model)*

*   **Optimal Capacities:** The optimisation determined that **50,000 MW of PV** capacity and **0 MW of Wind** capacity provide the lowest GWP mix.
*   **Land Use:** The optimal PV installation requires 1000.00 km² (50,000 MW * 0.02 km²/MW). The total land usage is exactly the 1000 km² available limit.
*   **Energy Mix:** The resulting annual energy supply meeting the 10,000 MWh demand is composed of:
    *   PV Generation: 5,218.58 MWh (50.5%)
    *   Wind Generation: 0.00 MWh (0.0%)
    *   Grid Usage: 5,125.24 MWh (49.5%)
    *(See Figure: `figures/optimal_energy_mix.png`)*.
*   **GWP:** The minimised average GWP for this optimal mix is **0.3326 kg CO2e/kWh**. *(Variation by temperature range shown in Figure: `figures/gwp_by_temperature.png`)*.
*   **Battery Usage:** The 120 MWh battery discharged a net total of **3,079.89 MWh** over the year.
*   **Stability & Grid Reliance:** Grid power is required during **4874 hours (55.6%)** of the year. The maximum calculated hourly energy deficit supplied by the grid was 1304.69 kWh.
*   **Curtailment:** With 0 MW of wind and PV sized to the land limit, no significant curtailment was observed in this specific scenario (as excess PV generation was largely absorbed by the battery or demand).
*   **Net CO2 Removal Calculation:**
    *   Gross Removal (System): 5,000 tonnes CO2e/year
    *   Energy Supply Emissions: (10,000 MWh/yr * 1000 kWh/MWh) * 0.3326 kg CO2e/kWh = 3,326,000 kg CO2e/yr = 3,326 tonnes CO2e/year
    *   **Net CO2 Removal:** 5,000 - 3,326 = **1,674 tonnes CO2e/year**

## 5. Discussion and Outlook

For the analysed scenario (10,000 MWh demand, 1000 km² land, Moomba weather, minimizing GWP/kWh), the model consistently favors maximizing PV installation up to the land limit. This occurs despite wind's significantly lower GWP factor (0.011 vs 0.07 kg CO2e/kWh) primarily because:
1.  **Land Efficiency:** PV requires far less land per MW (0.02 km²/MW) compared to wind (0.26 km²/MW).
2.  **Generation Profile:** At the Moomba site, the total annual energy potential deliverable per km² appears higher for PV than for wind, based on the specific models used.
Even with a large land area, the lowest GWP solution involved filling that area with PV and supplementing the remaining ~50% demand with grid power (and battery buffering), rather than allocating land to lower-GWP wind which would displace more total PV generation potential.

The inclusion of the 120 MWh battery significantly reduces grid dependency compared to a no-storage scenario but is insufficient to fully cover deficits for a load of this size with the variable renewable generation profile.

The results highlight the critical interplay between GWP factors, technology land footprints, site-specific weather resources, and system constraints (land area, demand level) in determining an optimal energy mix.

**Potential Improvements:**
*   **Refine Assumptions:** Use more detailed, potentially dynamic GWP factors, land use data, and component models (PV degradation, turbine choice, battery lifecycle).
*   **Battery Optimisation:** Include battery capacity (MWh) and power (MW) as variables within the optimisation search space instead of using fixed values.
*   **Demand Modelling:** Enhance the demand model to reflect more realistic operational profiles (e.g., for the CO2 removal system) beyond simple temperature correlation.
*   **Economic Analysis:** Add cost factors to explore trade-offs between GWP minimization and economic viability.
*   **Optimisation Algorithm:** Investigate more advanced optimisation techniques for potentially faster convergence or handling more complex variable spaces (e.g., if optimizing battery size).
*   **Sensitivity Analysis:** Assess the impact of varying land availability, demand levels, battery sizes, or GWP factors on the optimal solution.
