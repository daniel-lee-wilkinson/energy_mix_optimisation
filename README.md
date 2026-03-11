# Energy Mix Optimisation for DAC Operations

An hourly simulation and optimisation model that sizes PV and Wind capacity to minimise the **lifecycle GWP per kWh** supplied to a Direct Air Capture (DAC) facility, subject to land area constraints and battery dispatch logic. Built as a decision-support tool with executive-ready outputs.

> **Context:** DAC plants have high, continuous energy demands. The carbon intensity of that energy directly affects net CO₂ removal — poor energy sourcing can eliminate most of the climate benefit. This project quantifies that trade-off and finds the optimal renewable mix for a given site and demand level.

---

## What This Project Does

1. Fetches real weather data from the NASA POWER API (solar irradiance, wind speed, temperature) for a configurable site
2. Simulates energy supply hourly across a full year, combining PV, wind, battery storage, and grid fallback
3. Optimises PV/Wind capacity via grid search to minimise average GWP/kWh under land and demand constraints
4. Accounts for net CO₂ removal — reports gross GWP from energy supply against the atmospheric CO₂ removal credit
5. Runs demand sensitivity analysis — sweeps across demand levels to show how source mix and capacity shift
6. Generates publication-quality figures and a presentation-ready output suite

---

## Key Results (Example Scenario)

| Parameter | Value |
|---|---|
| Annual demand | 10,000 MWh |
| Land constraint | 1,000 km² |
| Optimal configuration | Maximum PV (50 GW) |
| Grid backup share | ~50% of energy |
| Rationale | PV's low lifecycle GWP (0.07 kg CO₂e/kWh) outweighs intermittency cost at this scale |

Even with ~50% grid backup, maximising PV minimises overall GWP/kWh — wind's higher land footprint (0.26 km²/MW vs 0.02 km²/MW for PV) limits its deployable capacity within the land constraint.

---

## Project Structure

```
project/
├── src/
│   └── energy_mix_optimization_*.py    # Core hourly simulation & optimisation
│
├── run_optimization.py                 # Main entry point — hourly grid search
├── run_lp_optimization.py              # Simplified LP model (annual averages, no battery)
├── run_demand_sensitivity.py           # Sweeps demand levels, plots source-share changes
│
├── figures/
│   ├── generation_profiles.png
│   ├── gwp_by_temperature.png
│   ├── monthly_energy_mix.png
│   ├── optimal_energy_mix.png
│   ├── optimal_system_profiles.png
│   ├── temperature_analysis.png
│   ├── demand_sensitivity_energy_mix.png
│   ├── demand_sensitivity_capacities.png
│   └── monthly_first_week_profiles/
│       └── hourly_supply_profile_month_MM.png
│
├── output_data/
│   ├── site_energy_data_potentials.csv  # Hourly generation potential per MW
│   ├── optimal_supply_profile.csv       # Hourly results for the optimal mix
│   └── demand_sensitivity_results.csv
│
├── requirements.txt
└── README.md
```

---

## Quickstart

```bash
# 1. Clone and create a virtual environment
git clone https://github.com/daniel-lee-wilkinson/energy_mix_optimisation
cd energy_mix_optimisation
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Configure your site via .env — see Environment Configuration below
#    If skipped, built-in anonymous defaults are used.

# 4. Run the main optimisation
python run_optimization.py
# You will be prompted for annual energy demand in MWh

# 5. (Optional) Run demand sensitivity sweep
python run_demand_sensitivity.py

# 6. (Optional) Run the simplified LP model
python run_lp_optimization.py
```

Figures are written to `figures/` and data to `output_data/`. Each run overwrites the previous output.

---

## Environment Configuration

Site coordinates and capacity search bounds are loaded from environment variables or a `.env` file in the project root (auto-loaded via `python-dotenv`). If not set, built-in anonymous defaults are used — the model runs without any configuration.

