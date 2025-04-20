import pandas as pd
import numpy as np
from scipy.optimize import minimize
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import os
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
    
    # Parameters for the API request
    params = {
        "parameters": "ALLSKY_SFC_SW_DWN,WS2M",  # Solar radiation and wind speed at 2m
        "community": "RE",
        "longitude": longitude,
        "latitude": latitude,
        "start": start_str,
        "end": end_str,
        "format": "CSV"
    }
    
    try:
        # Make the API request
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        
        # Parse the CSV data
        data = pd.read_csv(StringIO(response.text), skiprows=14)
        
        # Convert to datetime
        data['YEAR'] = data['YEAR'].astype(str)
        data['MO'] = data['MO'].astype(str).str.zfill(2)
        data['DY'] = data['DY'].astype(str).str.zfill(2)
        data['HR'] = data['HR'].astype(str).str.zfill(2)
        
        data['timestamp'] = pd.to_datetime(
            data['YEAR'] + data['MO'] + data['DY'] + data['HR'],
            format='%Y%m%d%H'
        )
        
        # Rename columns to match our existing code
        data = data.rename(columns={
            'ALLSKY_SFC_SW_DWN': 'solar_irradiation',
            'WS2M': 'wind_speed'
        })
        
        # Select and reorder columns
        data = data[['timestamp', 'solar_irradiation', 'wind_speed']]
        
        return data
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching NASA POWER data: {e}")
        return None

def process_real_data(weather_data, pv_capacity=1000, wind_capacity=2000):
    """
    Process real weather data to calculate generation
    """
    # Calculate PV generation (kWh)
    # Assuming system with 15% efficiency and temperature effect
    pv_efficiency = 0.15
    temp_effect = 1 - 0.004 * 30  # Typical temperature effect for Moomba
    weather_data['pv_generation'] = (
        weather_data['solar_irradiation'] * 
        pv_efficiency * 
        pv_capacity * 
        temp_effect / 1000  # Convert to kWh
    )
    
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
        elif speed > rated_speed:
            return wind_capacity
        else:
            return wind_capacity * ((speed - cut_in_speed) / (rated_speed - cut_in_speed)) ** 3
    
    weather_data['wind_generation'] = weather_data['wind_speed'].apply(wind_power_curve)
    
    # Add additional columns
    weather_data['total_generation'] = weather_data['pv_generation'] + weather_data['wind_generation']
    weather_data['month'] = weather_data['timestamp'].dt.month
    weather_data['hour'] = weather_data['timestamp'].dt.hour
    weather_data['season'] = weather_data['timestamp'].dt.month % 12 // 3 + 1
    
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
    
    # Create DataFrame
    data = pd.DataFrame({
        'timestamp': date_range,
        'solar_irradiation': solar_irradiation,
        'wind_speed': wind_speed
    })
    
    # Process the synthetic data
    data = process_real_data(data)
    
    return data

def save_data_to_csv(data, filename):
    """
    Save the data to a CSV file in the data directory
    """
    # Ensure the data directory exists
    os.makedirs('data', exist_ok=True)
    
    # Save the data
    filepath = os.path.join('data', filename)
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

