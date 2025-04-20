#!/usr/bin/env python
"""
Run script for the energy mix optimization project
This script imports and runs the main function from the latest version of the optimization script
"""

import os
import glob
import importlib.util
import sys
from datetime import datetime

def find_latest_script():
    """Find the latest optimization script in the src directory"""
    # Get all optimization scripts
    scripts = glob.glob('src/energy_mix_optimization_*.py')
    
    if not scripts:
        print("Error: No optimization scripts found in src directory")
        sys.exit(1)
    
    # Sort by modification time (newest first)
    latest_script = max(scripts, key=os.path.getmtime)
    print(f"Using latest script: {latest_script}")
    return latest_script

def import_and_run():
    """Import and run the main function from the latest script"""
    script_path = find_latest_script()
    
    # Extract the module name without extension
    module_name = os.path.splitext(os.path.basename(script_path))[0]
    
    # Import the module
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    
    # Run the main function
    print(f"Starting optimization at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    module.main()
    print(f"Optimization completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    import_and_run() 