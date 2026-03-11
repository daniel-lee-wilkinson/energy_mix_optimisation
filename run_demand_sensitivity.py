#!/usr/bin/env python
"""
Run demand sensitivity analysis for the hourly optimisation model.

This script sweeps annual demand values and visualises how PV/Wind/Grid
shares change under a fixed land constraint while minimising GWP.
"""

import glob
import importlib.util
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def find_latest_script() -> str:
    """Find the latest timestamped optimisation script in the src directory."""
    scripts = glob.glob('src/energy_mix_optimization_*.py')
    if not scripts:
        print('Error: No optimisation scripts found in src directory')
        sys.exit(1)

    latest_script = sorted(scripts)[-1]
    print(f'Using latest script: {latest_script}')
    return latest_script


def load_latest_module():
    """Import the latest optimisation module dynamically."""
    script_path = find_latest_script()
    module_name = os.path.splitext(os.path.basename(script_path))[0]

    spec = importlib.util.spec_from_file_location(module_name, script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _prompt_float(prompt: str, min_value: float = None, default: float = None) -> float:
    """Prompt for a float with optional lower bound and default value."""
    while True:
        raw = input(prompt).strip()
        if raw == '' and default is not None:
            value = float(default)
        else:
            try:
                value = float(raw)
            except ValueError:
                print('Invalid number, please try again.')
                continue

        if min_value is not None and value < min_value:
            print(f'Value must be >= {min_value}.')
            continue
        return value


def _prompt_int(prompt: str, min_value: int = None, default: int = None) -> int:
    """Prompt for an int with optional lower bound and default value."""
    while True:
        raw = input(prompt).strip()
        if raw == '' and default is not None:
            value = int(default)
        else:
            try:
                value = int(raw)
            except ValueError:
                print('Invalid integer, please try again.')
                continue

        if min_value is not None and value < min_value:
            print(f'Value must be >= {min_value}.')
            continue
        return value


def _get_capacity_overrides(module):
    """Read optional capacity bounds from environment with module helpers."""
    get_float = getattr(module, '_get_env_optional_float', None)
    get_int = getattr(module, '_get_env_optional_int', None)

    if callable(get_float) and callable(get_int):
        return {
            'pv_min_mw': get_float('PV_CAPACITY_MIN_MW') if get_float('PV_CAPACITY_MIN_MW') is not None else 0.0,
            'pv_max_mw': get_float('PV_CAPACITY_MAX_MW'),
            'wind_min_mw': get_float('WIND_CAPACITY_MIN_MW') if get_float('WIND_CAPACITY_MIN_MW') is not None else 0.0,
            'wind_max_mw': get_float('WIND_CAPACITY_MAX_MW'),
            'capacity_steps': get_int('CAPACITY_STEPS') if get_int('CAPACITY_STEPS') is not None else 30,
        }

    # Fallback parser if helpers are unavailable.
    def parse_float(name):
        value = os.getenv(name)
        if value is None or value.strip() == '':
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def parse_int(name):
        value = os.getenv(name)
        if value is None or value.strip() == '':
            return None
        try:
            return int(value)
        except ValueError:
            return None

    return {
        'pv_min_mw': parse_float('PV_CAPACITY_MIN_MW') or 0.0,
        'pv_max_mw': parse_float('PV_CAPACITY_MAX_MW'),
        'wind_min_mw': parse_float('WIND_CAPACITY_MIN_MW') or 0.0,
        'wind_max_mw': parse_float('WIND_CAPACITY_MAX_MW'),
        'capacity_steps': parse_int('CAPACITY_STEPS') or 30,
    }


def _get_annual_removal_tonnes(module) -> float:
    """Read annual CO2 removal credit (tCO2e/yr) from env with default."""
    get_float = getattr(module, '_get_env_optional_float', None)
    if callable(get_float):
        value = get_float('ANNUAL_CO2_REMOVAL_TONNES')
        return 5000.0 if value is None else float(value)

    value = os.getenv('ANNUAL_CO2_REMOVAL_TONNES')
    if value is None or value.strip() == '':
        return 5000.0
    try:
        return float(value)
    except ValueError:
        return 5000.0


def run_demand_sensitivity():
    module = load_latest_module()
    module.apply_publication_formatting()
    module.ensure_base_directories()

    print('\n=== Demand Sensitivity Analysis ===')
    available_land_km2 = _prompt_float('Available land area in km² [default 1000]: ', min_value=1, default=1000)
    demand_min_mwh = _prompt_float('Minimum annual demand in MWh: ', min_value=1)
    demand_max_mwh = _prompt_float('Maximum annual demand in MWh: ', min_value=demand_min_mwh)
    demand_points = _prompt_int('Number of demand points [default 8]: ', min_value=2, default=8)

    demands = np.linspace(demand_min_mwh, demand_max_mwh, demand_points)

    start_date, end_date = module.get_analysis_period(quick_test=False)
    primary, fallback = module.load_location_configuration()
    energy_data, location_name_used, use_synthetic = module.load_energy_data_with_fallback(
        primary,
        fallback,
        start_date,
        end_date,
    )

    if energy_data is None or energy_data.empty:
        print('CRITICAL ERROR: No valid energy data loaded. Exiting.')
        return

    print(
        f"\nData source: {location_name_used}"
        f"{' (synthetic)' if use_synthetic else ' (real NASA POWER)'}"
    )

    capacity_overrides = _get_capacity_overrides(module)
    annual_co2_removal_tonnes = _get_annual_removal_tonnes(module)
    print('Capacity range settings used for each demand point:')
    print(
        f"  PV min/max: {capacity_overrides['pv_min_mw']} / {capacity_overrides['pv_max_mw']}"
        f"  | Wind min/max: {capacity_overrides['wind_min_mw']} / {capacity_overrides['wind_max_mw']}"
        f"  | Steps: {capacity_overrides['capacity_steps']}"
    )
    print(f"  Annual CO2 removal credit: {annual_co2_removal_tonnes:.2f} tCO2e/yr")

    rows = []
    for idx, demand_mwh in enumerate(demands, start=1):
        print(f"\n[{idx}/{len(demands)}] Optimising for annual demand = {demand_mwh:.2f} MWh")

        pv_caps, wind_caps = module.calculate_dynamic_capacity_ranges(
            energy_data=energy_data,
            annual_demand_mwh=float(demand_mwh),
            available_land_km2=available_land_km2,
            pv_land_per_mw=0.02,
            wind_land_per_mw=0.26,
            pv_min_mw=capacity_overrides['pv_min_mw'],
            pv_max_mw=capacity_overrides['pv_max_mw'],
            wind_min_mw=capacity_overrides['wind_min_mw'],
            wind_max_mw=capacity_overrides['wind_max_mw'],
            num_capacity_steps=capacity_overrides['capacity_steps'],
        )

        result = module.optimise_land_use(
            energy_data=energy_data.copy(),
            annual_demand_mwh=float(demand_mwh),
            available_land_km2=available_land_km2,
            pv_land_per_mw=0.02,
            wind_land_per_mw=0.26,
            pv_gwp=0.07,
            wind_gwp=0.011,
            grid_gwp=0.6,
            annual_co2_removal_tonnes=annual_co2_removal_tonnes,
            pv_capacities=pv_caps,
            wind_capacities=wind_caps,
            save_artifacts=False,
        )

        if result.get('error'):
            print(f"  Skipped: {result['error']}")
            continue

        rows.append({
            'annual_demand_mwh': float(demand_mwh),
            'pv_share_pct': result['pv_share'],
            'wind_share_pct': result['wind_share'],
            'grid_share_pct': result['grid_share'],
            'gross_gwp_kgco2e_per_kwh': result['total_gwp'],
            'net_gwp_kgco2e_per_kwh': result.get('net_gwp', result['total_gwp']),
            'pv_capacity_mw': result['pv_capacity'],
            'wind_capacity_mw': result['wind_capacity'],
            'grid_annual_mwh': result['grid_annual_total'] / 1000,
            'gross_annual_emissions_kgco2e': result.get('gross_annual_emissions_kgco2e', np.nan),
            'net_annual_emissions_kgco2e': result.get('net_annual_emissions_kgco2e', np.nan),
        })

    if not rows:
        print('No feasible solutions were produced for the selected demand range.')
        return

    results_df = pd.DataFrame(rows).sort_values('annual_demand_mwh')

    os.makedirs('output_data', exist_ok=True)
    os.makedirs('figures', exist_ok=True)

    results_path = os.path.join('output_data', 'demand_sensitivity_results.csv')
    results_df.to_csv(results_path, index=False)
    print(f'\nSaved demand sensitivity table to {results_path}')

    # Plot 1: shares (stacked area) + GWP (secondary axis).
    fig, ax1 = plt.subplots(figsize=(12, 7))
    x = results_df['annual_demand_mwh'].values

    ax1.stackplot(
        x,
        results_df['pv_share_pct'].values,
        results_df['wind_share_pct'].values,
        results_df['grid_share_pct'].values,
        labels=['PV share', 'Wind share', 'Grid share'],
        colors=['gold', 'deepskyblue', 'dimgray'],
        alpha=0.85,
    )
    ax1.set_xlabel('Annual Demand (MWh)')
    ax1.set_ylabel('Energy Share (%)')
    ax1.set_ylim(0, 100)
    ax1.grid(True, linestyle='--', alpha=0.4)

    ax2 = ax1.twinx()
    ax2.plot(
        x,
        results_df['net_gwp_kgco2e_per_kwh'].values,
        color='black',
        marker='o',
        linewidth=2,
        label='Average Net GWP',
    )
    ax2.set_ylabel('Average Net GWP (kg CO2e/kWh)')

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc='upper left')

    plt.title('Energy Mix Share vs Annual Demand (Fixed Land Area)')
    plt.tight_layout()
    share_plot_path = os.path.join('figures', 'demand_sensitivity_energy_mix.png')
    plt.savefig(share_plot_path, bbox_inches='tight')
    plt.close()
    print(f'Saved demand share plot to {share_plot_path}')

    # Plot 2: required PV/Wind capacities vs demand.
    plt.figure(figsize=(12, 7))
    plt.plot(x, results_df['pv_capacity_mw'].values, color='goldenrod', marker='o', label='PV Capacity (MW)')
    plt.plot(x, results_df['wind_capacity_mw'].values, color='teal', marker='s', label='Wind Capacity (MW)')
    plt.xlabel('Annual Demand (MWh)')
    plt.ylabel('Optimal Capacity (MW)')
    plt.title('Optimal Capacity vs Annual Demand (Fixed Land Area)')
    plt.grid(True, linestyle='--', alpha=0.4)
    plt.legend()
    plt.tight_layout()
    cap_plot_path = os.path.join('figures', 'demand_sensitivity_capacities.png')
    plt.savefig(cap_plot_path, bbox_inches='tight')
    plt.close()
    print(f'Saved capacity plot to {cap_plot_path}')


if __name__ == '__main__':
    run_demand_sensitivity()
