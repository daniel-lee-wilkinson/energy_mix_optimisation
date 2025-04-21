from dotenv import load_dotenv
load_dotenv() 
        

import pandas as pd
import numpy as np
from scipy.optimize import minimize
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import os
import shutil # Import shutil for moving files
import pytz
import math
import requests
from io import StringIO
import traceback

def calculate_solar_position(dates, latitude, longitude):
    """
    Calculate solar elevation and azimuth angles using basic astronomical formulas
    """
    # Convert latitude to radians
    lat_rad = math.radians(latitude)
    
    # Initialize arrays for results
    elevation = np.zeros(len(dates))
    azimuth = np.zeros(len(dates))
    
    for i, date in enumerate(dates):
        # Calculate day of year (1-365)
        day_of_year = date.timetuple().tm_yday
        
        # Calculate solar declination (in radians)
        declination = math.radians(23.45 * math.sin(math.radians(360 * (284 + day_of_year) / 365)))
        
        # Calculate hour angle (in radians)
        hour = date.hour + date.minute/60
        hour_angle = math.radians(15 * (hour - 12))
        
        # Calculate solar elevation angle
        sin_elevation = (math.sin(lat_rad) * math.sin(declination) + 
                        math.cos(lat_rad) * math.cos(declination) * math.cos(hour_angle))
        elevation[i] = math.degrees(math.asin(sin_elevation))
        
        # Calculate solar azimuth angle
        cos_azimuth = ((math.sin(declination) * math.cos(lat_rad) - 
                       math.cos(declination) * math.sin(lat_rad) * math.cos(hour_angle)) / 
                      math.cos(math.radians(elevation[i])))
        azimuth[i] = math.degrees(math.acos(max(-1, min(1, cos_azimuth))))
        
        # Adjust azimuth for morning/afternoon
        if hour_angle > 0:
            azimuth[i] = 360 - azimuth[i]
    
    return pd.DataFrame({
        'elevation': elevation,
        'azimuth': azimuth
    })

def fetch_nasa_power_data(latitude, longitude, start_date, end_date):
    """
    Fetch weather data from NASA POWER dataset
    """
    # Convert dates to required format
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d')
    
    start_str = start_date.strftime('%Y%m%d')
    end_str = end_date.strftime('%Y%m%d')
    
    # NASA POWER API endpoint
    base_url = "https://power.larc.nasa.gov/api/temporal/hourly/point"
    
    # Parameters for the API request, including temperature (T2M)
    params = {
        "parameters": "ALLSKY_SFC_SW_DWN,WS2M,T2M",  # Solar radiation, wind speed at 2m, and temperature at 2m
        "community": "RE",
        "longitude": longitude,
        "latitude": latitude,
        "start": start_str,
        "end": end_str,
        "format": "JSON"  # Use JSON instead of CSV
    }
    
    try:
        print(f"Requesting data from NASA POWER API for period {start_str} to {end_str}...")
        # Make the API request
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        
        print("Data received successfully from NASA POWER API.")
        
        # Parse the JSON data
        try:
            json_data = response.json()
            
            # Extract the time series data
            properties = json_data.get('properties', {})
            parameters = properties.get('parameter', {})
            
            # Get time details
            time_info = properties.get('temporal', {})
            time_start = datetime.strptime(time_info.get('begin', start_str), '%Y%m%d')
            
            # Extract the data arrays
            solar_data = parameters.get('ALLSKY_SFC_SW_DWN', {})
            wind_data = parameters.get('WS2M', {})
            temp_data = parameters.get('T2M', {})
            
            # Get the timestamps (format: YYYYMMDD-HH where HH is 00-23)
            timestamps = list(solar_data.keys())
            timestamps.sort()  # Ensure chronological order
            
            # Create a dataframe
            data_list = []
            for ts in timestamps:
                # Parse timestamp: YYYYMMDD-HH
                year = int(ts[:4])
                month = int(ts[4:6])
                day = int(ts[6:8])
                hour = int(ts[9:11])
                
                timestamp = datetime(year, month, day, hour)
                
                # Get values for this timestamp
                solar_value = solar_data.get(ts, None)
                wind_value = wind_data.get(ts, None)
                temp_value = temp_data.get(ts, None)
                
                # Add to data list
                data_list.append({
                    'timestamp': timestamp,
                    'solar_irradiation': solar_value,
                    'wind_speed': wind_value,
                    'temperature': temp_value
                })
            
            # Create DataFrame
            df = pd.DataFrame(data_list)
            
            print(f"Parsed JSON data with {len(df)} rows.")
            
            # --- ETL Pipeline: Clean Data ---
            initial_rows = len(df)
            print("Starting data cleaning...")
            
            # Define columns to clean
            columns_to_clean = ['solar_irradiation', 'wind_speed', 'temperature']
            
            # Replace common filler values (-999) with NaN
            for col in columns_to_clean:
                if col in df.columns:
                    # Ensure column is numeric before replacing - use errors='coerce' to turn non-numeric into NaN
                    df[col] = pd.to_numeric(df[col], errors='coerce') 
                    df[col] = df[col].replace(-999.0, np.nan) # NASA POWER uses -999 for missing data
            
            # Drop rows with NaN in specified columns
            df.dropna(subset=columns_to_clean, inplace=True)
            
            cleaned_rows = len(df)
            rows_dropped = initial_rows - cleaned_rows
            print(f"Data cleaning finished. Dropped {rows_dropped} rows with missing values.")
            # --- End ETL Pipeline ---

            if len(df) > 0:
                print("Sample of cleaned data:")
                print(df.head(3))
                
            return df
            
        except Exception as e:
            print(f"Error parsing JSON: {e}")
            print("First 200 characters of response:")
            print(response.text[:200])
            raise
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching NASA POWER data: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status code: {e.response.status_code}")
            print(f"Response text: {e.response.text[:200]}...")  # Print first 200 chars
        return None

def process_real_data(weather_data, pv_capacity=1000, wind_capacity=2000):
    """
    Process real weather data to calculate generation potential per MW.
    The pv_capacity and wind_capacity arguments are no longer used directly 
    for calculating output columns but are kept for potential future use or compatibility.
    """
    # Calculate PV generation (kWh)
    # First ensure zero generation when sun is below horizon (elevation ≤ 0)
    # Calculate solar position for each timestamp
    dates = weather_data['timestamp'].tolist()
    # Moomba coordinates (use these directly as we know them)
    latitude = -28.1083  # South
    longitude = 140.2028  # East
    
    # Calculate solar position to determine day/night
    solpos = calculate_solar_position(dates, latitude, longitude)
    
    # Align index with weather_data before creating mask
    solpos.index = weather_data.index

    # Ensure zero generation when sun is below horizon
    # Create a mask for nighttime (elevation ≤ 0)
    night_mask = solpos['elevation'] <= 0
    
    # Apply solar panel efficiency and temperature corrections for daytime
    pv_efficiency = 0.15
    stc_temp = 25  # Standard Test Condition temperature in °C
    temp_coefficient = -0.004  # -0.4% per degree Celsius

    # Calculate temperature effect dynamically based on weather_data['temperature']
    # Note: Ensure 'temperature' column exists before this calculation. 
    # The code below already adds synthetic temperature if it's missing.
    temp_effect = 1 + (weather_data['temperature'] - stc_temp) * temp_coefficient
    
    # --- Calculate PV Generation Potential per MW ---
    weather_data['pv_potential_per_mw'] = (
        weather_data['solar_irradiation'] * 
        pv_efficiency * 
        1 *  # Calculate for 1 MW capacity
        temp_effect / 1000  # Convert W to kW (potential kWh per hour)
    )

    # Ensure generation potential is non-negative after temperature correction
    weather_data['pv_potential_per_mw'] = weather_data['pv_potential_per_mw'].clip(lower=0)
    
    # Ensure zero potential at night
    weather_data.loc[night_mask, 'pv_potential_per_mw'] = 0
    
    # --- Calculate Wind Generation Potential per MW ---
    # Assuming wind turbine with power curve, scaled for 1 MW
    cut_in_speed = 3  # m/s
    rated_speed = 12  # m/s
    cut_out_speed = 25  # m/s
    rated_capacity_kw = 1000 # Rated capacity for 1 MW turbine in kW
    
    def wind_power_curve_per_mw(speed):
        if speed < cut_in_speed:
            return 0
        elif speed > cut_out_speed:
            return 0
        elif speed >= rated_speed:
            return rated_capacity_kw / 1000 # Return potential in kWh per hour
        else:
            # Correct cubic relationship between wind speed and power
            normalised_speed = (speed - cut_in_speed) / (rated_speed - cut_in_speed)
            # Calculate power in kW, then convert to kWh/hour potential
            power_kw = (rated_capacity_kw * normalised_speed ** 3)
            return power_kw / 1000
    
    weather_data['wind_potential_per_mw'] = weather_data['wind_speed'].apply(wind_power_curve_per_mw)
    
    # --- Remove old/unused generation columns ---
    # weather_data.drop(columns=['pv_generation', 'wind_generation', 'total_generation'], errors='ignore', inplace=True)
    
    # --- Add time/season columns --- 
    weather_data['month'] = weather_data['timestamp'].dt.month
    weather_data['hour'] = weather_data['timestamp'].dt.hour
    weather_data['season'] = weather_data['timestamp'].dt.month % 12 // 3 + 1
    
    # If we don't have temperature data in real weather data, generate synthetic temperature
    if 'temperature' not in weather_data.columns:
        print("Adding synthetic temperature data to real weather data")
        # Generate synthetic temperature based on season and time of day
        base_temp = 20  # Base temperature
        seasonal_temp = np.sin(2 * np.pi * (weather_data['timestamp'].dt.dayofyear + 183) / 365) * 15
        diurnal_temp = np.sin(np.pi * weather_data['timestamp'].dt.hour / 24) * 5
        
        # Add some correlation with solar irradiation
        solar_effect = (weather_data['solar_irradiation'] / weather_data['solar_irradiation'].max()) * 3
        
        weather_data['temperature'] = base_temp + seasonal_temp + diurnal_temp + solar_effect + np.random.normal(0, 2, len(weather_data))
    
    return weather_data

