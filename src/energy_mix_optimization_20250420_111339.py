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
    Process real weather data to calculate generation
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
    
    # Initialize PV generation
    weather_data['pv_generation'] = (
        weather_data['solar_irradiation'] * 
        pv_efficiency * 
        pv_capacity * 
        temp_effect / 1000  # Convert to kWh
    )

    # Ensure generation is non-negative after temperature correction
    weather_data['pv_generation'] = weather_data['pv_generation'].clip(lower=0)
    
    # Ensure zero generation at night
    weather_data.loc[night_mask, 'pv_generation'] = 0
    
    # Calculate wind generation (kWh)
    # Assuming wind turbine with power curve
    cut_in_speed = 3  # m/s
    rated_speed = 12  # m/s
    cut_out_speed = 25  # m/s
    
    def wind_power_curve(speed):
        if speed < cut_in_speed:
            return 0
        elif speed > cut_out_speed:
            return 0
        elif speed >= rated_speed:
            return wind_capacity
        else:
            # Correct cubic relationship between wind speed and power
            # The correct formula applies the cube to just the wind speed, not to the entire ratio
            normalized_speed = (speed - cut_in_speed) / (rated_speed - cut_in_speed)
            return wind_capacity * normalized_speed ** 3
    
    weather_data['wind_generation'] = weather_data['wind_speed'].apply(wind_power_curve)
    
    # Add additional columns
    weather_data['total_generation'] = weather_data['pv_generation'] + weather_data['wind_generation']
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

