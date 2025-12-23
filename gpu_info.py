#!/usr/bin/env python3
"""
GPU Info - Cross-platform GPU information utility
Displays detailed information about GPUs from NVIDIA, AMD, Intel, and Apple.

Requirements:
  - Python 3.6+
  - For NVIDIA GPU support: pip install nvidia-ml-py
  - Linux: lspci (install via: sudo apt-get install pciutils)
  - macOS: No additional requirements
  - Windows: PowerShell (pre-installed)
"""

import platform
import subprocess
import json
import os
import sys
import time
import shutil
from typing import List, Dict

def get_elapsed_time(start_time: float) -> str:
    """
    Calculate and format the elapsed time since a given start time.
    
    Args:
        start_time: The starting timestamp (from time.time())
    
    Returns:
        Formatted string showing elapsed time in seconds (e.g., "1.23s")
    """
    elapsed = time.time() - start_time
    return f"{elapsed:.2f}s"

def get_macos_gpu_info() -> List[Dict]:
    """
    Get GPU information on macOS using system_profiler.
    
    This function retrieves GPU details specifically for macOS systems,
    with special handling for Apple Silicon chips (M1/M2/M3/M4 series).
    
    Returns:
        List of dictionaries containing GPU information for each detected GPU
    """
    gpus = []
    
    # Dictionary mapping Apple Silicon chip models to their specifications
    # Format: chip_name: (gpu_cores, clock_speed_ghz, memory_bandwidth_gbs, cache_mb)
    APPLE_SILICON_SPECS = {
        "M1": (8, 1.30, 68.2, 8),
        "M1 Pro": (14, 1.30, 204.8, 16),
        "M1 Max": (32, 1.30, 409.6, 24),
        "M1 Ultra": (64, 1.30, 819.2, 48),
        "M2": (10, 1.40, 76.8, 8),
        "M2 Pro": (16, 1.40, 204.8, 16),
        "M2 Max": (38, 1.40, 409.6, 24),
        "M2 Ultra": (76, 1.40, 819.2, 48),
        "M3": (10, 1.50, 102.4, 8),
        "M3 Pro": (14, 1.50, 153.6, 16),
        "M3 Max": (30, 1.50, 307.2, 24),
        "M3 Ultra": (60, 1.50, 614.4, 48),
        "M4": (10, 1.40, 136.5, 8),
        "M4 Pro": (16, 1.40, 273.0, 16),
        "M4 Max": (32, 1.40, 546.0, 24),
    }
    
    try:
        # Run system_profiler command to get display/GPU information in JSON format
        result = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse the JSON output
        data = json.loads(result.stdout)
        displays = data.get("SPDisplaysDataType", [])
        
        # Iterate through each display/GPU device
        for display in displays:
            gpu_info = {}
            
            # Extract basic GPU information from system_profiler output
            gpu_info["GPU name"] = display.get("_name", "Unknown")
            gpu_info["GPU vendor"] = display.get("sppci_vendor", "Apple")
            
            # Get GPU core count (specific to Apple Silicon)
            gpu_info["GPU core count"] = display.get("sppci_cores", "N/A")
            
            # Get Metal GPU family support (Apple's graphics API)
            gpu_info["GPU family"] = display.get("spdisplays_mtlgpufamilysupport", "N/A")
            
            # Get VRAM (Video RAM) size
            gpu_info["GPU memory"] = display.get("spdisplays_vram", "N/A")
            
            # Try to match GPU name against known Apple Silicon specs
            gpu_name = gpu_info["GPU name"]
            found_specs = False
            for chip, (cores, clock, bandwidth, cache) in APPLE_SILICON_SPECS.items():
                if chip in gpu_name:
                    # Apply known specifications for this chip
                    gpu_info["GPU system level cache"] = f"{cache} MB"
                    gpu_info["GPU clock frequency"] = f"{clock:.2f} GHz"
                    gpu_info["GPU bandwidth"] = f"{bandwidth:.1f} GB/s"
                    
                    # Calculate FLOPS (Floating Point Operations Per Second) and IPS (Instructions Per Second)
                    if gpu_info["GPU core count"] != "N/A":
                        try:
                            actual_cores = int(gpu_info["GPU core count"])
                            alus_per_core = 128  # Apple GPU architecture has 128 ALUs per core
                            # FMA (Fused Multiply-Add) counts as 2 operations per clock cycle
                            flops = actual_cores * clock * alus_per_core * 2
                            gpu_info["GPU FLOPS"] = f"{flops / 1000:.3f} TFLOPS"
                            gpu_info["GPU IPS"] = f"{flops / 1000:.3f} TIPS"
                        except:
                            gpu_info["GPU FLOPS"] = "N/A"
                            gpu_info["GPU IPS"] = "N/A"
                    found_specs = True
                    break
            
            # If chip specs weren't found in our lookup table, try to get cache from sysctl
            if not found_specs:
                try:
                    cache_result = subprocess.run(
                        ["sysctl", "-n", "hw.l2cache"],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    # Convert cache size from bytes to megabytes
                    cache_bytes = int(cache_result.stdout.strip())
                    gpu_info["GPU system level cache"] = f"{cache_bytes // 1024 // 1024} MB"
                except:
                    gpu_info["GPU system level cache"] = "N/A"
                
                # Set remaining fields as unavailable
                gpu_info["GPU clock frequency"] = "N/A"
                gpu_info["GPU bandwidth"] = "N/A"
            
            gpus.append(gpu_info)
            
    except Exception as e:
        # If any error occurs, add an error entry to the results
        gpus.append({"Error": f"Failed to get macOS GPU info: {e}"})
    
    return gpus

def estimate_nvidia_cores(gpu_name: str) -> str:
    """
    Estimate the number of CUDA cores for an NVIDIA GPU based on its model name.
    
    This function uses a lookup table of known GPU models to estimate core counts,
    since this information isn't always available through system APIs.
    
    Args:
        gpu_name: The name of the NVIDIA GPU
    
    Returns:
        Estimated core count as a string, or "N/A" if unknown
    """
    name_upper = gpu_name.upper()
    
    # Dictionary of known NVIDIA GPU models and their CUDA core counts
    core_estimates = {
        # RTX 40 series
        "4090": "16384", "4080": "9728", "4070 Ti": "7680", "4070": "5888", "4060 Ti": "4352", "4060": "3072",
        # RTX 30 series
        "3090 Ti": "10752", "3090": "10496", "3080 Ti": "10240", "3080": "8704", "3070 Ti": "6144", "3070": "5888", "3060 Ti": "4864", "3060": "3584", "3050": "2560",
        # RTX 20 series
        "2080 Ti": "4352", "2080 Super": "3072", "2080": "2944", "2070 Super": "2560", "2070": "2304", "2060 Super": "2176", "2060": "1920",
        # GTX 16 series
        "1660 Super": "1408", "1660 Ti": "1536", "1660": "1408", "1650 Super": "1280", "1650": "896",
        # TITAN series
        "TITAN RTX": "4608", "TITAN V": "5120", "TITAN Xp": "3840",
        # Data center GPUs
        "A100": "6912", "A40": "10752", "A30": "3584", "A16": "5120", "A10": "9216",
        "V100": "5120", "P100": "3584", "T4": "2560",
    }
    
    # Check for exact model matches first
    for model, cores in core_estimates.items():
        if model in gpu_name:
            return cores
    
    # If no exact match, provide rough estimates based on GPU series
    if any(x in name_upper for x in ["RTX 40", "RTX 30"]):
        return "~4000"
    elif any(x in name_upper for x in ["RTX 20", "GTX 16"]):
        return "~2000"
    elif "GTX 10" in name_upper:
        return "~1500"
    return "N/A"

def get_nvidia_l2_cache(handle) -> str:
    """
    Get the L2 cache size for an NVIDIA GPU using the NVML library.
    
    Args:
        handle: NVML device handle for the GPU
    
    Returns:
        L2 cache size as a formatted string, or "N/A" if unavailable
    """
    try:
        import pynvml
        # Query L2 cache size in kilobytes and convert to megabytes
        cache_kb = pynvml.nvmlDeviceGetL2CacheSize(handle)
        return f"{cache_kb // 1024} MB"
    except:
        return "N/A"

def get_linux_gpu_info() -> List[Dict]:
    """
    Get GPU information on Linux systems.
    
    This function tries multiple methods in order of preference:
    1. NVIDIA GPUs via pynvml (NVIDIA Management Library)
    2. AMD GPUs via rocm-smi (ROCm System Management Interface)
    3. All GPUs via lspci (PCI utilities)
    
    Returns:
        List of dictionaries containing GPU information for each detected GPU
    """
    gpus = []
    
    # Method 1: Try NVIDIA via pynvml (most reliable for NVIDIA GPUs)
    try:
        import pynvml
        # Initialize NVIDIA Management Library
        pynvml.nvmlInit()
        device_count = pynvml.nvmlDeviceGetCount()
        
        # Iterate through each NVIDIA GPU
        for i in range(device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            gpu_info = {}
            
            # Get GPU name and set vendor
            name = pynvml.nvmlDeviceGetName(handle)
            gpu_info["GPU name"] = name.decode() if isinstance(name, bytes) else name
            gpu_info["GPU vendor"] = "NVIDIA"
            
            # Get memory information (total VRAM)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            gpu_info["GPU memory"] = f"{mem_info.total // 1024**3} GB"
            
            # Get maximum graphics clock frequency
            try:
                clock_mhz = pynvml.nvmlDeviceGetMaxClockInfo(handle, pynvml.NVML_CLOCK_GRAPHICS)
                gpu_info["GPU clock frequency"] = f"{clock_mhz / 1000:.2f} GHz"
            except:
                gpu_info["GPU clock frequency"] = "N/A"
            
            # Get L2 cache size
            gpu_info["GPU system level cache"] = get_nvidia_l2_cache(handle)
            
            # Estimate CUDA core count based on GPU model
            gpu_info["GPU core count"] = estimate_nvidia_cores(gpu_info["GPU name"])
            
            # Try to estimate memory bandwidth
            gpu_info["GPU bandwidth"] = "N/A"
            try:
                # Get memory bus width in bits
                bus_width = pynvml.nvmlDeviceGetMemoryBusWidth(handle)
                # Estimate bandwidth using GDDR6 assumption (14 Gbps effective per pin)
                # Bandwidth = (bus_width * data_rate) / 8 bits per byte
                if bus_width > 0:
                    bandwidth = (bus_width * 14) / 8  # GB/s
                    gpu_info["GPU bandwidth"] = f"{bandwidth:.1f} GB/s"
            except:
                pass
            
            # Calculate theoretical FLOPS (floating point operations per second)
            if gpu_info["GPU core count"] != "N/A":
                try:
                    cores_str = gpu_info["GPU core count"].replace("~", "")
                    cores = int(cores_str)
                    clock_ghz = float(gpu_info["GPU clock frequency"].split()[0])
                    # FLOPS = cores * clock_speed * operations_per_clock
                    # FMA (Fused Multiply-Add) = 2 operations per clock cycle
                    flops = cores * clock_ghz * 2
                    gpu_info["GPU FLOPS"] = f"{flops / 1000:.3f} TFLOPS"
                    gpu_info["GPU IPS"] = f"{flops / 1000:.3f} TIPS"
                except:
                    gpu_info["GPU FLOPS"] = "N/A"
                    gpu_info["GPU IPS"] = "N/A"
            else:
                gpu_info["GPU FLOPS"] = "N/A"
                gpu_info["GPU IPS"] = "N/A"
            
            # GPU family not readily available via pynvml
            gpu_info["GPU family"] = "N/A"
            
            gpus.append(gpu_info)
        
        # Clean up NVML
        pynvml.nvmlShutdown()
        return gpus
        
    except ImportError:
        # pynvml not installed, continue to other methods
        pass
    except Exception as e:
        # Other errors with pynvml, fall back to alternative methods
        pass
    
    # Method 2: Try AMD via rocm-smi
    if shutil.which("rocm-smi"):
        try:
            # Run rocm-smi with JSON output for AMD GPUs
            result = subprocess.run(
                ["rocm-smi", "--showproductname", "--showmeminfo", "vram", "--showid", "--json"],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse JSON output
            amd_data = json.loads(result.stdout)
            for gpu_id, gpu_data in amd_data.items():
                gpu_info = {
                    "GPU name": gpu_data.get("Product Name", "Unknown AMD GPU"),
                    "GPU vendor": "AMD",
                    "GPU memory": f"{int(gpu_data.get('VRAM Total Memory', 0)) // 1024**3} GB",
                    "GPU core count": "N/A",  # Difficult to extract from rocm-smi
                    "GPU clock frequency": "N/A",
                    "GPU bandwidth": "N/A",
                    "GPU FLOPS": "N/A",
                    "GPU IPS": "N/A",
                    "GPU system level cache": "N/A",
                    "GPU family": "N/A"
                }
                gpus.append(gpu_info)
            return gpus
        except:
            # rocm-smi failed, continue to fallback method
            pass
    
    # Method 3: Fallback to lspci (works for all GPU vendors but less detailed)
    if not shutil.which("lspci"):
        gpus.append({"Error": "lspci not found. Install pciutils package."})
        return gpus
    
    try:
        # List all PCI devices with verbose output
        result = subprocess.run(
            ["lspci", "-nn", "-D"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse lspci output to find GPU devices
        for line in result.stdout.strip().split("\n"):
            # Look for VGA controllers or display controllers
            if "VGA compatible controller" in line or "Display controller" in line:
                gpu_info = {}
                
                # Extract PCI device address (e.g., 0000:01:00.0)
                parts = line.split(" ")
                device_addr = parts[0]
                
                # Get detailed information for this specific device
                detail_result = subprocess.run(
                    ["lspci", "-vvs", device_addr],
                    capture_output=True,
                    text=True,
                    check=True
                )
                output = detail_result.stdout
                
                # Determine GPU vendor from output
                if "NVIDIA" in output:
                    gpu_info["GPU vendor"] = "NVIDIA"
                elif "AMD" in output or "ATI" in output:
                    gpu_info["GPU vendor"] = "AMD"
                elif "Intel" in output:
                    gpu_info["GPU vendor"] = "Intel"
                else:
                    gpu_info["GPU vendor"] = "Unknown"
                
                # Extract GPU name from the first line
                name_line = output.split("\n")[0]
                gpu_info["GPU name"] = name_line.split(device_addr)[1].split("(")[0].strip()
                
                # Try to extract memory size from lspci output
                gpu_info["GPU memory"] = "N/A"
                for detail_line in output.split("\n"):
                    if "Memory" in detail_line and "size=" in detail_line:
                        try:
                            size_part = detail_line.split("size=")[1].split("]")[0]
                            gpu_info["GPU memory"] = size_part
                        except:
                            pass
                        break
                
                # For AMD GPUs, try to get clock frequency from sysfs
                if gpu_info["GPU vendor"] == "AMD":
                    try:
                        # Iterate through DRM (Direct Rendering Manager) devices
                        for drm_file in os.listdir("/sys/class/drm/"):
                            if drm_file.startswith("card") and "-VGA" in drm_file:
                                gpu_path = f"/sys/class/drm/{drm_file}/device/"
                                # Read GPU clock states
                                if os.path.exists(gpu_path + "pp_dpm_sclk"):
                                    with open(gpu_path + "pp_dpm_sclk", "r") as f:
                                        clocks = f.read()
                                        # Extract the highest clock frequency
                                        gpu_info["GPU clock frequency"] = clocks.strip().split("\n")[-1].split(":")[1].strip()
                                break
                    except:
                        pass
                
                # Fill in remaining fields with N/A for lspci method
                gpu_info["GPU core count"] = "N/A"
                if "GPU clock frequency" not in gpu_info:
                    gpu_info["GPU clock frequency"] = "N/A"
                gpu_info["GPU bandwidth"] = "N/A"
                gpu_info["GPU FLOPS"] = "N/A"
                gpu_info["GPU IPS"] = "N/A"
                gpu_info["GPU system level cache"] = "N/A"
                gpu_info["GPU family"] = "N/A"
                
                gpus.append(gpu_info)
        
    except Exception as e:
        gpus.append({"Error": f"Failed to get Linux GPU info: {e}"})
    
    return gpus

def get_windows_gpu_info() -> List[Dict]:
    """
    Get GPU information on Windows using PowerShell and WMI.
    
    Uses the Win32_VideoController WMI class to retrieve GPU information
    through PowerShell commands.
    
    Returns:
        List of dictionaries containing GPU information for each detected GPU
    """
    gpus = []
    
    try:
        # PowerShell command to query WMI for video controller information
        ps_command = """
        Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM, VideoProcessor, CurrentClockSpeed, MaxClockSpeed | ConvertTo-Json
        """
        
        # Execute PowerShell command
        result = subprocess.run(
            ["powershell", "-Command", ps_command],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse JSON output
        data = json.loads(result.stdout)
        # Handle both single GPU (dict) and multiple GPUs (list)
        if isinstance(data, dict):
            data = [data]
        
        # Process each video controller
        for controller in data:
            gpu_info = {}
            
            # Extract GPU name
            name = controller.get("Name", "Unknown")
            gpu_info["GPU name"] = name
            
            # Determine vendor based on GPU name
            if "NVIDIA" in name.upper():
                gpu_info["GPU vendor"] = "NVIDIA"
            elif "AMD" in name.upper() or "ATI" in name.upper():
                gpu_info["GPU vendor"] = "AMD"
            elif "INTEL" in name.upper():
                gpu_info["GPU vendor"] = "Intel"
            else:
                gpu_info["GPU vendor"] = "Unknown"
            
            # Get GPU memory (VRAM) size
            adapter_ram = controller.get("AdapterRAM", 0)
            if adapter_ram:
                gpu_info["GPU memory"] = f"{adapter_ram // 1024**2} MB"
            else:
                gpu_info["GPU memory"] = "N/A"
            
            # Get clock frequency (prefer max, fall back to current)
            clock = controller.get("MaxClockSpeed", 0) or controller.get("CurrentClockSpeed", 0)
            if clock:
                # Clock speed is in MHz, convert to GHz
                gpu_info["GPU clock frequency"] = f"{clock / 1000:.2f} GHz"
            else:
                gpu_info["GPU clock frequency"] = "N/A"
            
            # Try to get additional details from Windows registry (placeholder)
            gpu_info["GPU system level cache"] = "N/A"
            try:
                # This would require proper registry parsing in a full implementation
                pass
            except:
                pass
            
            # Set remaining fields as unavailable (not easily accessible via WMI)
            gpu_info["GPU core count"] = "N/A"
            gpu_info["GPU bandwidth"] = "N/A"
            gpu_info["GPU FLOPS"] = "N/A"
            gpu_info["GPU IPS"] = "N/A"
            gpu_info["GPU family"] = "N/A"
            
            gpus.append(gpu_info)
        
    except Exception as e:
        gpus.append({"Error": f"Failed to get Windows GPU info: {e}"})
    
    return gpus

def print_gpu_info(gpus: List[Dict]):
    """
    Print GPU information in a formatted, human-readable way.
    
    Displays each GPU's specifications in a consistent order with proper
    formatting and spacing between multiple GPUs.
    
    Args:
        gpus: List of GPU information dictionaries to display
    """
    if not gpus:
        print("No GPU information available.")
        return
    
    # Iterate through each GPU
    for i, gpu in enumerate(gpus):
        # Add spacing between multiple GPUs
        if i > 0:
            print()  # Empty line between GPUs
        
        # If this entry is an error message, print it and continue
        if "Error" in gpu:
            print(f"Error: {gpu['Error']}")
            continue
        
        # Define the order in which fields should be displayed
        fields = [
            "GPU name", "GPU vendor", "GPU core count", "GPU clock frequency",
            "GPU bandwidth", "GPU FLOPS", "GPU IPS", "GPU system level cache",
            "GPU memory", "GPU family"
        ]
        
        # Print each field with its value
        for field in fields:
            print(f"{field}: {gpu.get(field, 'N/A')}")

def main():
    """
    Main entry point for the GPU information utility.
    
    Detects the operating system, calls the appropriate GPU detection function,
    and displays the results with timing information.
    """
    # Record start time for performance measurement
    start_time = time.time()
    
    # Detect the current operating system
    system = platform.system()
    
    # Call the appropriate function based on the operating system
    if system == "Darwin":  # macOS
        gpus = get_macos_gpu_info()
    elif system == "Linux":
        gpus = get_linux_gpu_info()
    elif system == "Windows":
        gpus = get_windows_gpu_info()
    else:
        # Unsupported operating system
        print(f"Unsupported platform: {system}")
        sys.exit(1)
    
    # Print build completion message with elapsed time
    elapsed = get_elapsed_time(start_time)
    print(f"Build of product 'gpuinfo' complete! ({elapsed})")
    print()
    
    # Display the collected GPU information
    print_gpu_info(gpus)

# Script entry point - only runs when executed directly (not imported)
if __name__ == "__main__":
    main()