def generate_moomba_data(start_date, end_date, resolution='1H', use_real_data=True):
    """
    Generate weather and generation data for Moomba, Australia
    Coordinates: 28° 06′ 30″ S, 140° 12′ 10″ E
    """
    # Moomba coordinates
    latitude = -28.1083  # South
    longitude = 140.2028  # East
    
    if use_real_data:
        # Fetch real data from NASA POWER
        data = fetch_nasa_power_data(latitude, longitude, start_date, end_date)
        if data is not None:
            # Process the real data
            data = process_real_data(data)
            return data
        else:
            print("Falling back to synthetic data due to API error")
    
    # Fallback to synthetic data if real data fetch fails
    return generate_synthetic_data(start_date, end_date, latitude, longitude)

def generate_synthetic_data(start_date, end_date, latitude, longitude):
    """
    Generate synthetic weather data (fallback method)
    """
    # Create time range
    date_range = pd.date_range(start=start_date, end=end_date, freq='1H')
    
    # Calculate solar position
    solpos = calculate_solar_position(date_range, latitude, longitude)
    
    # Generate synthetic data
    np.random.seed(42)  # For reproducibility
    
    # Solar irradiation (W/m²) - adjusted for southern hemisphere
    base_irradiation = 1000
    seasonal_variation = np.sin(2 * np.pi * (date_range.dayofyear + 183) / 365) * 300
    daily_pattern = np.sin(np.radians(solpos['elevation'])) * 0.8
    solar_irradiation = np.maximum(0, base_irradiation + seasonal_variation + daily_pattern * base_irradiation)
    
    # Wind speed (m/s)
    base_wind = 6
    seasonal_wind = np.sin(2 * np.pi * (date_range.dayofyear + 183) / 365) * 3
    diurnal_variation = np.sin(2 * np.pi * date_range.hour / 24) * 2
    wind_speed = np.maximum(0, base_wind + seasonal_wind + diurnal_variation + np.random.normal(0, 1.5, len(date_range)))
    
    # Temperature (°C) - synthesize temperature data based on season and time of day
    base_temp = 20  # Base temperature
    seasonal_temp = np.sin(2 * np.pi * (date_range.dayofyear + 183) / 365) * 15  # +/-15°C seasonal variation
    diurnal_temp = np.sin(np.pi * date_range.hour / 24) * 5  # +/-5°C daily variation
    temperature = base_temp + seasonal_temp + diurnal_temp + np.random.normal(0, 2, len(date_range))  # Add some noise
    
    # Create DataFrame
    data = pd.DataFrame({
        'timestamp': date_range,
        'solar_irradiation': solar_irradiation,
        'wind_speed': wind_speed,
        'temperature': temperature
    })
    
    # Process the synthetic data
    data = process_real_data(data)
    
    return data

def calculate_temperature_adjusted_demand(base_demand, temperature):
    """
    Calculate temperature-adjusted energy demand
    
    Parameters:
    -----------
    base_demand : float
        Base demand in kWh
    temperature : array-like
        Temperature values in °C
    
    Returns:
    --------
    array-like
        Temperature-adjusted demand
    """
    # Simple model: demand is base_demand until 30°C, then increases by 20%
    adjustment = np.where(temperature > 30, 1.2, 1.0)
    
    # Return adjusted demand
    return base_demand * adjustment