def plot_demand_sensitivity(energy_data, capacity_constraints, emission_factors):
    """
    Create a plot showing how the optimal energy mix changes with varying demand
    """
    # Create a range of demand values
    min_demand = energy_data['total_generation'].min()
    max_demand = energy_data['total_generation'].max()
    demand_values = np.linspace(min_demand, max_demand, 50)
    
    # Calculate optimal mix for each demand value
    grid_shares = []
    pv_shares = []
    wind_shares = []
    gwp_values = []
    
    for demand in demand_values:
        optimal_mix = optimize_energy_mix(energy_data, demand, capacity_constraints, emission_factors)
        grid_shares.append(optimal_mix[0] * 100)
        pv_shares.append(optimal_mix[1] * 100)
        wind_shares.append(optimal_mix[2] * 100)
        gwp_values.append(calculate_gwp(optimal_mix, np.array(list(emission_factors.values()))))
    
    # Create the plot with two subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 12), height_ratios=[2, 1])
    
    # Plot energy mix
    ax1.plot(demand_values, grid_shares, label='Grid', linewidth=2, color='blue')
    ax1.plot(demand_values, pv_shares, label='PV', linewidth=2, color='orange', linestyle='--')
    ax1.plot(demand_values, wind_shares, label='Wind', linewidth=2, color='green', linestyle=':')
    
    # Add a vertical line at the average demand
    avg_demand = energy_data['total_generation'].mean()
    ax1.axvline(x=avg_demand, color='gray', linestyle='--', label='Average Demand')
    
    # Add horizontal lines for capacity constraints
    ax1.axhline(y=capacity_constraints['grid']*100, color='blue', linestyle=':', alpha=0.3)
    ax1.axhline(y=capacity_constraints['pv']*100, color='orange', linestyle=':', alpha=0.3)
    ax1.axhline(y=capacity_constraints['wind']*100, color='green', linestyle=':', alpha=0.3)
    
    ax1.set_xlabel('Energy Demand (kWh)')
    ax1.set_ylabel('Share of Energy Mix (%)')
    ax1.set_title('Optimal Energy Mix vs. Energy Demand')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Add some annotations
    ax1.annotate(f'Average Demand: {avg_demand:.1f} kWh',
                xy=(avg_demand, 0),
                xytext=(10, 10),
                textcoords='offset points',
                bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.3))
    
    # Add capacity constraint annotations
    for source, constraint in capacity_constraints.items():
        ax1.annotate(f'{source.capitalize()} Max: {constraint*100}%',
                    xy=(demand_values[-1], constraint*100),
                    xytext=(-100, 0),
                    textcoords='offset points',
                    color={'grid': 'blue', 'pv': 'orange', 'wind': 'green'}[source],
                    alpha=0.7)
    
    # Plot GWP
    ax2.plot(demand_values, gwp_values, label='GWP', color='red', linewidth=2)
    ax2.set_xlabel('Energy Demand (kWh)')
    ax2.set_ylabel('Global Warming Potential\n(kg CO2e/kWh)')
    ax2.set_title('Global Warming Potential vs. Energy Demand')
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('data/demand_sensitivity.png')
    plt.close()

def main():
    # Generate synthetic data for Moomba
    start_date = '2023-01-01'
    end_date = '2023-12-31'
    
    try:
        # Try to fetch real data first
        energy_data = generate_moomba_data(start_date, end_date, use_real_data=True)
    except Exception as e:
        print(f"Error with real data: {e}")
        print("Falling back to synthetic data...")
        energy_data = generate_moomba_data(start_date, end_date, use_real_data=False)
    
    # Save the generated data
    save_data_to_csv(energy_data, 'moomba_energy_data.csv')
    
    # Example parameters (adjust based on your needs)
    demand = 1000  # kWh
    capacity_constraints = {
        'grid': 0.6,  # Maximum 60% from grid
        'pv': 0.4,    # Maximum 40% from PV
        'wind': 0.4   # Maximum 40% from wind
    }
    
    # Example emission factors (kg CO2e/kWh)
    # These should be provided by the user for each location
    emission_factors = {
        'grid': 0.85,  # Example grid emission factor for Australia
        'pv': 0.041,   # Typical PV emission factor
        'wind': 0.011  # Typical wind emission factor
    }
    
    # Create demand sensitivity plot
    plot_demand_sensitivity(energy_data, capacity_constraints, emission_factors)
    
    # Optimize energy mix for the specified demand
    optimal_mix = optimize_energy_mix(energy_data, demand, capacity_constraints, emission_factors)
    
    # Print results
    print("\nOptimal Energy Mix:")
    print(f"Grid: {optimal_mix[0]*100:.2f}%")
    print(f"PV: {optimal_mix[1]*100:.2f}%")
    print(f"Wind: {optimal_mix[2]*100:.2f}%")
    
    # Calculate and print GWP
    gwp = calculate_gwp(optimal_mix, np.array(list(emission_factors.values())))
    print(f"\nGlobal Warming Potential: {gwp:.2f} kg CO2e/kWh")
    
    # Plot results
    plt.figure(figsize=(10, 6))
    sources = ['Grid', 'PV', 'Wind']
    plt.pie(optimal_mix, labels=sources, autopct='%1.1f%%')
    plt.title('Optimal Energy Mix')
    plt.savefig('data/optimal_energy_mix.png')
    plt.close()
    
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
    plt.plot(energy_data['timestamp'], energy_data['solar_irradiation'])
    plt.title('Solar Irradiation')
    plt.ylabel('W/m²')
    
    plt.tight_layout()
    plt.savefig('data/generation_profiles.png')
    plt.close()

if __name__ == "__main__":
    main() 