def get_timestamped_filename(filename):
    """
    Add a timestamp to a filename
    
    Parameters:
    -----------
    filename : str
        Original filename
    
    Returns:
    --------
    str
        Filename with timestamp inserted before the extension
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    name, ext = os.path.splitext(filename)
    return f"{name}_{timestamp}{ext}"

def save_data_to_csv(data, filename):
    """
    Save the data to a CSV file in the output_data directory
    """
    # Ensure the output_data directory exists
    os.makedirs('output_data', exist_ok=True)
    
    # Create timestamped filename
    timestamped_filename = get_timestamped_filename(filename)
    
    # Save the data
    filepath = os.path.join('output_data', timestamped_filename)
    data.to_csv(filepath, index=False)
    print(f"Data saved to {filepath}")
    
    # Print some basic statistics
    print("\nData Statistics:")
    print(f"Total records: {len(data)}")
    print(f"Time period: {data['timestamp'].min()} to {data['timestamp'].max()}")
    print(f"Average PV generation: {data['pv_generation'].mean():.2f} kWh")
    print(f"Average wind generation: {data['wind_generation'].mean():.2f} kWh")
    print(f"Average total generation: {data['total_generation'].mean():.2f} kWh")

def read_energy_data(csv_file):
    """
    Read and process the energy data from CSV file
    Expected columns: timestamp, pv_generation, wind_generation, grid_emission_factor
    """
    df = pd.read_csv(csv_file)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

def calculate_gwp(energy_mix, emission_factors):
    """
    Calculate the global warming potential based on energy mix and emission factors
    """
    return np.sum(energy_mix * emission_factors)

def optimize_energy_mix(energy_data, demand, capacity_constraints, emission_factors):
    """
    Optimize the energy mix to minimize global warming potential
    """
    # Initial guess (equal distribution)
    x0 = np.array([0.2, 0.4, 0.4])  # Start with maximum PV and wind
    
    # Define constraints
    constraints = [
        {'type': 'eq', 'fun': lambda x: np.sum(x) - 1},  # Sum of fractions must be 1
        {'type': 'ineq', 'fun': lambda x: x[0]},  # Grid fraction >= 0
        {'type': 'ineq', 'fun': lambda x: x[1]},  # PV fraction >= 0
        {'type': 'ineq', 'fun': lambda x: x[2]},  # Wind fraction >= 0
        # Add minimum generation constraints
        {'type': 'ineq', 'fun': lambda x: x[0] * demand - energy_data['total_generation'].min()},  # Grid must meet minimum
        {'type': 'ineq', 'fun': lambda x: x[1] * demand - energy_data['pv_generation'].min()},    # PV must meet minimum
        {'type': 'ineq', 'fun': lambda x: x[2] * demand - energy_data['wind_generation'].min()}   # Wind must meet minimum
    ]
    
    # Define bounds based on capacity constraints
    bounds = [
        (0, capacity_constraints['grid']),
        (0, capacity_constraints['pv']),
        (0, capacity_constraints['wind'])
    ]
    
    # Objective function to minimize
    def objective(x):
        total_emissions = (
            x[0] * emission_factors['grid'] +
            x[1] * emission_factors['pv'] +
            x[2] * emission_factors['wind']
        )
        return total_emissions
    
    # Perform optimization
    result = minimize(
        objective,
        x0,
        method='SLSQP',
        bounds=bounds,
        constraints=constraints,
        options={'ftol': 1e-8, 'maxiter': 1000}
    )
    
    if not result.success:
        print(f"Warning: Optimization may not have converged. Message: {result.message}")
    
    return result.x

def plot_demand_sensitivity(energy_data, capacity_constraints, emission_factors, demand_scenarios=None):
    """
    Create a plot showing how the optimal energy mix changes with varying demand
    
    Parameters:
    -----------
    energy_data : pandas DataFrame
        The energy generation data
    capacity_constraints : dict
        Maximum capacity constraints for each source
    emission_factors : dict
        Emission factors for each source
    demand_scenarios : list, optional
        List of specific demand values to analyze (in kWh)
        If None, will create a range of values based on generation capacity
    """
    # If no specific demand scenarios provided, create a range
    if demand_scenarios is None:
        # Use a range from 20% to 120% of maximum total generation capacity
        max_capacity = (
            energy_data['pv_generation'].max() * capacity_constraints['pv'] +
            energy_data['wind_generation'].max() * capacity_constraints['wind'] +
            energy_data['total_generation'].max() * capacity_constraints['grid']
        )
        demand_values = np.linspace(0.2 * max_capacity, 1.2 * max_capacity, 50)
    else:
        demand_values = np.array(sorted(demand_scenarios))
    
    # Calculate optimal mix for each demand value
    grid_shares = []
    pv_shares = []
    wind_shares = []
    gwp_values = []
    feasible_demands = []
    
    for demand in demand_values:
        try:
            optimal_mix = optimize_energy_mix(energy_data, demand, capacity_constraints, emission_factors)
            grid_shares.append(optimal_mix[0] * 100)
            pv_shares.append(optimal_mix[1] * 100)
            wind_shares.append(optimal_mix[2] * 100)
            gwp_values.append(calculate_gwp(optimal_mix, np.array(list(emission_factors.values()))))
            feasible_demands.append(demand)
        except Exception as e:
            print(f"Warning: Could not find optimal mix for demand {demand:.1f} kWh")
            continue
    
    # Convert to numpy arrays for easier manipulation
    feasible_demands = np.array(feasible_demands)
    grid_shares = np.array(grid_shares)
    pv_shares = np.array(pv_shares)
    wind_shares = np.array(wind_shares)
    gwp_values = np.array(gwp_values)
    
    # Create the plot with two subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 12), height_ratios=[2, 1])
    
    # Plot energy mix
    ax1.plot(feasible_demands, grid_shares, label='Grid', linewidth=2, color='blue')
    ax1.plot(feasible_demands, pv_shares, label='PV', linewidth=2, color='orange', linestyle='--')
    ax1.plot(feasible_demands, wind_shares, label='Wind', linewidth=2, color='green', linestyle=':')
    
    # Add horizontal lines for capacity constraints
    ax1.axhline(y=capacity_constraints['grid']*100, color='blue', linestyle=':', alpha=0.3)
    ax1.axhline(y=capacity_constraints['pv']*100, color='orange', linestyle=':', alpha=0.3)
    ax1.axhline(y=capacity_constraints['wind']*100, color='green', linestyle=':', alpha=0.3)
    
    # If specific demand scenarios were provided, mark them on the plot
    if demand_scenarios is not None:
        for demand in demand_scenarios:
            if demand in feasible_demands:
                ax1.axvline(x=demand, color='gray', linestyle='--', alpha=0.3)
                # Find the optimal mix for this demand
                idx = np.where(feasible_demands == demand)[0][0]
                ax1.annotate(f'Demand: {demand:.0f} kWh\nGrid: {grid_shares[idx]:.1f}%\nPV: {pv_shares[idx]:.1f}%\nWind: {wind_shares[idx]:.1f}%',
                            xy=(demand, 0),
                            xytext=(10, 10),
                            textcoords='offset points',
                            bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.3))
    
    ax1.set_xlabel('Energy Demand (kWh)')
    ax1.set_ylabel('Share of Energy Mix (%)')
    ax1.set_title('Optimal Energy Mix vs. Energy Demand')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Add capacity constraint annotations
    for source, constraint in capacity_constraints.items():
        ax1.annotate(f'{source.capitalize()} Max: {constraint*100}%',
                    xy=(feasible_demands[-1], constraint*100),
                    xytext=(-100, 0),
                    textcoords='offset points',
                    color={'grid': 'blue', 'pv': 'orange', 'wind': 'green'}[source],
                    alpha=0.7)
    
    # Plot GWP
    ax2.plot(feasible_demands, gwp_values, label='GWP', color='red', linewidth=2)
    ax2.set_xlabel('Energy Demand (kWh)')
    ax2.set_ylabel('Global Warming Potential\n(kg CO2e/kWh)')
    ax2.set_title('Global Warming Potential vs. Energy Demand')
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Ensure figures directory exists
    os.makedirs('figures', exist_ok=True)
    
    # Save with timestamped filename
    timestamped_filename = get_timestamped_filename('demand_sensitivity.png')
    plt.savefig(os.path.join('figures', timestamped_filename))
    plt.close()
    
    # Return the results for further analysis if needed
    return pd.DataFrame({
        'demand': feasible_demands,
        'grid_share': grid_shares,
        'pv_share': pv_shares,
        'wind_share': wind_shares,
        'gwp': gwp_values
    })

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

def optimize_land_use(energy_data, annual_demand_mwh, available_land_km2):
    """
    Optimize PV and wind installation to minimize GWP with land constraint
    
    Parameters:
    -----------
    energy_data : pandas DataFrame
        The energy generation data
    annual_demand_mwh : float
        Annual energy demand in MWh
    available_land_km2 : float
        Available land in square kilometers
    
    Returns:
    --------
    dict
        Containing the optimal mix information
    """
    # Convert annual demand to hourly demand for the calculation
    hourly_demand_kwh = annual_demand_mwh * 1000 / 8760  # Convert MWh/year to kWh/hour
    
    # Adjust demand based on temperature if temperature data is available
    if 'temperature' in energy_data.columns:
        # Apply more realistic temperature-based demand adjustment
        adjusted_hourly_demand = calculate_temperature_adjusted_demand(hourly_demand_kwh, energy_data['temperature'].values)
        
        # Summarize temperature effects on demand
        print(f"Temperature-adjusted demand (base: {hourly_demand_kwh:.2f} kWh/hour)")
        print(f"Hours with high temperature (>30°C): {(energy_data['temperature'] > 30).sum()} ({(energy_data['temperature'] > 30).sum()/len(energy_data)*100:.1f}%)")
        print(f"Hours with low temperature (<10°C): {(energy_data['temperature'] < 10).sum()} ({(energy_data['temperature'] < 10).sum()/len(energy_data)*100:.1f}%)")
        print(f"Average demand adjustment factor: {np.mean(adjusted_hourly_demand/hourly_demand_kwh):.3f}")
        print(f"Max hourly demand: {np.max(adjusted_hourly_demand):.2f} kWh (vs base {hourly_demand_kwh:.2f} kWh)")
        print(f"Total annual demand after adjustment: {np.sum(adjusted_hourly_demand)/1000:.2f} MWh (vs base {annual_demand_mwh:.2f} MWh)")
        
        # Create temperature band analysis
        temp_bands = [(float('-inf'), 0), (0, 5), (5, 10), (10, 15), (15, 20), (20, 25), 
                      (25, 30), (30, 35), (35, 40), (40, float('inf'))]
        temp_band_hours = {}
        temp_band_demand = {}
        
        for lower, upper in temp_bands:
            if lower == float('-inf'):
                mask = energy_data['temperature'] < upper
                band_name = f"<{upper}°C"
            elif upper == float('inf'):
                mask = energy_data['temperature'] >= lower
                band_name = f"≥{lower}°C"
            else:
                mask = (energy_data['temperature'] >= lower) & (energy_data['temperature'] < upper)
                band_name = f"{lower}-{upper}°C"
            
            temp_band_hours[band_name] = mask.sum()
            if mask.sum() > 0:
                temp_band_demand[band_name] = adjusted_hourly_demand[mask].mean() / hourly_demand_kwh
        
        print("\nTemperature band analysis:")
        print(f"{'Temperature band':<15} {'Hours':<10} {'% of year':<12} {'Demand factor':<15}")
        print("-" * 55)
        for band in sorted(temp_band_hours.keys()):
            hours = temp_band_hours[band]
            pct = hours / len(energy_data) * 100
            factor = temp_band_demand.get(band, 0)
            print(f"{band:<15} {hours:<10} {pct:5.1f}%       {factor:6.3f}x")
    else:
        # If no temperature data, use constant demand
        print("No temperature data available, using constant demand profile")
        adjusted_hourly_demand = np.ones(len(energy_data)) * hourly_demand_kwh
    
    # Land use factors (approximate values)
    # PV requires ~2 ha (0.02 km²) per MW installed capacity
    # Wind requires ~40 ha (0.4 km²) per MW installed capacity, but spacing allows multiple use
    pv_land_use_km2_per_mw = 0.02
    wind_land_use_km2_per_mw = 0.4
    
    # Emission factors (kg CO2e/kWh)
    emission_factors = {
        'grid': 0.65,  # Updated grid emission factor
        'pv': 0.041,   # Typical PV emission factor
        'wind': 0.011  # Typical wind emission factor
    }
    
    # Calculate unit generation profiles (scaled to 1 MW capacity)
    pv_unit_generation = energy_data['pv_generation'] / energy_data['pv_generation'].max() if energy_data['pv_generation'].max() > 0 else 0
    wind_unit_generation = energy_data['wind_generation'] / energy_data['wind_generation'].max() if energy_data['wind_generation'].max() > 0 else 0
    
    # Calculate capacity factors
    pv_capacity_factor = pv_unit_generation.mean()
    wind_capacity_factor = wind_unit_generation.mean()
    
    print(f"PV capacity factor: {pv_capacity_factor:.3f}")
    print(f"Wind capacity factor: {wind_capacity_factor:.3f}")
    
    # Maximum capacity based on land constraints
    max_pv_capacity = available_land_km2 / pv_land_use_km2_per_mw
    max_wind_capacity = available_land_km2 / wind_land_use_km2_per_mw
    
    print(f"Max PV capacity with available land: {max_pv_capacity:.2f} MW")
    print(f"Max wind capacity with available land: {max_wind_capacity:.2f} MW")
    
    # We'll use a grid search approach to find the optimal mix
    # This is more reliable than optimization for this specific problem
    
    # Define the grid for PV and wind capacities
    # We'll use a smaller number of points to speed up the search
    # This is a small problem so we don't need a very fine grid
    # Scale down the search space to more realistic capacities for a 40 MWh/year demand
    max_relevant_pv = min(max_pv_capacity, 50)  # PV systems are usually smaller than the theoretical max
    max_relevant_wind = min(max_wind_capacity, 50)  # Wind systems are usually smaller than the theoretical max
    
    pv_capacities = np.linspace(0, max_relevant_pv, 20)  # 20 points instead of 20
    wind_capacities = np.linspace(0, max_relevant_wind, 20)  # 20 points instead of 20
    
    # Initialize variables to track the best solution
    best_gwp = float('inf')
    best_mix = None
    
    # Grid search
    print("Starting grid search for optimal mix...")
    for pv_capacity_mw in pv_capacities:
        for wind_capacity_mw in wind_capacities:
            # Calculate land usage
            pv_land = pv_capacity_mw * pv_land_use_km2_per_mw
            wind_land = wind_capacity_mw * wind_land_use_km2_per_mw
            total_land = pv_land + wind_land
            
            # Skip if land usage exceeds available land
            if total_land > available_land_km2:
                continue
            
            # Calculate hourly generation
            pv_hourly = pv_unit_generation * pv_capacity_mw
            wind_hourly = wind_unit_generation * wind_capacity_mw
            renewable_hourly = pv_hourly + wind_hourly
            
            # Calculate grid contribution (deficit to be supplied by grid)
            # Use temperature-adjusted demand
            grid_hourly = np.maximum(0, adjusted_hourly_demand - renewable_hourly)
            
            # Calculate annual generation
            pv_annual_kwh = pv_hourly.sum()
            wind_annual_kwh = wind_hourly.sum()
            grid_annual_kwh = grid_hourly.sum()
            total_annual_kwh = pv_annual_kwh + wind_annual_kwh + grid_annual_kwh
            
            # Skip solutions that don't meet annual demand
            total_demand_kwh = adjusted_hourly_demand.sum()
            if total_annual_kwh < total_demand_kwh * 0.99:  # Allow 1% tolerance
                continue
                
            # Calculate shares
            pv_share = pv_annual_kwh / total_annual_kwh
            wind_share = wind_annual_kwh / total_annual_kwh
            grid_share = grid_annual_kwh / total_annual_kwh
            
            # Calculate GWP
            gwp = (
                pv_share * emission_factors['pv'] +
                wind_share * emission_factors['wind'] +
                grid_share * emission_factors['grid']
            )
            
            # Calculate stability metrics
            hours_with_deficit = (grid_hourly > 0).sum()
            deficit_percentage = hours_with_deficit / len(energy_data) * 100
            max_deficit = grid_hourly.max()
            
            # Update best solution if this is better
            if gwp < best_gwp:
                best_gwp = gwp
                best_mix = {
                    'pv_capacity_mw': pv_capacity_mw,
                    'wind_capacity_mw': wind_capacity_mw,
                    'pv_land_km2': pv_land,
                    'wind_land_km2': wind_land,
                    'total_land_km2': total_land,
                    'pv_annual_mwh': pv_annual_kwh / 1000,
                    'wind_annual_mwh': wind_annual_kwh / 1000,
                    'grid_annual_mwh': grid_annual_kwh / 1000,
                    'total_annual_mwh': total_annual_kwh / 1000,
                    'pv_percentage': pv_share * 100,
                    'wind_percentage': wind_share * 100,
                    'grid_percentage': grid_share * 100,
                    'total_gwp': gwp,
                    'hours_with_deficit': hours_with_deficit,
                    'deficit_percentage': deficit_percentage,
                    'max_hourly_deficit_kwh': max_deficit,
                    'pv_hourly': pv_hourly,
                    'wind_hourly': wind_hourly,
                    'grid_hourly': grid_hourly,
                    'demand_hourly': adjusted_hourly_demand
                }
                print(f"New best solution: PV={pv_capacity_mw:.2f} MW, Wind={wind_capacity_mw:.2f} MW, GWP={gwp:.4f} kg CO2e/kWh")
    
    if best_mix is None:
        raise ValueError("No feasible solution found. Try adjusting constraints.")
    
    # Create hourly supply profile for the best solution
    supply_profile = pd.DataFrame({
        'timestamp': energy_data['timestamp'],
        'pv_generation': best_mix['pv_hourly'],
        'wind_generation': best_mix['wind_hourly'],
        'renewable_total': best_mix['pv_hourly'] + best_mix['wind_hourly'],
        'demand': best_mix['demand_hourly'],
        'grid_required': best_mix['grid_hourly']
    })
    
    # If temperature data is available, add it to the supply profile
    if 'temperature' in energy_data.columns:
        supply_profile['temperature'] = energy_data['temperature']
    
    # Save the hourly supply profile for further analysis
    # Ensure output_data directory exists
    os.makedirs('output_data', exist_ok=True)
    
    # Save with timestamped filename
    timestamped_filename = get_timestamped_filename('optimal_supply_profile.csv')
    supply_profile.to_csv(os.path.join('output_data', timestamped_filename), index=False)
    
    # --- Generate Hourly Supply Profile Plots for First Week of Each Month ---
    print("\nGenerating weekly supply profile plots for each available month...")
    # Create a dedicated directory for these plots
    monthly_plots_dir = 'figures/monthly_first_week_profiles'
    os.makedirs(monthly_plots_dir, exist_ok=True)

    unique_months = sorted(supply_profile['timestamp'].dt.month.unique())
    
    for month in unique_months:
        # Find the start of the month in the data
        month_data = supply_profile[supply_profile['timestamp'].dt.month == month]
        if month_data.empty:
            continue # Skip if no data for this month (shouldn't happen with unique_months)
            
        start_of_month_ts = month_data['timestamp'].min()
        # Define the end of the first week (start + 7 days)
        end_of_first_week_ts = start_of_month_ts + pd.Timedelta(days=7)
        
        # Select data for the first week of this month
        sample_week = supply_profile[
            (supply_profile['timestamp'] >= start_of_month_ts) & 
            (supply_profile['timestamp'] < end_of_first_week_ts)
        ].copy()

        if sample_week.empty:
            print(f"Warning: No data found for the first week of month {month}. Skipping plot.")
            continue

        # --- Smoothing and Sorting for Plotting ---
        sample_week = sample_week.sort_values('timestamp')
        window_size = 6
        cols_to_smooth = ['pv_generation', 'wind_generation', 'renewable_total', 'demand', 'grid_required']
        for col in cols_to_smooth:
            sample_week[f'{col}_smoothed'] = sample_week[col].rolling(window=window_size, center=True, min_periods=1).mean()
        # --- End Smoothing ---

        plt.figure(figsize=(15, 10))
        month_name = start_of_month_ts.strftime('%B') # Get month name

        # --- Plot 1: Supply/Demand ---
        plt.subplot(2, 1, 1)
        plt.plot(sample_week['timestamp'], sample_week['pv_generation_smoothed'], label='PV (Smoothed)', color='orange')
        plt.plot(sample_week['timestamp'], sample_week['wind_generation_smoothed'], label='Wind (Smoothed)', color='green')
        plt.plot(sample_week['timestamp'], sample_week['demand_smoothed'], label='Demand (Smoothed)', color='black', linestyle='--')
        plt.fill_between(sample_week['timestamp'], 0, sample_week['grid_required_smoothed'], color='blue', alpha=0.3, label='Grid Required (Smoothed)')
        plt.title(f'Hourly Energy Supply and Demand (First Week of {month_name} - {window_size}hr Smoothed)')
        plt.ylabel('kWh')
        plt.legend()
        
        # --- Plot 2: Renewable/Demand ---
        plt.subplot(2, 1, 2)
        plt.plot(sample_week['timestamp'], sample_week['renewable_total_smoothed'], label='Renewable Generation (Smoothed)', color='green')
        plt.plot(sample_week['timestamp'], sample_week['demand_smoothed'], label='Demand (Smoothed)', color='black', linestyle='--')
        plt.fill_between(sample_week['timestamp'], 
                        sample_week['renewable_total_smoothed'], 
                        sample_week['demand_smoothed'], 
                        where=(sample_week['demand_smoothed'] > sample_week['renewable_total_smoothed']),
                        color='blue', alpha=0.3, label='Grid Required (Smoothed)')
        plt.title(f'Renewable Generation vs. Demand (First Week of {month_name} - {window_size}hr Smoothed)')
        plt.ylabel('kWh')
        plt.legend()
        
        plt.tight_layout()
        
        # Save the plot to the dedicated directory
        plot_filename = f'hourly_supply_profile_month_{month:02d}.png'
        plot_filepath = os.path.join(monthly_plots_dir, plot_filename)
        plt.savefig(plot_filepath)
        plt.close() # Close the plot figure to free memory
        print(f" - Saved plot: {plot_filepath}")

    print("Finished generating monthly weekly plots.")
    # --- End of Monthly Plot Generation ---

    # Create monthly energy mix chart
    monthly_data = supply_profile.copy()
    monthly_data['month'] = monthly_data['timestamp'].dt.month
    monthly_summary = monthly_data.groupby('month').agg({
        'pv_generation': 'sum',
        'wind_generation': 'sum',
        'grid_required': 'sum',
        'demand': 'sum'
    })
    
    # --- Filter summary for plotting --- 
    # Only include months where renewable generation occurred
    initial_months = len(monthly_summary)
    monthly_summary = monthly_summary[monthly_summary['pv_generation'] + monthly_summary['wind_generation'] > 0.1] # Use threshold > 0
    filtered_months = len(monthly_summary)
    if initial_months > filtered_months:
        print(f"Filtering monthly plot: Removed {initial_months - filtered_months} months with zero renewable generation.")
    # --- End filter --- 

    # Plot monthly energy mix
    plt.figure(figsize=(14, 8))
    
    # Define colors to match previous plots and common conventions
    colors = {'pv_generation': 'orange', 'wind_generation': 'green', 'grid_required': 'blue'}
    
    # Plot the stacked bar chart first using the DataFrame plot method
    # This generally ensures stack order matches legend order (bottom to top)
    ax = monthly_summary[['pv_generation', 'wind_generation', 'grid_required']].plot(
        kind='bar', 
        stacked=True, 
        color=[colors['pv_generation'], colors['wind_generation'], colors['grid_required']], 
        alpha=0.7,
        figsize=(14, 8) # Specify figsize here for the DataFrame plot
    )
    
    # Plot the demand line on the same axes (ax)
    monthly_summary['demand'].plot(
        kind='line', 
        color='red', 
        marker='o', 
        linewidth=2, 
        label='Demand',
        ax=ax # Ensure it plots on the same axes
    )
    
    plt.title('Monthly Energy Generation by Source')
    plt.xlabel('Month')
    plt.ylabel('Energy (kWh)')
    
    # Improve legend placement
    plt.legend(loc='upper left', bbox_to_anchor=(1, 1)) # Place legend outside plot area
    
    # Set x-ticks (adjust index based on filtered months if necessary)
    month_indices = monthly_summary.index.tolist()
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    plt.xticks(ticks=range(len(month_indices)), labels=[month_names[i-1] for i in month_indices], rotation=0) # Use filtered indices
    
    plt.tight_layout(rect=[0, 0, 0.85, 1]) # Adjust layout to make space for the legend

    # Save with timestamped filename
    timestamped_filename = get_timestamped_filename('monthly_energy_mix.png')
    plt.savefig(os.path.join('figures', timestamped_filename))
    plt.close()
    
    # If temperature data is available, create a temperature vs. demand plot
    if 'temperature' in energy_data.columns:
        plt.figure(figsize=(15, 10))
        
        # Plot 1: Temperature distribution
        plt.subplot(2, 2, 1)
        plt.hist(energy_data['temperature'], bins=20, color='royalblue', alpha=0.7)
        plt.axvline(x=30, color='red', linestyle='--', label='30°C threshold')
        plt.title('Temperature Distribution')
        plt.xlabel('Temperature (°C)')
        plt.ylabel('Hours')
        plt.legend()
        
        # Plot 2: Temperature vs. Demand Curve
        plt.subplot(2, 2, 2)
        
        # Create temperature bins focused around 30°C threshold
        temp_bins = np.array([-10, 0, 10, 20, 25, 28, 30, 32, 35, 40, 45])  # Focus more detail around 30°C
        supply_profile['temp_bin'] = pd.cut(supply_profile['temperature'], bins=temp_bins)
        
        # Group data by temperature bins
        temp_demand = supply_profile.groupby('temp_bin')['demand'].mean()
        base_demand = hourly_demand_kwh
        
        # Plot temperature vs. demand with clear 30°C threshold
        ax = temp_demand.plot(kind='bar', color='darkred')
        plt.axhline(y=base_demand, color='black', linestyle='--', label='Base demand')
        plt.axhline(y=base_demand*1.2, color='red', linestyle='--', label='Base demand +20%')
        
        # Add vertical line at 30°C threshold
        plt.axvline(x=6, color='blue', linestyle='--', label='30°C threshold')  # 6 is the 30°C bin position
        
        plt.title('Average Hourly Demand by Temperature Range')
        plt.xlabel('Temperature Range (°C)')
        plt.ylabel('Average Demand (kWh)')
        plt.legend()
        
        # Plot 3: Daily temperature and demand profile for a hot week
        plt.subplot(2, 2, 3)
        
        try:
            # Find a week with high temperatures
            weekly_temp = supply_profile.set_index('timestamp')['temperature'].resample('W').mean()
            hot_week_start = weekly_temp.idxmax() - pd.Timedelta(days=3)
            hot_week = supply_profile[(supply_profile['timestamp'] >= hot_week_start) & 
                                    (supply_profile['timestamp'] < hot_week_start + pd.Timedelta(days=7))]
            
            # Plot temperature and demand for the hot week
            plt.plot(hot_week['timestamp'], hot_week['temperature'], 'r-', label='Temperature')
            plt.axhline(y=30, color='r', linestyle='--', alpha=0.7, label='30°C threshold')
            plt.title(f'Temperature During Hottest Week ({hot_week_start.strftime("%Y-%m-%d")})')
            plt.ylabel('Temperature (°C)')
            plt.legend(loc='upper left')
            
            # Create second y-axis for demand
            ax2 = plt.twinx()
            ax2.plot(hot_week['timestamp'], hot_week['demand'], 'b-', label='Demand')
            ax2.plot(hot_week['timestamp'], [hourly_demand_kwh] * len(hot_week), 'b--', alpha=0.7, label='Base demand')
            ax2.set_ylabel('Demand (kWh)')
            ax2.legend(loc='upper right')
        except Exception as e:
            # If there's an error with the hot week data, plot the first week instead
            print(f"Error plotting hot week: {e}. Using first week instead.")
            first_week = supply_profile.iloc[:168]  # First week
            
            plt.plot(first_week['timestamp'], first_week['temperature'], 'r-', label='Temperature')
            plt.axhline(y=30, color='r', linestyle='--', alpha=0.7, label='30°C threshold')
            plt.title('Temperature During First Week')
            plt.ylabel('Temperature (°C)')
            plt.legend(loc='upper left')
            
            # Create second y-axis for demand
            ax2 = plt.twinx()
            ax2.plot(first_week['timestamp'], first_week['demand'], 'b-', label='Demand')
            ax2.plot(first_week['timestamp'], [hourly_demand_kwh] * len(first_week), 'b--', alpha=0.7, label='Base demand')
            ax2.set_ylabel('Demand (kWh)')
            ax2.legend(loc='upper right')
        
        # Plot 4: Energy mix by temperature band
        plt.subplot(2, 2, 4)
        
        # Calculate energy mix by temperature band
        # Use just two temperature bands: ≤30°C and >30°C
        temp_bins_simple = [-20, 30, 50]  # ≤30°C, >30°C
        bin_labels = ['≤30°C (Base Demand)', '>30°C (+20% Demand)']
        supply_profile['temp_category'] = pd.cut(supply_profile['temperature'], bins=temp_bins_simple, labels=bin_labels)
        
        # Group data by temperature category
        temp_energy = supply_profile.groupby('temp_category').agg({
            'pv_generation': 'sum',
            'wind_generation': 'sum',
            'grid_required': 'sum',
            'demand': 'sum'
        })
        
        # Calculate percentage of demand
        for col in ['pv_generation', 'wind_generation', 'grid_required']:
            temp_energy[f'{col}_pct'] = temp_energy[col] / temp_energy['demand'] * 100
        
        # Plot stacked bar chart
        temp_energy[['grid_required_pct', 'wind_generation_pct', 'pv_generation_pct']].plot(
            kind='bar', stacked=True, 
            color=['#1E90FF', '#32CD32', '#FFA500'],
            title='Energy Mix by Temperature Range'
        )
        plt.xlabel('Temperature Range')
        plt.ylabel('Percentage of Demand (%)')
        plt.legend(['Grid', 'Wind', 'PV'])
        
        plt.tight_layout()
        
        # Save with timestamped filename
        timestamped_filename = get_timestamped_filename('temperature_analysis.png')
        plt.savefig(os.path.join('figures', timestamped_filename))
        plt.close()
        
        # Create a GWP vs. temperature analysis
        plt.figure(figsize=(12, 6))
        
        # Calculate GWP for each hour
        supply_profile['hourly_gwp'] = (
            (supply_profile['pv_generation'] * emission_factors['pv']) +
            (supply_profile['wind_generation'] * emission_factors['wind']) +
            (supply_profile['grid_required'] * emission_factors['grid'])
        ) / supply_profile['demand']
        
        # Group by temperature bins
        gwp_by_temp = supply_profile.groupby('temp_bin')['hourly_gwp'].mean()
        
        # Plot GWP vs. temperature
        gwp_by_temp.plot(kind='bar', color='purple')
        plt.title('Average GWP by Temperature Range')
        plt.xlabel('Temperature Range (°C)')
        plt.ylabel('GWP (kg CO2e/kWh)')
        
        # Calculate average GWP
        avg_gwp = supply_profile['hourly_gwp'].mean()
        plt.axhline(y=avg_gwp, color='red', linestyle='--', label=f'Overall Average GWP: {avg_gwp:.4f}')
        plt.legend()
        
        plt.tight_layout()
        
        # Save with timestamped filename
        timestamped_filename = get_timestamped_filename('gwp_by_temperature.png')
        plt.savefig(os.path.join('figures', timestamped_filename))
        plt.close()
    
    # Clean up the best_mix dictionary before returning
    best_mix.pop('pv_hourly', None)
    best_mix.pop('wind_hourly', None)
    best_mix.pop('grid_hourly', None)
    best_mix.pop('demand_hourly', None)
    
    return best_mix

def main():
    # Debug print
    print("Starting optimization script...")

    # --- Archive previous run's output --- 
    print("Archiving previous run's output files...")
    
    # Define directories
    figures_dir = 'figures'
    figures_old_dir = os.path.join(figures_dir, 'old')
    data_dir = 'output_data'
    data_old_dir = os.path.join(data_dir, 'old')
    monthly_profiles_dir = os.path.join(figures_dir, 'monthly_first_week_profiles') # Also handle this special dir
    monthly_profiles_old_dir = os.path.join(figures_old_dir, 'monthly_first_week_profiles')

    # Ensure base and old directories exist
    os.makedirs(figures_dir, exist_ok=True)
    os.makedirs(figures_old_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(data_old_dir, exist_ok=True)
    os.makedirs(monthly_profiles_dir, exist_ok=True) # Need this for plots
    os.makedirs(monthly_profiles_old_dir, exist_ok=True) # Create nested old dir

    # Archive figures/*.png
    try:
        for filename in os.listdir(figures_dir):
            source_path = os.path.join(figures_dir, filename)
            # Check if it's a PNG file and not a directory
            if filename.lower().endswith('.png') and os.path.isfile(source_path):
                dest_path = os.path.join(figures_old_dir, filename)
                print(f" - Archiving figure: {filename}")
                shutil.move(source_path, dest_path)
    except Exception as e:
        print(f"Warning: Could not archive figures: {e}")

    # Archive figures/monthly_first_week_profiles/*.png
    if os.path.exists(monthly_profiles_dir):
        try:
            for filename in os.listdir(monthly_profiles_dir):
                source_path = os.path.join(monthly_profiles_dir, filename)
                if filename.lower().endswith('.png') and os.path.isfile(source_path):
                    dest_path = os.path.join(monthly_profiles_old_dir, filename)
                    print(f" - Archiving monthly profile: {filename}")
                    shutil.move(source_path, dest_path)
        except Exception as e:
            print(f"Warning: Could not archive monthly profiles: {e}")

    # Archive output_data/*.*
    try:
        for filename in os.listdir(data_dir):
            source_path = os.path.join(data_dir, filename)
            # Check if it's a file (not the 'old' directory)
            if os.path.isfile(source_path):
                dest_path = os.path.join(data_old_dir, filename)
                print(f" - Archiving data file: {filename}")
                shutil.move(source_path, dest_path) 
    except Exception as e:
        print(f"Warning: Could not archive output data: {e}")

    # --- End Archiving ---

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
    
    # Moomba coordinates
    moomba_latitude = -28.1083  # South
    moomba_longitude = 140.2028  # East
    
    # Coober Pedy coordinates (fallback)
    coober_pedy_latitude = -29.0139  # South
    coober_pedy_longitude = 134.7544  # East
    
    use_synthetic = False
    location_name = "Unknown"
    
    # Try to fetch real data for Moomba first
    try:
        print("\nAttempting to fetch NASA POWER data for Moomba, Australia...")
        energy_data, real_data_flag = generate_location_data("Moomba", moomba_latitude, moomba_longitude, start_date, end_date)
        location_name = "Moomba"
        use_synthetic = not real_data_flag
    except Exception as e:
        print(f"\nError with Moomba data: {e}")
        
        # Try to fetch Coober Pedy data as fallback
        try:
            print("\nAttempting to fetch NASA POWER data for Coober Pedy, Australia...")
            energy_data, real_data_flag = generate_location_data("Coober Pedy", coober_pedy_latitude, coober_pedy_longitude, start_date, end_date)
            location_name = "Coober Pedy"
            use_synthetic = not real_data_flag
        except Exception as e:
            print(f"\nError with Coober Pedy data: {e}")
            print("\nFalling back to synthetic data...")
            energy_data = generate_synthetic_data(start_date, end_date, moomba_latitude, moomba_longitude)
            energy_data['location'] = "Synthetic Moomba data"
            use_synthetic = True
    
    print(f"\nData source: {location_name}{' (synthetic)' if use_synthetic else ' (real NASA POWER)'}")
    
    # --- Add check for actual data range ---
    if energy_data is not None and not energy_data.empty:
        actual_start = energy_data['timestamp'].min()
        actual_end = energy_data['timestamp'].max()
        print(f"Actual data range in DataFrame: {actual_start} to {actual_end}")
        # Check if the data covers the expected end date (or close to it)
        expected_end_dt = pd.to_datetime(end_date) # Convert string end_date to datetime
        if actual_end < expected_end_dt - pd.Timedelta(days=1): # Allow a small buffer
             print(f"Warning: Data appears incomplete. Expected end date {expected_end_dt.date()}, but data ends on {actual_end.date()}.")
             print(f"Monthly plot will likely be truncated.")
    else:
        print("Error: energy_data DataFrame is None or empty after generation/loading. Cannot proceed.")
        return # Exit if no data
    # --- End check ---

    # Save the generated data
    save_data_to_csv(energy_data, 'australian_energy_data.csv')
    
    # Display location information if available
    if 'location' in energy_data.columns:
        print(f"\nAnalysis based on data from: {energy_data['location'].iloc[0]}")
    
    # Plot generation profiles
    plt.figure(figsize=(15, 10))
    
    plt.subplot(3, 1, 1)
    plt.plot(energy_data['timestamp'], energy_data['pv_generation'])
    plt.title('PV Generation')
    plt.ylabel('kWh')
    
    plt.subplot(3, 1, 2)
    plt.plot(energy_data['timestamp'], energy_data['wind_generation'])
    plt.title('Wind Generation')
    plt.ylabel('kWh')
    
    plt.subplot(3, 1, 3)
    plt.plot(energy_data['timestamp'], energy_data['temperature'])
    plt.title('Temperature')
    plt.ylabel('°C')
    plt.axhline(y=30, color='red', linestyle='--', label='30°C threshold')
    plt.legend()
    
    plt.tight_layout()
    
    # Save with timestamped filename
    timestamped_filename = get_timestamped_filename('generation_profiles.png')
    plt.savefig(os.path.join('figures', timestamped_filename))
    plt.close()
    
    # New section: Calculate optimal land use for 40 MWh annual demand with 50 km² available land
    print("\nOptimizing energy mix for 40 MWh annual demand with 50 km² available land:")
    print("-" * 80)
    
    # Run the land use optimization
    optimal_mix = optimize_land_use(energy_data, 40, 50)
    
    # Print the results
    print("\n" + "="*80)
    print("OPTIMAL ENERGY MIX SOLUTION")
    print("="*80)
    print(f"Optimal PV capacity: {optimal_mix['pv_capacity_mw']:.2f} MW using {optimal_mix['pv_land_km2']:.2f} km²")
    print(f"Optimal wind capacity: {optimal_mix['wind_capacity_mw']:.2f} MW using {optimal_mix['wind_land_km2']:.2f} km²")
    print(f"Total land usage: {optimal_mix['total_land_km2']:.2f} km² of {50:.2f} km² available")
    print("\nEnergy mix:")
    print(f"PV generation: {optimal_mix['pv_annual_mwh']:.2f} MWh/year ({optimal_mix['pv_percentage']:.1f}%)")
    print(f"Wind generation: {optimal_mix['wind_annual_mwh']:.2f} MWh/year ({optimal_mix['wind_percentage']:.1f}%)")
    print(f"Grid usage: {optimal_mix['grid_annual_mwh']:.2f} MWh/year ({optimal_mix['grid_percentage']:.1f}%)")
    print(f"Total annual generation: {optimal_mix.get('total_annual_mwh', optimal_mix['pv_annual_mwh'] + optimal_mix['wind_annual_mwh'] + optimal_mix['grid_annual_mwh']):.2f} MWh/year")
    
    print(f"\nGlobal Warming Potential: {optimal_mix['total_gwp']:.4f} kg CO2e/kWh")
    
    print("\nStability analysis:")
    print(f"Hours with renewable generation deficit: {optimal_mix['hours_with_deficit']} of {len(energy_data)} ({optimal_mix['deficit_percentage']:.1f}%)")
    print(f"Maximum hourly deficit: {optimal_mix['max_hourly_deficit_kwh']:.2f} kWh")
    
    print("\nOutput files created:")
    print("- data/optimal_supply_profile.csv - Hourly generation data")
    print("- data/hourly_supply_profile.png - Visualizations of hourly supply")
    print("- data/monthly_energy_mix.png - Monthly energy mix chart")
    print("- data/optimal_energy_mix.png - Pie chart of energy mix")
    print("- data/temperature_analysis.png - Temperature impact analysis")
    print("- data/gwp_by_temperature.png - GWP vs temperature analysis")
    
    # Create visualization of the optimal mix
    labels = ['PV', 'Wind', 'Grid']
    sizes = [optimal_mix['pv_percentage'], optimal_mix['wind_percentage'], optimal_mix['grid_percentage']]
    colors = ['#FFA500', '#32CD32', '#1E90FF']
    explode = (0.1, 0.1, 0)
    
    plt.figure(figsize=(10, 7))
    plt.pie(sizes, explode=explode, labels=labels, colors=colors, autopct='%1.1f%%', startangle=140)
    plt.axis('equal')
    plt.title(f"Optimal Energy Mix for 40 MWh Annual Demand\nTotal GWP: {optimal_mix['total_gwp']:.4f} kg CO2e/kWh")
    
    # Save with timestamped filename
    timestamped_filename = get_timestamped_filename('optimal_energy_mix.png')
    plt.savefig(os.path.join('figures', timestamped_filename))
    plt.close()

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
            print(f"Successfully obtained NASA POWER data for {location_name}")
            
            # Add PV and wind generation based on the real weather data
            data = process_real_data(data)
            
            # Add location column
            data['location'] = location_name
            
            return data, True  # Return data and flag indicating real data
        else:
            print(f"NASA POWER data fetch for {location_name} returned empty dataset")
    except Exception as e:
        print(f"Error processing NASA POWER data for {location_name}: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"Unable to fetch real data for {location_name}, returning None")
    return None, False

if __name__ == "__main__":
    main() 