def optimise_land_use(energy_data, annual_demand_mwh, available_land_km2, 
                       pv_land_per_mw=0.02, wind_land_per_mw=0.26, 
                       pv_gwp=0.041, wind_gwp=0.011, grid_gwp=0.65, 
                       pv_capacities=np.linspace(0, 300, 30), wind_capacities=np.linspace(0, 200, 30), 
                       figures_dir='figures', output_data_dir='output_data',
                       target_demand_temp_threshold=30, target_demand_increase_factor=1.2,
                       # --- Battery Parameters ---
                       battery_capacity_mwh=120, # Added: Fixed battery capacity in MWh
                       battery_power_mw=90,     # Added: Fixed battery power rating in MW (0.75C of 120 MWh)
                       battery_efficiency=0.90, # Added: Round-trip efficiency (applied on discharge)
                       battery_min_soc=0.20):  # Added: Minimum state of charge
    """
    Optimises PV and Wind capacity to meet annual demand within land constraints,
    minimising GWP, incorporating fixed battery storage. Also includes
    temperature-adjusted demand and generates outputs.

    Args:
        energy_data (pd.DataFrame): Processed weather data with potential generation per MW.
        annual_demand_mwh (float): Target total annual energy demand in MWh.
        available_land_km2 (float): Maximum land area available for PV and Wind.
        pv_land_per_mw (float): Land required per MW of PV capacity (km²/MW).
        wind_land_per_mw (float): Land required per MW of Wind capacity (km²/MW).
        pv_gwp (float): GWP for PV (kg CO2e/kWh).
        wind_gwp (float): GWP for Wind (kg CO2e/kWh).
        grid_gwp (float): GWP for Grid (kg CO2e/kWh).
        pv_capacities (np.array): Range of PV capacities (MW) to test.
        wind_capacities (np.array): Range of Wind capacities (MW) to test.
        figures_dir (str): Directory to save plots.
        output_data_dir (str): Directory to save output CSV data.
        target_demand_temp_threshold (float): Temperature threshold (°C) for increased demand.
        target_demand_increase_factor (float): Factor by which demand increases above threshold.
        battery_capacity_mwh (float): Energy capacity of the battery storage in MWh.
        battery_power_mw (float): Maximum charge/discharge power of the battery in MW.
        battery_efficiency (float): Round-trip efficiency of the battery.
        battery_min_soc (float): Minimum allowed state of charge fraction (e.g., 0.2 for 20%).

    Returns:
        dict: Dictionary containing the results of the optimisation.
    """
    print("Starting land use optimisation...")
    print(f"Target Annual Demand: {annual_demand_mwh} MWh")
    print(f"Available Land: {available_land_km2} km²")
    print(f"PV Land Use: {pv_land_per_mw} km²/MW, Wind Land Use: {wind_land_per_mw} km²/MW")
    print(f"GWP Factors (kg CO2e/kWh): PV={pv_gwp}, Wind={wind_gwp}, Grid={grid_gwp}")
    print(f"Battery: {battery_capacity_mwh} MWh, {battery_power_mw} MW, {battery_efficiency*100}% eff, {battery_min_soc*100}% min SoC")

    # Ensure output directories exist
    os.makedirs(figures_dir, exist_ok=True)
    os.makedirs(output_data_dir, exist_ok=True)
    os.makedirs(os.path.join(figures_dir, 'monthly_first_week_profiles'), exist_ok=True)

    # --- Demand Calculation with Temperature Adjustment ---
    num_hours = len(energy_data)
    base_hourly_demand = (annual_demand_mwh * 1000) / num_hours # Convert MWh to kWh
    print(f"Calculated base average hourly demand: {base_hourly_demand:.2f} kWh")

    # Apply temperature adjustment
    energy_data['demand'] = base_hourly_demand
    temp_increase_mask = energy_data['temperature'] > target_demand_temp_threshold
    energy_data.loc[temp_increase_mask, 'demand'] *= target_demand_increase_factor
    
    # Scale demand to exactly match the annual target
    current_annual_demand_kwh = energy_data['demand'].sum()
    required_annual_demand_kwh = annual_demand_mwh * 1000
    scaling_factor = required_annual_demand_kwh / current_annual_demand_kwh if current_annual_demand_kwh > 0 else 1
    energy_data['demand'] *= scaling_factor
    final_annual_demand_kwh = energy_data['demand'].sum()
    print(f"Temperature-adjusted annual demand calculated: {final_annual_demand_kwh / 1000:.2f} MWh (scaling factor: {scaling_factor:.4f})")
    
    # Store adjusted demand for later use
    adjusted_demand_profile = energy_data['demand'].copy()

    # --- Initialize best_mix with high grid usage and GWP ---
    best_mix = {
        'pv_capacity': -1, 
        'wind_capacity': -1, 
        'total_gwp': float('inf'), 
        'land_used': -1,
        'pv_annual_total': 0,
        'wind_annual_total': 0,
        'grid_annual_total': float('inf'), # Primary objective: minimize this
        'total_annual_generation': 0,
        'pv_share': 0,
        'wind_share': 0,
        'grid_share': 0,
        'grid_deficit_hours': 0,
        'grid_deficit_percentage': 0,
        'max_hourly_deficit': 0,
        'pv_hourly': None, # Store hourly data for the optimal mix
        'wind_hourly': None,
        'grid_hourly': None,
        'demand_hourly': None,
        'battery_soc_hourly': None, # Added: Battery State of Charge
        'battery_charge_hourly': None, # Added: Battery Charge
        'battery_discharge_hourly': None, # Added: Battery Discharge
        'curtailment_hourly': None, # Added: Renewable Curtailment
        'battery_cycles': 0 # Added: Estimated battery cycles
    }
    total_combinations = len(pv_capacities) * len(wind_capacities)
    print(f"Starting grid search over {total_combinations} capacity combinations (with battery simulation)...\n")
    count = 0

    # --- Add flag for verbose debugging ---
    verbose_debug = True # Set to False to reduce output

    for pv_cap in pv_capacities:
        for wind_cap in wind_capacities:
            count += 1
            # --- Optional: Reduce debug output frequency ---
            # verbose_print = verbose_debug and (count % 100 == 0 or count == 1) 
            verbose_print = verbose_debug # Print for every combination for now

            if verbose_print: 
                 print(f"\n-- Checking Combo {count}/{total_combinations}: PV={pv_cap:.1f} MW, Wind={wind_cap:.1f} MW --")
                 
            # Calculate land use for this combination
            pv_land = pv_cap * pv_land_per_mw
            wind_land = wind_cap * wind_land_per_mw
            total_land = pv_land + wind_land
            if verbose_print: print(f"  Land Used: {total_land:.2f} km² (PV: {pv_land:.2f}, Wind: {wind_land:.2f}) / {available_land_km2:.2f} km² limit")

            # Check land constraint
            if total_land > available_land_km2:
                if verbose_print: print("  Skipping: Exceeds land limit.")
                continue # Skip if land constraint is violated

            # Calculate hourly generation for this capacity mix
            pv_hourly = energy_data['pv_potential_per_mw'] * pv_cap
            wind_hourly = energy_data['wind_potential_per_mw'] * wind_cap
            renewable_total_hourly = pv_hourly + wind_hourly

            # Use the pre-calculated adjusted demand profile
            demand_hourly = adjusted_demand_profile
            
            # --- Initialize Battery Simulation Variables ---
            num_hours = len(energy_data)
            battery_capacity_kwh = battery_capacity_mwh * 1000
            battery_power_kw = battery_power_mw * 1000
            min_soc_kwh = battery_capacity_kwh * battery_min_soc
            
            # Start battery at minimum state of charge
            battery_soc_hourly = np.zeros(num_hours + 1) # +1 to store final state easily
            battery_soc_hourly[0] = min_soc_kwh 
            
            battery_charge_hourly = np.zeros(num_hours)
            battery_discharge_hourly = np.zeros(num_hours) # Net energy delivered by battery
            grid_required_hourly = np.zeros(num_hours)
            curtailment_hourly = np.zeros(num_hours)
            
            # --- Hourly Energy Balance Loop with Battery ---
            for t in range(num_hours):
                current_soc_kwh = battery_soc_hourly[t]
                
                # Get generation and demand for the hour (kWh)
                renewable_gen_kwh = renewable_total_hourly.iloc[t]
                demand_kwh = demand_hourly.iloc[t]
                balance_kwh = renewable_gen_kwh - demand_kwh

                charge_kwh = 0
                discharge_net_kwh = 0
                grid_kwh = 0
                curtailment_kwh = 0
                actual_discharge_gross_kwh = 0 # Energy leaving battery storage

                if balance_kwh > 0: # Excess generation
                    potential_charge_kwh = balance_kwh
                    soc_space_kwh = battery_capacity_kwh - current_soc_kwh
                    
                    # Charge limited by excess, power rating, and available SoC space
                    charge_kwh = min(potential_charge_kwh, battery_power_kw, soc_space_kwh)
                    
                    # Update SoC
                    current_soc_kwh += charge_kwh
                    curtailment_kwh = potential_charge_kwh - charge_kwh # Store curtailed energy
                
                elif balance_kwh < 0: # Deficit
                    deficit_kwh = abs(balance_kwh)
                    
                    # Max energy that *can* leave battery physically (respecting min SoC)
                    available_discharge_gross_kwh = current_soc_kwh - min_soc_kwh
                    
                    # Max energy that *can* leave battery due to power limit
                    power_limited_discharge_gross_kwh = battery_power_kw 
                    
                    # Potential discharge (limited by SoC and Power)
                    potential_discharge_gross_kwh = min(available_discharge_gross_kwh, power_limited_discharge_gross_kwh)

                    # How much gross energy needs to leave battery to meet deficit (after efficiency loss)
                    discharge_needed_gross_kwh = deficit_kwh / battery_efficiency
                    
                    # Actual gross energy leaving battery
                    actual_discharge_gross_kwh = min(potential_discharge_gross_kwh, discharge_needed_gross_kwh)
                    
                    # Net energy delivered to meet demand
                    discharge_net_kwh = actual_discharge_gross_kwh * battery_efficiency
                    
                    # Update SoC
                    current_soc_kwh -= actual_discharge_gross_kwh
                    
                    # Grid makes up the rest
                    grid_kwh = max(0, deficit_kwh - discharge_net_kwh) # Ensure grid is non-negative
                
                # Store results for the hour
                battery_soc_hourly[t+1] = current_soc_kwh
                battery_charge_hourly[t] = charge_kwh
                battery_discharge_hourly[t] = discharge_net_kwh # Store net delivered energy
                grid_required_hourly[t] = grid_kwh
                curtailment_hourly[t] = curtailment_kwh

            # Convert hourly numpy arrays back to pandas Series with correct index
            grid_required_hourly_series = pd.Series(grid_required_hourly, index=energy_data.index)
            battery_soc_hourly_series = pd.Series(battery_soc_hourly[:-1], index=energy_data.index) # Exclude final state for length match
            battery_charge_hourly_series = pd.Series(battery_charge_hourly, index=energy_data.index)
            battery_discharge_hourly_series = pd.Series(battery_discharge_hourly, index=energy_data.index)
            curtailment_hourly_series = pd.Series(curtailment_hourly, index=energy_data.index)

            # Calculate annual totals (kWh) using the new grid_required_hourly
            pv_annual = pv_hourly.sum()
            wind_annual = wind_hourly.sum()
            grid_annual = grid_required_hourly_series.sum() # Use grid after battery
            battery_discharge_annual = battery_discharge_hourly_series.sum() # Total energy delivered by battery

            # Total generation = PV + Wind + Grid (Battery discharge is intermediate transfer, not primary source)
            total_generation_annual = pv_annual + wind_annual + grid_annual 
            total_demand_annual = demand_hourly.sum() # Demand remains the same
            total_curtailment_annual = curtailment_hourly_series.sum() # Total curtailed energy
            
            # Estimate battery cycles (e.g., using total discharged energy)
            # Simple estimation: total discharged energy / battery capacity
            if battery_capacity_kwh > 0:
                 estimated_cycles = battery_discharge_annual / battery_capacity_kwh
            else:
                 estimated_cycles = 0

            # Calculate GWP per kWh (overall average, considering grid usage after battery)
            if total_generation_annual > 0:
                # GWP calculation now only includes PV, Wind, and final Grid contributions
                # Battery GWP could be added (lifecycle) but is omitted here for simplicity
                overall_gwp_per_kwh = (pv_annual * pv_gwp + wind_annual * wind_gwp + grid_annual * grid_gwp) / total_generation_annual
            else:
                overall_gwp_per_kwh = float('inf') # Avoid division by zero
            if verbose_print: 
                print(f"  Annual Totals (kWh): PV={pv_annual:.0f}, Wind={wind_annual:.0f}, Grid={grid_annual:.0f}, Bat Discharge={battery_discharge_annual:.0f}, Curtailment={total_curtailment_annual:.0f}")
                print(f"  Average GWP: {overall_gwp_per_kwh:.4f} kg CO2e/kWh")
                print(f"  Estimated Battery Cycles: {estimated_cycles:.1f}")

            # --- Comparison Logic: Minimize overall_gwp_per_kwh --- 
            update_best = False
            # Primary objective: Lower GWP is always better
            if overall_gwp_per_kwh < best_mix['total_gwp']:
                update_best = True
                reason = "Lower GWP/kWh"
            # Secondary objective: If GWP is the same, prefer lower grid usage (optional tie-breaker)
            elif np.isclose(overall_gwp_per_kwh, best_mix['total_gwp'], rtol=1e-5) and grid_annual < best_mix['grid_annual_total']:
                 update_best = True
                 reason = "Same GWP/kWh, lower grid usage"

            if update_best:
                if verbose_print: 
                    print(f"  *** New Best Mix Found! Reason: {reason}. ***")
                    print(f"      (Previous GWP: {best_mix['total_gwp']:.4f}, Grid: {best_mix['grid_annual_total']:.0f} kWh) -> ")
                    print(f"      (New GWP:      {overall_gwp_per_kwh:.4f}, Grid: {grid_annual:.0f} kWh)")
                      
                best_mix['pv_capacity'] = pv_cap
                best_mix['wind_capacity'] = wind_cap
                best_mix['total_gwp'] = overall_gwp_per_kwh # Store the primary objective value
                best_mix['grid_annual_total'] = grid_annual # Store grid usage for tie-breaking and info
                best_mix['land_used'] = total_land
                best_mix['pv_land'] = pv_land
                best_mix['wind_land'] = wind_land
                best_mix['pv_annual_total'] = pv_annual
                best_mix['wind_annual_total'] = wind_annual
                # Grid annual total already updated
                best_mix['total_annual_generation'] = total_generation_annual
                
                # Store hourly profiles for the best mix found so far
                best_mix['pv_hourly'] = pv_hourly.copy()
                best_mix['wind_hourly'] = wind_hourly.copy()
                best_mix['grid_hourly'] = grid_required_hourly_series.copy()
                best_mix['demand_hourly'] = demand_hourly.copy()
                best_mix['battery_soc_hourly'] = battery_soc_hourly_series.copy()
                best_mix['battery_charge_hourly'] = battery_charge_hourly_series.copy()
                best_mix['battery_discharge_hourly'] = battery_discharge_hourly_series.copy()
                best_mix['curtailment_hourly'] = curtailment_hourly_series.copy()
                best_mix['battery_cycles'] = estimated_cycles # Float, no copy needed

    print(f"Grid search finished. Optimal combination found.")

    # --- Post-Optimisation Analysis & Output Generation ---
    if best_mix['pv_capacity'] == -1:
        print("Error: No valid solution found within constraints.")
        # Return default or indicate failure
        return {"error": "No feasible solution found"}

    print("\n--- Optimal Mix Results ---")
    print(f"Optimal PV Capacity: {best_mix['pv_capacity']:.2f} MW")
    print(f"Optimal Wind Capacity: {best_mix['wind_capacity']:.2f} MW")
    print(f"Total Land Used: {best_mix['land_used']:.2f} km² (PV: {best_mix['pv_land']:.2f} km², Wind: {best_mix['wind_land']:.2f} km²)")
    print(f"Minimum Overall GWP: {best_mix['total_gwp']:.4f} kg CO2e/kWh")
    print(f"Total Annual Generation: {best_mix['total_annual_generation']/1000:.2f} MWh")
    print(f"  PV Contribution: {best_mix['pv_annual_total']/1000:.2f} MWh")
    print(f"  Wind Contribution: {best_mix['wind_annual_total']/1000:.2f} MWh")
    print(f"  Grid Contribution: {best_mix['grid_annual_total']/1000:.2f} MWh")
    print(f"  Battery Discharged (net): {best_mix['battery_discharge_hourly'].sum()/1000:.2f} MWh")
    print(f"  Estimated Battery Cycles: {best_mix['battery_cycles']:.1f}")

    # Calculate percentage shares
    total_gen = best_mix['total_annual_generation']
    if total_gen > 0:
        best_mix['pv_share'] = (best_mix['pv_annual_total'] / total_gen) * 100
        best_mix['wind_share'] = (best_mix['wind_annual_total'] / total_gen) * 100
        best_mix['grid_share'] = (best_mix['grid_annual_total'] / total_gen) * 100
    else:
        best_mix['pv_share'] = 0
        best_mix['wind_share'] = 0
        best_mix['grid_share'] = 0
        
    print(f"Energy Mix (%): PV={best_mix['pv_share']:.1f}%, Wind={best_mix['wind_share']:.1f}%, Grid={best_mix['grid_share']:.1f}%")

    # Calculate grid deficit metrics using the stored optimal hourly data
    optimal_supply_profile = pd.DataFrame({
        'timestamp': energy_data['timestamp'],
        'pv_generation': best_mix['pv_hourly'],
        'wind_generation': best_mix['wind_hourly'],
        'renewable_total': best_mix['pv_hourly'] + best_mix['wind_hourly'],
        'demand': best_mix['demand_hourly'],
        'grid_required': best_mix['grid_hourly'],
        'temperature': energy_data['temperature'], # Include temperature for analysis
        'battery_soc': best_mix['battery_soc_hourly'] / 1000, # Convert to MWh for profile
        'battery_charge': best_mix['battery_charge_hourly'],
        'battery_discharge': best_mix['battery_discharge_hourly'],
        'curtailment': best_mix['curtailment_hourly']
    })

    grid_deficit_hours = (optimal_supply_profile['grid_required'] > 0.001).sum() # Count hours with > 0.001 kWh grid use
    total_hours = len(optimal_supply_profile)
    grid_deficit_percentage = (grid_deficit_hours / total_hours) * 100 if total_hours > 0 else 0
    max_hourly_deficit = optimal_supply_profile['grid_required'].max()

    best_mix['grid_deficit_hours'] = grid_deficit_hours
    best_mix['grid_deficit_percentage'] = grid_deficit_percentage
    best_mix['max_hourly_deficit'] = max_hourly_deficit

    print(f"Grid required for {grid_deficit_hours} hours ({grid_deficit_percentage:.1f}% of the year)")
    print(f"Maximum hourly grid requirement: {max_hourly_deficit:.2f} kWh")

    # Calculate hourly GWP for the optimal mix
    # Note: Denominator now includes only the final supply sources (PV, Wind, Grid)
    hourly_supply_sum = (optimal_supply_profile['pv_generation'] + 
                         optimal_supply_profile['wind_generation'] + 
                         optimal_supply_profile['grid_required'])
    
    optimal_supply_profile['hourly_gwp'] = (
        (optimal_supply_profile['pv_generation'] * pv_gwp) + 
        (optimal_supply_profile['wind_generation'] * wind_gwp) + 
        (optimal_supply_profile['grid_required'] * grid_gwp)
    ) / hourly_supply_sum.replace(0, np.nan) # Avoid division by zero

    
    # --- Data Saving ---
    print("Saving output data...")
    # Save the potential generation data (from input energy_data)
    # potential_data_filename = get_timestamped_filename("australian_energy_data.csv")
    # save_data_to_csv(energy_data, os.path.join(output_data_dir, "australian_energy_data.csv")) # Removed: Redundant, already saved in main()
    # print(f"Saved potential generation data to output_data/australian_energy_data.csv")

    # Save the optimal supply profile (pass only filename)
    optimal_profile_filename = get_timestamped_filename("optimal_supply_profile.csv")
    # save_data_to_csv(optimal_supply_profile, os.path.join(output_data_dir, "optimal_supply_profile.csv"))
    save_data_to_csv(optimal_supply_profile, optimal_profile_filename) # Pass only filename
    print(f"Saved optimal supply profile to output_data/{optimal_profile_filename}")

    # --- Plotting ---
    print("Generating plots...")
    
    # Define consistent colors
    pv_color = 'gold'
    wind_color = 'deepskyblue'
    grid_color = 'dimgray'
    demand_color = 'red'
    temp_color = 'lightcoral'

    # Plot 1: Generation Profiles (Potential per MW and Temperature)
    try:
        fig_gen, ax1 = plt.subplots(figsize=(15, 6))

        # Plot potential generation per MW on primary y-axis
        ax1.plot(energy_data['timestamp'], energy_data['pv_potential_per_mw'], label='Potential PV Gen (per MW)', color=pv_color, alpha=0.7)
        ax1.plot(energy_data['timestamp'], energy_data['wind_potential_per_mw'], label='Potential Wind Gen (per MW)', color=wind_color, alpha=0.7)
        ax1.set_xlabel('Date')
        ax1.set_ylabel('Potential Generation (kWh per MW)', color='black')
        ax1.tick_params(axis='y', labelcolor='black')
        ax1.legend(loc='upper left')
        ax1.grid(True, linestyle='--', alpha=0.5)

        # Create secondary y-axis for temperature
        ax2 = ax1.twinx()
        ax2.plot(energy_data['timestamp'], energy_data['temperature'], label='Temperature (°C)', color=temp_color, linestyle=':')
        ax2.set_ylabel('Temperature (°C)', color=temp_color)
        ax2.tick_params(axis='y', labelcolor=temp_color)
        ax2.legend(loc='upper right')

        plt.title('Potential Renewable Generation per MW and Temperature')
        plt.tight_layout()
        gen_profile_filename = get_timestamped_filename("generation_profiles.png")
        plt.savefig(os.path.join(figures_dir, "generation_profiles.png"), bbox_inches='tight')
        print(f"Saved generation profiles plot to figures/generation_profiles.png")
        plt.close()
    except Exception as e:
        print(f"Error generating generation profiles plot: {e}")

    # Plot 2: Monthly Energy Mix (Optimal Scenario)
    try:
        # Aggregate optimal supply profile by month
        optimal_supply_profile['month'] = optimal_supply_profile['timestamp'].dt.month
        monthly_mix = optimal_supply_profile.groupby('month')[[ 'pv_generation', 'wind_generation', 'grid_required', 'demand']].sum() / 1000 # Convert to MWh
        
        plt.figure(figsize=(12, 7))
        # Stacked bar chart for generation sources
        plt.bar(monthly_mix.index, monthly_mix['pv_generation'], label='PV Generation', color=pv_color)
        plt.bar(monthly_mix.index, monthly_mix['wind_generation'], bottom=monthly_mix['pv_generation'], label='Wind Generation', color=wind_color)
        plt.bar(monthly_mix.index, monthly_mix['grid_required'], bottom=monthly_mix['pv_generation'] + monthly_mix['wind_generation'], label='Grid Required', color=grid_color)
        
        # Line plot for demand
        plt.plot(monthly_mix.index, monthly_mix['demand'], label='Demand', color=demand_color, marker='o', linestyle='--')
        
        plt.xlabel('Month')
        plt.ylabel('Energy (MWh)')
        plt.title('Monthly Energy Mix vs. Demand (Optimal Scenario)')
        plt.xticks(monthly_mix.index)
        plt.legend()
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout()
        monthly_mix_filename = get_timestamped_filename("monthly_energy_mix.png")
        plt.savefig(os.path.join(figures_dir, "monthly_energy_mix.png"), bbox_inches='tight')
        print(f"Saved monthly energy mix plot to figures/monthly_energy_mix.png")
        plt.close()
    except Exception as e:
        print(f"Error generating monthly energy mix plot: {e}")

    # Plot 3: Optimal Energy Mix (Pie Chart) - Reduce Size
    try:
        plt.figure(figsize=(6, 6)) # Reduced size 
        pv_annual_total = best_mix['pv_annual_total']
        wind_annual_total = best_mix['wind_annual_total']
        grid_annual_total = best_mix['grid_annual_total']
        total_annual_generation = best_mix['total_annual_generation']
        
        if total_annual_generation > 0:
             # Use calculated shares if generation exists
            labels = ['PV Generation', 'Wind Generation', 'Grid Required']
            sizes = [pv_annual_total, wind_annual_total, grid_annual_total]
            colors_pie = [pv_color, wind_color, grid_color] # Define colors list
            
            # Filter out zero-value slices for clarity
            non_zero_elements = [(labels[i], sizes[i], colors_pie[i]) for i, size in enumerate(sizes) if size > 0.001 * total_annual_generation] # Avoid tiny slices
            
            if non_zero_elements:
                 non_zero_labels, non_zero_sizes, non_zero_colors = zip(*non_zero_elements)
                 plt.pie(non_zero_sizes, labels=non_zero_labels, autopct='%1.1f%%', startangle=90, 
                         colors=non_zero_colors) # Use filtered colors
                 plt.title(f'Optimal Energy Mix Contribution\n(Total: {total_annual_generation:,.0f} kWh)')
            else:
                 # Handle case where all generation is near zero
                 plt.text(0.5, 0.5, 'No significant generation', horizontalalignment='center', verticalalignment='center')
                 plt.title('Optimal Energy Mix Contribution')

        else:
            # Handle case with zero total generation
             plt.text(0.5, 0.5, 'Total generation is zero', horizontalalignment='center', verticalalignment='center')
             plt.title('Optimal Energy Mix Contribution')
        
        plt.axis('equal') # Ensure pie is drawn as a circle
        plt.tight_layout()
        pie_chart_filename = get_timestamped_filename("optimal_energy_mix.png")
        plt.savefig(os.path.join(figures_dir, "optimal_energy_mix.png"), bbox_inches='tight')
        print(f"Saved optimal energy mix pie chart to figures/optimal_energy_mix.png")
        plt.close()
    except Exception as e:
        print(f"Error generating optimal energy mix pie chart: {e}")
        
    # Create temperature bins and categories for analysis
    bins = [-np.inf, 0, 10, 20, 30, np.inf]
    labels = ['<0°C', '0-10°C', '10-20°C', '20-30°C', '>30°C']
    optimal_supply_profile['temp_bin'] = pd.cut(optimal_supply_profile['temperature'], bins=bins, labels=labels, right=False)
    optimal_supply_profile['temp_category'] = optimal_supply_profile['temp_bin'].astype(str) # Use string category for grouping

    # Plot 4: Temperature Analysis - Make Bars Horizontal
    try:
        # Ensure 'temperature' and related columns exist
        if 'temperature' in optimal_supply_profile.columns and 'temp_category' in optimal_supply_profile.columns:
            fig_temp, axes_temp = plt.subplots(3, 1, figsize=(10, 12), sharex=False) # Keep original figure size for multiple plots

            # Subplot 1: Temperature Distribution (Histogram remains vertical)
            if not optimal_supply_profile['temperature'].isnull().all():
                axes_temp[0].hist(optimal_supply_profile['temperature'].dropna(), bins=30, color='skyblue', edgecolor='black')
                axes_temp[0].set_title('Hourly Temperature Distribution')
                axes_temp[0].set_xlabel('Temperature (°C)')
                axes_temp[0].set_ylabel('Number of Hours')
                axes_temp[0].grid(axis='y', linestyle='--', alpha=0.7)
            else:
                axes_temp[0].text(0.5, 0.5, 'No temperature data', horizontalalignment='center', verticalalignment='center')
                axes_temp[0].set_title('Hourly Temperature Distribution')

            # Subplot 2: Mean Demand by Temperature Category (Horizontal Bar)
            if 'demand' in optimal_supply_profile.columns:
                 # Calculate mean demand, ensuring numeric type and handling potential NaNs/Infs
                 demand_by_temp = optimal_supply_profile.groupby('temp_category')['demand'].mean().replace([np.inf, -np.inf], np.nan).dropna()
                 # Reorder based on the defined labels for logical presentation
                 demand_by_temp = demand_by_temp.reindex(labels).dropna()
                 if not demand_by_temp.empty:
                     axes_temp[1].barh(demand_by_temp.index, demand_by_temp.values, color='lightcoral') # Use barh
                     axes_temp[1].set_title('Mean Hourly Demand by Temperature Category')
                     axes_temp[1].set_xlabel('Average Demand (kWh)') # Swapped label
                     axes_temp[1].set_ylabel('Temperature Category') # Swapped label
                     axes_temp[1].grid(axis='x', linestyle='--', alpha=0.7) # Grid on value axis
                 else:
                    axes_temp[1].text(0.5, 0.5, 'No demand data or categories', horizontalalignment='center', verticalalignment='center')
                    axes_temp[1].set_title('Mean Hourly Demand by Temperature Category')

            # Subplot 3: Mean Grid Use by Temperature Category (Horizontal Bar)
            if 'grid_required' in optimal_supply_profile.columns:
                 # Calculate mean grid use, ensuring numeric type and handling potential NaNs/Infs
                 grid_by_temp = optimal_supply_profile.groupby('temp_category')['grid_required'].mean().replace([np.inf, -np.inf], np.nan).dropna()
                 # Reorder based on the defined labels
                 grid_by_temp = grid_by_temp.reindex(labels).dropna()
                 if not grid_by_temp.empty:
                     axes_temp[2].barh(grid_by_temp.index, grid_by_temp.values, color=grid_color) # Use barh and consistent color
                     axes_temp[2].set_title('Mean Hourly Grid Requirement by Temperature Category')
                     axes_temp[2].set_xlabel('Average Grid Required (kWh)') # Swapped label
                     axes_temp[2].set_ylabel('Temperature Category') # Swapped label
                     axes_temp[2].grid(axis='x', linestyle='--', alpha=0.7) # Grid on value axis
                 else:
                    axes_temp[2].text(0.5, 0.5, 'No grid data or categories', horizontalalignment='center', verticalalignment='center')
                    axes_temp[2].set_title('Mean Hourly Grid Requirement by Temperature Category')


            plt.tight_layout(rect=[0, 0.03, 1, 0.95]) # Adjust layout
            temp_analysis_filename = get_timestamped_filename("temperature_analysis.png")
            plt.savefig(os.path.join(figures_dir, "temperature_analysis.png"), bbox_inches='tight')
            print(f"Saved temperature analysis plot to figures/temperature_analysis.png")
            plt.close()
        else:
             print("Skipping temperature analysis plot due to missing columns.")
             
    except Exception as e:
        print(f"Error generating temperature analysis plot: {e}")


    # Plot 5: GWP by Temperature Range - Horizontal Ticks
    try:
        # Ensure necessary columns exist
        if 'hourly_gwp' in optimal_supply_profile.columns and 'temp_bin' in optimal_supply_profile.columns:
            # Calculate mean GWP per bin, handling potential NaNs/Infs
             gwp_by_temp = optimal_supply_profile.groupby('temp_bin')['hourly_gwp'].mean().replace([np.inf, -np.inf], np.nan).dropna()
             # Reorder based on defined labels
             gwp_by_temp = gwp_by_temp.reindex(labels).dropna()
             
             if not gwp_by_temp.empty:
                plt.figure(figsize=(10, 6))
                # Use the ordered index for plotting
                bars = plt.barh(gwp_by_temp.index, gwp_by_temp.values, color='purple')
                plt.ylabel('Temperature Range (°C)')
                plt.xlabel('Average GWP (kg CO2e/kWh)')
                plt.title('Average GWP by Temperature Range')
                plt.grid(axis='x', linestyle='--', alpha=0.7)
                plt.tight_layout()
                gwp_temp_filename = get_timestamped_filename("gwp_by_temperature.png")
                plt.savefig(os.path.join(figures_dir, "gwp_by_temperature.png"), bbox_inches='tight')
                print(f"Saved GWP by temperature plot to figures/gwp_by_temperature.png")
                plt.close()
             else:
                print("Skipping GWP by temperature plot: No valid GWP data per temperature bin.")

        else:
             print("Skipping GWP by temperature plot due to missing columns.")

    except Exception as e:
        print(f"Error generating GWP by temperature plot: {e}")


    # Plot 6: Monthly First Week Hourly Profiles
    try:
        print("Generating weekly profile plots for each month...")
        # Get unique months present in the data
        months = sorted(optimal_supply_profile['timestamp'].dt.month.unique())
        
        # Dictionary to map month number to name
        month_names = {
            1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May', 6: 'June',
            7: 'July', 8: 'August', 9: 'September', 10: 'October', 11: 'November', 12: 'December'
        }
        
        for month in months:
            # Filter data for the first 7 days of the month
            start_of_month = optimal_supply_profile['timestamp'].min().replace(day=1, month=month)
            end_of_week = start_of_month + timedelta(days=7)
            weekly_data = optimal_supply_profile[
                (optimal_supply_profile['timestamp'] >= start_of_month) & 
                (optimal_supply_profile['timestamp'] < end_of_week)
            ]
            
            if weekly_data.empty:
                print(f"  Skipping month {month:02d}: No data for the first week.")
                continue

            plt.figure(figsize=(15, 7))
            
            # Stacked area plot for generation components
            plt.stackplot(weekly_data['timestamp'], 
                          weekly_data['pv_generation'], 
                          weekly_data['wind_generation'], 
                          weekly_data['grid_required'], 
                          labels=['PV', 'Wind', 'Grid'], 
                          colors=[pv_color, wind_color, grid_color],
                          alpha=0.7)
            
            # Line plot for demand
            plt.plot(weekly_data['timestamp'], weekly_data['demand'], label='Demand', color=demand_color, linestyle='--', linewidth=2)
            
            plt.xlabel('Date and Time')
            plt.ylabel('Energy (kWh)')
            # Use month name in the title
            month_name = month_names.get(month, f'Month {month:02d}') # Fallback if month number is unexpected
            plt.title(f'Hourly Supply vs. Demand - First Week of {month_name}')
            plt.legend(loc='upper right')
            plt.grid(True, linestyle='--', alpha=0.5)
            plt.xticks(rotation=45)
            plt.tight_layout()
            
            # Save the plot
            week_plot_filename = get_timestamped_filename(f"hourly_supply_profile_month_{month:02d}.png")
            plt.savefig(os.path.join(figures_dir, 'monthly_first_week_profiles', f"hourly_supply_profile_month_{month:02d}.png"), bbox_inches='tight')
            print(f"  Saved weekly profile for month {month:02d} to figures/monthly_first_week_profiles/")
            plt.close()
            
    except Exception as e:
        print(f"Error generating weekly profile plots: {e}")

    print("Plot generation complete.")
    
    # Clean up the best_mix dictionary before returning
    best_mix.pop('pv_hourly', None)
    best_mix.pop('wind_hourly', None)
    best_mix.pop('grid_hourly', None)
    best_mix.pop('demand_hourly', None)
    best_mix.pop('battery_soc_hourly', None)
    best_mix.pop('battery_charge_hourly', None)
    best_mix.pop('battery_discharge_hourly', None)
    best_mix.pop('curtailment_hourly', None)
    
    return best_mix

