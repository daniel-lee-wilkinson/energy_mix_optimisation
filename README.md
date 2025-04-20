# Energy Mix Optimization Project

This project performs energy mix optimization analysis for renewable energy sources.

## Project Structure

```
project/
│
├── src/                  # Source code directory
│   └── energy_mix_optimization_YYYYMMDD_HHMMSS.py  # Main optimization script with timestamp
│
├── figures/              # Contains all figures/plots with timestamps
│   ├── demand_sensitivity_YYYYMMDD_HHMMSS.png
│   ├── generation_profiles_YYYYMMDD_HHMMSS.png
│   ├── gwp_by_temperature_YYYYMMDD_HHMMSS.png
│   └── ...
│
├── output_data/          # Contains all output data files with timestamps
│   ├── optimization_results_YYYYMMDD_HHMMSS.csv
│   ├── optimal_supply_profile_YYYYMMDD_HHMMSS.csv
│   └── ...
│
└── requirements_YYYYMMDD_HHMMSS.txt  # Python package dependencies with timestamp
```

## File Naming Convention

All files include a timestamp (YYYYMMDD_HHMMSS) in their filename to track when they were created or modified.

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