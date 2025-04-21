# Energy Mix Optimization Project

This project performs energy mix optimization analysis for renewable energy sources.

## Project Structure

```
project/
│
├── src/                  # Source code directory
│   └── energy_mix_optimization_*.py  # Main optimization script
│
├── figures/              # Contains latest figures/plots
│   ├── old/              # Contains archived figures from previous runs
│   │   └── monthly_first_week_profiles/ # Archived weekly profiles
│   ├── monthly_first_week_profiles/ # Contains latest weekly profiles
│   └── ...
│
├── output_data/          # Contains latest output data files
│   ├── old/              # Contains archived data files from previous runs
│   └── ...
│
├── requirements.txt      # Python package dependencies 
└── README.md
```

## File Naming Convention

Output files include a timestamp (YYYYMMDD_HHMMSS) in their filename indicating when they were generated. Before each run, the script archives files from the previous run by moving them into corresponding `old/` subdirectories within `figures/` and `output_data/`.

## Setup

1. Create a Python virtual environment
2. Install the dependencies: `pip install -r requirements_YYYYMMDD_HHMMSS.txt`
3. Run the optimization script: `python src/energy_mix_optimization_YYYYMMDD_HHMMSS.py`

## Features

- Fetches real weather data from NASA POWER API
- Calculates optimal energy mix to minimize global warming potential
- Analyzes temperature effects on energy demand
- Optimizes land use for PV and wind installations
- Creates visualizations of energy generation profiles and optimization results 

## Assumptions

The model and analysis rely on the following key assumptions:

**General:**
*   **Location:** Primarily Moomba, Australia (-28.1083 S, 140.2028 E). Falls back to Coober Pedy, Australia (-29.0139 S, 134.7544 E) if Moomba data fails, then to synthetic data based on Moomba coordinates.
*   **Time Resolution:** All weather data and calculations are performed at an hourly resolution.
*   **Data Source:** Prefers real weather data from NASA POWER API. Generates synthetic data if API fails.

**PV Generation:**
*   **Efficiency:** Assumed constant at 15%.
*   **Temperature Effect:** Performance degrades by 0.4% for every 1°C increase above the Standard Test Condition (STC) temperature of 25°C.
*   **Land Use:** Requires 0.02 km² of land per MW of installed capacity.
*   **GWP (Lifecycle):** Assumed to be 0.041 kg CO2e per kWh generated.

**Wind Generation:**
*   **Power Curve:**
    *   Cut-in Speed: 3 m/s
    *   Rated Speed: 12 m/s
    *   Cut-out Speed: 25 m/s
    *   Power output follows a cubic relationship between cut-in and rated speeds.
*   **Land Use:** Requires 0.4 km² of land per MW of installed capacity (reflecting spacing needs).
*   **GWP (Lifecycle):** Assumed to be 0.011 kg CO2e per kWh generated.

**Grid Supply:**
*   **GWP:** Assumed to be 0.65 kg CO2e per kWh (representative value for South Australia, may vary).

**Energy Demand:**
*   **Annual Target:** The `annual_demand_mwh` value provided (e.g., 40 MWh in `main`) represents the *target total annual energy demand* that the optimized mix must meet.
*   **Hourly Profile Shaping:** An initial hourly demand profile is created by calculating a base average hourly demand from the annual target and then applying a temperature adjustment (increasing demand by 20% during hours > 30°C).
*   **Scaling:** This initial hourly profile is then scaled proportionally (up or down) so that the sum of hourly demands over the entire year exactly matches the specified `annual_demand_mwh` target.

**Optimization (`optimize_land_use` function):**
*   **Objective:** Minimize the overall Global Warming Potential (GWP) of the energy mix (PV, Wind, Grid).
*   **Primary Constraints:** Total land use must not exceed available land (e.g., 50 km² in `main`), and the total annual energy generated must meet the specified annual demand.
*   **Method:** Uses a grid search over a predefined range of potential PV and Wind capacities (0-50 MW each in 20 steps by default) to find the combination that minimizes GWP while satisfying constraints.

**Plotting:**
*   **Weekly Profiles:** Smoothed using a 6-hour rolling average.

## Input Data Structure

*   **Primary Source:** NASA POWER API (JSON format).
The script expects the API to provide hourly data for:
    *   `ALLSKY_SFC_SW_DWN`: All Sky Insolation Incident on a Horizontal Surface (W/m²)
    *   `WS2M`: Wind Speed at 2 Meters (m/s)
    *   `T2M`: Temperature at 2 Meters (°C)
*   **Internal Processing:** The fetched or synthetically generated data is initially processed into a pandas DataFrame (`weather_data`).
*   **Data Cleaning (within `fetch_nasa_power_data`):**
    *   **Type Conversion:** Attempts to convert `solar_irradiation`, `wind_speed`, and `temperature` columns to numeric types. Non-numeric values become `NaN`.
    *   **Missing Value Handling:** Replaces NASA POWER's standard missing value indicator (`-999.0`) with `NaN` in the key weather columns.
    *   **Row Removal:** Drops any rows (hourly records) that contain `NaN` in `solar_irradiation`, `wind_speed`, or `temperature` after the above steps.

## Output Data Structure

The script generates CSV data files and PNG image files.

**Data Files (in `output_data/`):**
*   `australian_energy_data_*.csv`:
    *   Contains the processed hourly weather and *potential* generation data for the entire analysis period, *before* optimization.
    *   Columns: `timestamp`, `solar_irradiation`, `wind_speed`, `temperature`, `pv_generation` (potential per MW), `wind_generation` (potential per MW), `total_generation` (potential PV+Wind), `month`, `hour`, `season`, `location`.
*   `optimal_supply_profile_*.csv`:
    *   Contains the hourly demand and generation profile for the *optimal* PV/Wind capacity mix determined by the `optimize_land_use` function.
    *   Columns: `timestamp`, `pv_generation` (actual kWh for optimal capacity), `wind_generation` (actual kWh), `renewable_total`, `demand` (adjusted), `grid_required`, `temperature`, `temp_bin`, `temp_category`, `hourly_gwp`.

**Figure Files (in `figures/`):**
*   `generation_profiles_*.png`: Time series plots of potential PV generation, potential Wind generation, and Temperature.
*   `monthly_energy_mix_*.png`: Stacked bar chart showing the contribution of PV, Wind, and Grid to meet monthly demand for the optimal mix.
*   `optimal_energy_mix_*.png`: Pie chart visualizing the percentage share of PV, Wind, and Grid in the final optimal annual energy mix.
*   `temperature_analysis_*.png`: Multi-panel plot analyzing temperature distribution and its impact on demand and the energy mix.
*   `gwp_by_temperature_*.png`: Bar chart showing the average GWP per kWh across different temperature ranges for the optimal mix.
*   `figures/monthly_first_week_profiles/hourly_supply_profile_month_*.png`: Plots visualizing the hourly supply (PV, Wind, Grid) vs. demand for the first week of each month for the optimal mix.

**Archiving:**
*   Before each run, existing `.png` files in `figures/` and `figures/monthly_first_week_profiles/` are moved to respective `old/` subdirectories.
*   Before each run, existing files in `output_data/` are moved to `output_data/old/`. 