def main():
    # Debug print
    print("Starting optimization script...")

    # --- Apply Publication Formatting Settings --- 
    plt.rcParams.update({
        "font.size": 12,          # Base font size
        "font.family": "serif",   # Or "sans-serif"
        "font.serif": ["Times New Roman"], # Specific serif font
        # "font.sans-serif": ["Arial"],    # Specific sans-serif font
        "axes.labelsize": 14,     # Fontsize of the x and y labels
        "axes.titlesize": 16,     # Fontsize of the axes title
        "xtick.labelsize": 12,    # Fontsize of the tick labels
        "ytick.labelsize": 12,    # Fontsize of the tick labels
        "legend.fontsize": 12,    # Legend fontsize
        "figure.titlesize": 18,   # Fontsize of the figure title
        "lines.linewidth": 2,     # Line width
        "lines.markersize": 6,    # Marker size
        "figure.dpi": 300,        # Figure resolution
        "savefig.dpi": 300,       # Resolution for saved figures
        "savefig.format": 'png',  # Default save format (use png for compatibility, pdf also good)
        "savefig.bbox": 'tight',  # Tight bounding box
        "axes.spines.top": False, # Remove top spine
        "axes.spines.right": False # Remove right spine
    })
    print("Applied publication-ready formatting settings.")

    # --- Clean up / Archiving removed (Strategy 1: Fixed Filenames) ---
    
    # Ensure base directories exist (still needed)
    figures_dir = 'figures'
    data_dir = 'output_data'
    monthly_profiles_dir = os.path.join(figures_dir, 'monthly_first_week_profiles')
    os.makedirs(figures_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(monthly_profiles_dir, exist_ok=True)

    # Enable quick test mode to speed up execution
    quick_test = False  # Set to False for full year analysis
    print(f"Quick test mode: {quick_test}")
    
    # Time period
    if quick_test:
        # Use a shorter time period for quick testing
        start_date = '2023-01-01'
        end_date = '2023-01-07'  # Just one week for quick testing
    else:
        start_date = '2023-01-01' # Full year 2023
        end_date = '2023-12-31'  # Full year 2023
    
    print(f"Analysis period: {start_date} to {end_date}")
    
    # --- Load Location Configuration from Environment Variables ---
    print("\nLoading location configuration from environment variables...")
    
    # Primary Location (Defaults are placeholders, replace with env vars)
    default_primary_location_name = "Primary Location"
    default_primary_latitude = "-28.1083" # Default placeholder Latitude
    default_primary_longitude = "140.2028" # Default placeholder Longitude
    
    primary_location_name = os.getenv("PRIMARY_LOCATION_NAME", default_primary_location_name)
    try:
        primary_latitude = float(os.getenv("PRIMARY_LATITUDE", default_primary_latitude))
    except ValueError:
        print(f"Warning: Invalid PRIMARY_LATITUDE environment variable. Using default placeholder")
        primary_latitude = float(default_primary_latitude)
    try:
        primary_longitude = float(os.getenv("PRIMARY_LONGITUDE", default_primary_longitude))
    except ValueError:
        print(f"Warning: Invalid PRIMARY_LONGITUDE environment variable. Using default placeholder")
        primary_longitude = float(default_primary_longitude)

    print(f"  Primary Location: '{primary_location_name}' ({primary_latitude}, {primary_longitude})")

    # Fallback Location (Defaults are placeholders)
    default_fallback_location_name = "Fallback Location"
    default_fallback_latitude = "-29.0139" # Default placeholder Fallback Latitude
    default_fallback_longitude = "134.7544" # Default placeholder Fallback Longitude
    
    fallback_location_name = os.getenv("FALLBACK_LOCATION_NAME", default_fallback_location_name)
    try:
        fallback_latitude = float(os.getenv("FALLBACK_LATITUDE", default_fallback_latitude))
    except ValueError:
        print(f"Warning: Invalid FALLBACK_LATITUDE environment variable. Using default placeholder")
        fallback_latitude = float(default_fallback_latitude)
    try:
        fallback_longitude = float(os.getenv("FALLBACK_LONGITUDE", default_fallback_longitude))
    except ValueError:
        print(f"Warning: Invalid FALLBACK_LONGITUDE environment variable. Using default placeholder")
        fallback_longitude = float(default_fallback_longitude)

    print(f"  Fallback Location: '{fallback_location_name}' ({fallback_latitude}, {fallback_longitude})")
    # --- End Location Configuration ---

    # --- Data Fetching/Generation ---
    use_synthetic = False
    location_name_used = "Unknown" # Track which location data was actually used
    energy_data = None  # Initialize energy_data variable
    real_data_flag = False
    
    # Try to fetch real data for the primary location first
    try:
        print(f"\nAttempting to fetch NASA POWER data for {primary_location_name}...")
        energy_data, real_data_flag = generate_location_data(primary_location_name, primary_latitude, primary_longitude, start_date, end_date)
        if real_data_flag:
            location_name_used = primary_location_name
        else:
            print(f"Failed to get real data for {primary_location_name}.")
            energy_data = None # Ensure energy_data is None if fetch failed
    except Exception as e:
        print(f"\nError fetching or processing data for {primary_location_name}: {e}")
        traceback.print_exc() # Print detailed error
        energy_data = None # Ensure energy_data is None on error
        
    # If primary location failed, try fallback location
    if energy_data is None or energy_data.empty:
        print(f"\nPrimary location data failed. Attempting fallback location: {fallback_location_name}...")
        try:
            energy_data, real_data_flag = generate_location_data(fallback_location_name, fallback_latitude, fallback_longitude, start_date, end_date)
            if real_data_flag:
                 location_name_used = fallback_location_name
            else:
                print(f"Failed to get real data for {fallback_location_name}.")
                energy_data = None
        except Exception as e:
            print(f"\nError fetching or processing data for {fallback_location_name}: {e}")
            traceback.print_exc() # Print detailed error
            energy_data = None

    # If both real data attempts fail, fall back to synthetic data using primary location coordinates
    if energy_data is None or energy_data.empty:
        print("\nBoth real data fetches failed. Falling back to synthetic data...")
        try:
            # Generate synthetic data using the primary coordinates
            energy_data = generate_synthetic_data(start_date, end_date, primary_latitude, primary_longitude)
            # Add location column manually for synthetic data
            # Use a generic reference for the location name in the synthetic data identifier
            energy_data['location'] = f"Synthetic data for {primary_location_name} coordinates" 
            location_name_used = f"Synthetic ({primary_location_name} coords)"
            use_synthetic = True
        except Exception as e:
            print(f"\nError generating synthetic data: {e}")
            traceback.print_exc()
            # Handle catastrophic failure - no data at all
            print("CRITICAL ERROR: Could not obtain or generate any energy data. Exiting.")
            return # Exit script

    print(f"\nData source used for analysis: {location_name_used}{' (synthetic)' if use_synthetic else ' (real NASA POWER)'}")
    
    # --- Execute main logic ONLY if data is valid ---
    if energy_data is not None and not energy_data.empty:
        # --- Add check for actual data range ---
        actual_start = energy_data['timestamp'].min().strftime('%Y-%m-%d')
        actual_end = energy_data['timestamp'].max().strftime('%Y-%m-%d')
        actual_records = len(energy_data)
        print(f"Data contains {actual_records} hourly records from {actual_start} to {actual_end}")
        
        # Save the data to a CSV file
        save_data_to_csv(energy_data, "australian_energy_data_potentials.csv")
        print("Saved energy data to output_data/australian_energy_data_potentials.csv")

        # --- Get User Input for Annual Demand ---
        while True:
            try:
                user_demand_mwh = float(input("Enter the target annual energy demand in MWh (e.g., 40): "))
                if user_demand_mwh > 0:
                    break
                else:
                    print("Demand must be a positive number.")
            except ValueError:
                print("Invalid input. Please enter a number.")

        print(f"Using target annual demand: {user_demand_mwh} MWh")

        # --- Calculate Dynamic Capacity Search Ranges ---
        print("\nCalculating dynamic search ranges for PV and Wind capacities...")
        
        # Constants
        pv_land_per_mw = 0.02
        wind_land_per_mw = 0.26
        available_land_km2 = 1000 # Increased land area
        min_search_range_mw = 50  # Minimum capacity (MW) to search up to
        demand_headroom_factor = 1.5 # Multiplier for estimated capacity needed
        num_capacity_steps = 30 # Number of steps for linspace

        # Calculate average capacity factors from site data
        if 'pv_potential_per_mw' in energy_data.columns and 'wind_potential_per_mw' in energy_data.columns:
            avg_pv_cf = energy_data['pv_potential_per_mw'].mean()
            avg_wind_cf = energy_data['wind_potential_per_mw'].mean()
            # Use a small floor value to avoid division by zero for sites with no potential
            avg_pv_cf = max(avg_pv_cf, 0.01) 
            avg_wind_cf = max(avg_wind_cf, 0.01)
            print(f"  Average site potential (Capacity Factor estimate): PV={avg_pv_cf:.3f}, Wind={avg_wind_cf:.3f}")

            # Calculate max capacities based purely on land limit
            max_pv_from_land = available_land_km2 / pv_land_per_mw
            max_wind_from_land = available_land_km2 / wind_land_per_mw
            print(f"  Max capacity purely from land: PV={max_pv_from_land:.1f} MW, Wind={max_wind_from_land:.1f} MW")

            # Calculate average hourly demand in kW
            avg_hourly_demand_kw = (user_demand_mwh * 1000) / len(energy_data)

            # Estimate capacities needed if each tech met the entire demand
            estimated_pv_cap_for_demand = avg_hourly_demand_kw / avg_pv_cf
            estimated_wind_cap_for_demand = avg_hourly_demand_kw / avg_wind_cf
            print(f"  Estimated capacity to meet demand individually: PV={estimated_pv_cap_for_demand:.1f} MW, Wind={estimated_wind_cap_for_demand:.1f} MW")

            # Calculate the dynamic upper bound for the search range
            pv_search_upper_bound = max(min_search_range_mw, min(max_pv_from_land, demand_headroom_factor * estimated_pv_cap_for_demand))
            wind_search_upper_bound = max(min_search_range_mw, min(max_wind_from_land, demand_headroom_factor * estimated_wind_cap_for_demand))
            
            print(f"  Using dynamic search upper bounds: PV={pv_search_upper_bound:.1f} MW, Wind={wind_search_upper_bound:.1f} MW")

            # Create the dynamic capacity arrays
            pv_capacities_dynamic = np.linspace(0, pv_search_upper_bound, num_capacity_steps)
            wind_capacities_dynamic = np.linspace(0, wind_search_upper_bound, num_capacity_steps)
        else:
            print("Error: Required columns 'pv_potential_per_mw' or 'wind_potential_per_mw' not found in data.")
            print("Using default capacity search ranges.")
            pv_capacities_dynamic = np.linspace(0, 500, num_capacity_steps)
            wind_capacities_dynamic = np.linspace(0, 200, num_capacity_steps)

        # --- Run Optimization First ---
        print(f"\nOptimizing energy mix for {user_demand_mwh} MWh annual demand with {available_land_km2} km² available land:")
        print("-" * 80)

        # Run the land use optimization using user input and dynamic ranges
        optimal_mix = optimise_land_use(
            energy_data,
            annual_demand_mwh=user_demand_mwh, # Use user input
            available_land_km2=available_land_km2,
            pv_land_per_mw=pv_land_per_mw,
            wind_land_per_mw=wind_land_per_mw,
            # --- Pass updated GWP factors ---
            pv_gwp=0.07, 
            wind_gwp=0.011, 
            grid_gwp=0.6,
            # --- Use dynamic capacity search ranges ---
            pv_capacities=pv_capacities_dynamic, 
            wind_capacities=wind_capacities_dynamic 
        )

        # Check if optimization was successful before proceeding
        if optimal_mix.get("error"):
            print(f"Optimization failed: {optimal_mix['error']}")
            # Optionally, you might want to return here as well, or handle the error differently
        elif optimal_mix['pv_capacity'] < 0 or optimal_mix['wind_capacity'] < 0:
            print("Optimization did not find a valid positive capacity mix.")
            # Optionally, handle this case
        else:
            # --- Plotting for the Optimal System ---
            print("\nGenerating plot for the optimal system generation profiles...")
            
            # Calculate optimal generation based on returned capacities
            optimal_pv_gen = energy_data['pv_potential_per_mw'] * optimal_mix['pv_capacity']
            optimal_wind_gen = energy_data['wind_potential_per_mw'] * optimal_mix['wind_capacity']
            
            plt.figure(figsize=(15, 10))
            
            plt.subplot(3, 1, 1)
            plt.plot(energy_data['timestamp'], optimal_pv_gen)
            plt.title(f"Optimal PV Generation ({optimal_mix['pv_capacity']:.2f} MW)")
            plt.ylabel('kWh') # Use kWh
            
            plt.subplot(3, 1, 2)
            plt.plot(energy_data['timestamp'], optimal_wind_gen)
            plt.title(f"Optimal Wind Generation ({optimal_mix['wind_capacity']:.2f} MW)")
            plt.ylabel('kWh') # Use kWh
            
            plt.subplot(3, 1, 3)
            plt.plot(energy_data['timestamp'], energy_data['temperature'])
            plt.title('Temperature')
            plt.ylabel('°C')
            plt.axhline(y=30, color='red', linestyle='--', label='30°C threshold')
            plt.legend()
            
            plt.tight_layout()
            
            # Save the optimal system plot
            optimal_plot_filename = get_timestamped_filename('optimal_system_profiles.png') # New filename
            plt.savefig(os.path.join('figures', optimal_plot_filename))
            plt.close()
            print(f"Saved optimal system profiles plot to figures/{optimal_plot_filename}")
            
            # --- Print Optimization Results --- 
            print("\n" + "="*80)
            print("OPTIMAL ENERGY MIX SOLUTION")
            print("="*80)
            print(f"Optimal PV capacity: {optimal_mix['pv_capacity']:.2f} MW using {optimal_mix['pv_land']:.2f} km²")
            print(f"Optimal wind capacity: {optimal_mix['wind_capacity']:.2f} MW using {optimal_mix['wind_land']:.2f} km²")
            print(f"Total land usage: {optimal_mix['land_used']:.2f} km² of {1000:.2f} km² available")
            print("\nEnergy mix:")
            print(f"PV generation: {optimal_mix['pv_annual_total']/1000:.2f} MWh/year ({optimal_mix['pv_share']:.1f}%)")
            print(f"Wind generation: {optimal_mix['wind_annual_total']/1000:.2f} MWh/year ({optimal_mix['wind_share']:.1f}%)")
            print(f"Grid usage: {optimal_mix['grid_annual_total']/1000:.2f} MWh/year ({optimal_mix['grid_share']:.1f}%)")
            print(f"Total annual generation: {optimal_mix['total_annual_generation']/1000:.2f} MWh/year")
            
            print(f"\nGlobal Warming Potential: {optimal_mix['total_gwp']:.4f} kg CO2e/kWh")
            
            print("\nStability analysis:")
            print(f"Hours with renewable generation deficit: {optimal_mix['grid_deficit_hours']} of {len(energy_data)} ({optimal_mix['grid_deficit_percentage']:.1f}%)")
            print(f"Maximum hourly deficit: {optimal_mix['max_hourly_deficit']:.2f} kWh")
            
            print("\nOutput files created:")
            print("- output_data/optimal_supply_profile.csv - Hourly generation data")
            print("- figures/generation_profiles.png - Visualizations of potential generation")
            print("- figures/monthly_energy_mix.png - Monthly energy mix chart")
            print("- figures/optimal_energy_mix_summary.png - Pie chart of energy mix")
            print("- figures/temperature_analysis.png - Temperature impact analysis")
            print("- figures/gwp_by_temperature.png - GWP vs temperature analysis")
            print("- figures/optimal_system_profiles.png - Optimal system generation profiles")
            print("- figures/monthly_first_week_profiles/ - Hourly profiles for first week of each month")

            # Create visualization of the optimal mix
            labels = ['PV', 'Wind', 'Grid']
            sizes = [optimal_mix['pv_share'], optimal_mix['wind_share'], optimal_mix['grid_share']]
            colours = ['gold', 'deepskyblue', 'dimgray']
            explode = (0.1, 0.1, 0)
            
            plt.figure(figsize=(10, 7))
            plt.pie(sizes, explode=explode, labels=labels, colors=colours, autopct='%1.1f%%', startangle=140)
            plt.axis('equal')
            plt.title(f"Optimal Energy Mix for {user_demand_mwh} MWh Annual Demand\nTotal GWP: {optimal_mix['total_gwp']:.4f} kg CO2e/kWh")
            
            # Save with fixed filename consistent with optimise_land_use
            # timestamped_filename = get_timestamped_filename('optimal_energy_mix.png') 
            plt.savefig(os.path.join('figures', 'optimal_energy_mix_summary.png')) # Use fixed name
            plt.close()
            print(f"Saved optimal energy mix summary plot to figures/optimal_energy_mix_summary.png")

    else:
        print("CRITICAL ERROR: No valid energy data loaded. Cannot proceed with optimization. Exiting.")
        return # Exit script if data is not valid

def generate_location_data(location_name, latitude, longitude, start_date, end_date):
    """
    Generate or fetch energy data for a specific location
    """
    print(f"\n=== Attempting to fetch data for {location_name} ({latitude}, {longitude}) ===")
    print(f"Time period: {start_date} to {end_date}")
    
    # First try to get real data from NASA POWER
    try:
        data = fetch_nasa_power_data(latitude, longitude, start_date, end_date)
        
        if data is not None and not data.empty:
            print(f"Successfully obtained NASA POWER data for the site")
            
            # Add PV and wind generation based on the real weather data
            data = process_real_data(data)
            
            # Add location column
            data['location'] = location_name
            
            return data, True  # Return data and flag indicating real data
        else:
            print(f"NASA POWER data fetch returned empty dataset")
    except Exception as e:
        print(f"Error processing NASA POWER data: {e}")
        traceback.print_exc()
    
    print(f"Unable to fetch real data for the location, returning None")
    return None, False

# --- Restored Functions --- 

def get_timestamped_filename(filename):
    """
    Returns the original filename without adding a timestamp.
    (Strategy 1: Fixed Filenames)
    """
    # timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    # name, ext = os.path.splitext(filename)
    # return f"{name}_{timestamp}{ext}"
    return filename # Return the original filename

def save_data_to_csv(data, filename):
    """
    Save the data to a CSV file in the output_data directory
    """
    # Ensure the output_data directory exists
    output_dir = 'output_data' # Define base directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Get the filename (potentially timestamped, but currently not)
    processed_filename = get_timestamped_filename(filename)
    
    # Create the full path
    filepath = os.path.join(output_dir, processed_filename)
    
    # Save the data
    data.to_csv(filepath, index=False)
    print(f"Data saved to {filepath}")
    
    # Print some basic statistics (commented out as columns may not exist)
    # print("\nData Statistics:")
    # print(f"Total records: {len(data)}")
    # if 'timestamp' in data.columns:
    #      print(f"Time period: {data['timestamp'].min()} to {data['timestamp'].max()}")
    # # print(f"Average PV generation: {data['pv_generation'].mean():.2f} kWh") # Column removed
    # # print(f"Average wind generation: {data['wind_generation'].mean():.2f} kWh") # Column removed
    # # print(f"Average total generation: {data['total_generation'].mean():.2f} kWh") # Column removed

# --- End Restored Functions ---

if __name__ == "__main__":
    main() 