```env
# .env (keep out of version control)

PRIMARY_LOCATION_NAME=Primary Site
PRIMARY_LATITUDE=-XX.XXXX
PRIMARY_LONGITUDE=XXX.XXXX

FALLBACK_LOCATION_NAME=Fallback Site
FALLBACK_LATITUDE=-YY.YYYY
FALLBACK_LONGITUDE=YYY.YYYY

# Optional: capacity search bounds (MW)
PV_CAPACITY_MIN_MW=0
PV_CAPACITY_MAX_MW=800
WIND_CAPACITY_MIN_MW=0
WIND_CAPACITY_MAX_MW=400
CAPACITY_STEPS=40

# CO₂ removal credit for net GWP reporting
ANNUAL_CO2_REMOVAL_TONNES=5000
```

---

## Model Details

### Optimisation Approach

The main model (`run_optimization.py`) performs a **grid search** over PV and Wind capacity combinations, simulating each hourly over a full year and selecting the configuration that minimises average GWP/kWh supplied. A separate **LP model** (`run_lp_optimization.py`) provides a high-level cross-check using annual averages — faster but less accurate (no hourly dispatch, no battery).

### Key Assumptions

**PV**
- Panel efficiency: 15% (fixed)
- Temperature derating: −0.4%/°C above 25°C
- Land use: 0.02 km²/MW
- Lifecycle GWP: 0.07 kg CO₂e/kWh

**Wind**
- Standard power curve: cut-in 3 m/s, rated 12 m/s, cut-out 25 m/s
- Land use: 0.26 km²/MW
- Lifecycle GWP: 0.011 kg CO₂e/kWh

**Battery Storage (fixed size)**
- Capacity: 120 MWh | Power: 90 MW | Round-trip efficiency: 90% | Min SoC: 20%
- Charges from excess renewable generation only; discharges before any grid import

**Grid**
- Assumed infinitely available; GWP: 0.6 kg CO₂e/kWh

**Demand**
- User-specified annual target, scaled to hourly profile
- +20% demand when temperature > 30°C (cooling load proxy)

### Data Source

Weather data (solar irradiance, wind speed, temperature) is sourced from the [NASA POWER Project](https://power.larc.nasa.gov/) API at hourly resolution for the configured site. A fallback to a secondary site or synthetic data is used if the primary fetch fails.

---

## Outputs

| Output | Description |
|---|---|
| `optimal_energy_mix.png` | PV/Wind/Grid share for the optimal configuration |
| `monthly_energy_mix.png` | Month-by-month source breakdown |
| `optimal_system_profiles.png` | Hourly PV, wind, and temperature profiles for the optimal mix |
| `generation_profiles.png` | Annual generation potential profiles |
| `gwp_by_temperature.png` | GWP sensitivity to ambient temperature |
| `temperature_analysis.png` | Temperature distribution and demand adjustment |
| `demand_sensitivity_energy_mix.png` | How source shares shift across demand levels |
| `demand_sensitivity_capacities.png` | How optimal capacity scales with demand |
| `monthly_first_week_profiles/` | Hourly supply breakdown for the first week of each month |
| `optimal_supply_profile.csv` | Full hourly results: demand, PV, wind, battery SoC, grid import |
| `demand_sensitivity_results.csv` | Tabular sensitivity sweep results |

---

## Limitations & Future Work

- Battery size is fixed; co-optimising BESS capacity alongside PV/Wind would improve results
- Grid GWP is a static factor; a time-varying marginal emissions signal would better reflect real dispatch
- Demand profile uses a simple temperature adjustment; coupling to a real TVSA sorbent cycle model would improve accuracy
- Grid search resolution is configurable but coarse at default settings — finer sweeps increase runtime significantly

---

## Dependencies

```
pandas
numpy
matplotlib
scipy
requests
pytz
python-dotenv
```

Install via `pip install -r requirements.txt`.

---

## License

MIT
