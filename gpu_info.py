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
    """Format elapsed time string."""
    elapsed = time.time() - start_time
    return f"{elapsed:.2f}s"

def get_macos_gpu_info() -> List[Dict]:
    """Get GPU information on macOS."""
    gpus = []
    
    # Known Apple Silicon specs (chip: (cores, clock_ghz, bandwidth_gbs, cache_mb))
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
        result = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True,
            text=True,
            check=True
        )
        
        data = json.loads(result.stdout)
        displays = data.get("SPDisplaysDataType", [])
        
        for display in displays:
            gpu_info = {}
            
            # Basic GPU information
            gpu_info["GPU name"] = display.get("_name", "Unknown")
            gpu_info["GPU vendor"] = display.get("sppci_vendor", "Apple")
            
            # GPU core count (Apple Silicon)
            gpu_info["GPU core count"] = display.get("sppci_cores", "N/A")
            
            # Metal GPU family
            gpu_info["GPU family"] = display.get("spdisplays_mtlgpufamilysupport", "N/A")
            
            # VRAM
            gpu_info["GPU memory"] = display.get("spdisplays_vram", "N/A")
            
            # Try to get cache and clock from known specs
            gpu_name = gpu_info["GPU name"]
            found_specs = False
            for chip, (cores, clock, bandwidth, cache) in APPLE_SILICON_SPECS.items():
                if chip in gpu_name:
                    gpu_info["GPU system level cache"] = f"{cache} MB"
                    gpu_info["GPU clock frequency"] = f"{clock:.2f} GHz"
                    gpu_info["GPU bandwidth"] = f"{bandwidth:.1f} GB/s"
                    
                    # Recalculate FLOPS with actual clock
                    if gpu_info["GPU core count"] != "N/A":
                        try:
                            actual_cores = int(gpu_info["GPU core count"])
                            alus_per_core = 128  # Apple GPU architecture
                            flops = actual_cores * clock * alus_per_core * 2  # FMA = 2 ops
                            gpu_info["GPU FLOPS"] = f"{flops / 1000:.3f} TFLOPS"
                            gpu_info["GPU IPS"] = f"{flops / 1000:.3f} TIPS"
                        except:
                            gpu_info["GPU FLOPS"] = "N/A"
                            gpu_info["GPU IPS"] = "N/A"
                    found_specs = True
                    break
            
            if not found_specs:
                # Fallback to sysctl for cache
                try:
                    cache_result = subprocess.run(
                        ["sysctl", "-n", "hw.l2cache"],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    cache_bytes = int(cache_result.stdout.strip())
                    gpu_info["GPU system level cache"] = f"{cache_bytes // 1024 // 1024} MB"
                except:
                    gpu_info["GPU system level cache"] = "N/A"
                
                gpu_info["GPU clock frequency"] = "N/A"
                gpu_info["GPU bandwidth"] = "N/A"
            
            gpus.append(gpu_info)
            
    except Exception as e:
        gpus.append({"Error": f"Failed to get macOS GPU info: {e}"})
    
    return gpus

def estimate_nvidia_cores(gpu_name: str) -> str:
    """Estimate NVIDIA GPU core count from model name."""
    name_upper = gpu_name.upper()
    core_estimates = {
        "4090": "16384", "4080": "9728", "4070 Ti": "7680", "4070": "5888", "4060 Ti": "4352", "4060": "3072",
        "3090 Ti": "10752", "3090": "10496", "3080 Ti": "10240", "3080": "8704", "3070 Ti": "6144", "3070": "5888", "3060 Ti": "4864", "3060": "3584", "3050": "2560",
        "2080 Ti": "4352", "2080 Super": "3072", "2080": "2944", "2070 Super": "2560", "2070": "2304", "2060 Super": "2176", "2060": "1920",
        "1660 Super": "1408", "1660 Ti": "1536", "1660": "1408", "1650 Super": "1280", "1650": "896",
        "TITAN RTX": "4608", "TITAN V": "5120", "TITAN Xp": "3840",
        "A100": "6912", "A40": "10752", "A30": "3584", "A16": "5120", "A10": "9216",
        "V100": "5120", "P100": "3584", "T4": "2560",
    }
    
    # Check for specific models first
    for model, cores in core_estimates.items():
        if model in gpu_name:
            return cores
    
    # Default estimates based on series
    if any(x in name_upper for x in ["RTX 40", "RTX 30"]):
        return "~4000"
    elif any(x in name_upper for x in ["RTX 20", "GTX 16"]):
        return "~2000"
    elif "GTX 10" in name_upper:
        return "~1500"
    return "N/A"

def get_nvidia_l2_cache(handle) -> str:
    """Get NVIDIA L2 cache size using pynvml if available."""
    try:
        import pynvml
        cache_kb = pynvml.nvmlDeviceGetL2CacheSize(handle)
        return f"{cache_kb // 1024} MB"
    except:
        return "N/A"

def get_linux_gpu_info() -> List[Dict]:
    """Get GPU information on Linux."""
    gpus = []
    
    # Try NVIDIA via pynvml first (most reliable)
    try:
        import pynvml
        pynvml.nvmlInit()
        device_count = pynvml.nvmlDeviceGetCount()
        
        for i in range(device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            gpu_info = {}
            
            # Name and vendor
            name = pynvml.nvmlDeviceGetName(handle)
            gpu_info["GPU name"] = name.decode() if isinstance(name, bytes) else name
            gpu_info["GPU vendor"] = "NVIDIA"
            
            # Memory
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            gpu_info["GPU memory"] = f"{mem_info.total // 1024**3} GB"
            
            # Clock frequency
            try:
                clock_mhz = pynvml.nvmlDeviceGetMaxClockInfo(handle, pynvml.NVML_CLOCK_GRAPHICS)
                gpu_info["GPU clock frequency"] = f"{clock_mhz / 1000:.2f} GHz"
            except:
                gpu_info["GPU clock frequency"] = "N/A"
            
            # L2 Cache
            gpu_info["GPU system level cache"] = get_nvidia_l2_cache(handle)
            
            # CUDA cores
            gpu_info["GPU core count"] = estimate_nvidia_cores(gpu_info["GPU name"])
            
            # Memory bandwidth (estimated from memory and bus width if possible)
            gpu_info["GPU bandwidth"] = "N/A"
            try:
                # Try to get memory bus width
                bus_width = pynvml.nvmlDeviceGetMemoryBusWidth(handle)
                # For GDDR6, bandwidth = bus_width * memory_clock * 2 (DDR) / 8
                # This is a rough estimate
                if bus_width > 0:
                    # Assume GDDR6 at 14 Gbps per pin
                    bandwidth = (bus_width * 14) / 8  # GB/s
                    gpu_info["GPU bandwidth"] = f"{bandwidth:.1f} GB/s"
            except:
                pass
            
            # Calculate FLOPS
            if gpu_info["GPU core count"] != "N/A":
                try:
                    cores_str = gpu_info["GPU core count"].replace("~", "")
                    cores = int(cores_str)
                    clock_ghz = float(gpu_info["GPU clock frequency"].split()[0])
                    flops = cores * clock_ghz * 2  # FMA = 2 ops per clock
                    gpu_info["GPU FLOPS"] = f"{flops / 1000:.3f} TFLOPS"
                    gpu_info["GPU IPS"] = f"{flops / 1000:.3f} TIPS"
                except:
                    gpu_info["GPU FLOPS"] = "N/A"
                    gpu_info["GPU IPS"] = "N/A"
            else:
                gpu_info["GPU FLOPS"] = "N/A"
                gpu_info["GPU IPS"] = "N/A"
            
            # GPU family
            gpu_info["GPU family"] = "N/A"
            
            gpus.append(gpu_info)
        
        pynvml.nvmlShutdown()
        return gpus
        
    except ImportError:
        pass
    except Exception as e:
        # Don't return here, fall back to other methods
        pass
    
    # Try AMD via rocm-smi
    if shutil.which("rocm-smi"):
        try:
            result = subprocess.run(
                ["rocm-smi", "--showproductname", "--showmeminfo", "vram", "--showid", "--json"],
                capture_output=True,
                text=True,
                check=True
            )
            
            amd_data = json.loads(result.stdout)
            for gpu_id, gpu_data in amd_data.items():
                gpu_info = {
                    "GPU name": gpu_data.get("Product Name", "Unknown AMD GPU"),
                    "GPU vendor": "AMD",
                    "GPU memory": f"{int(gpu_data.get('VRAM Total Memory', 0)) // 1024**3} GB",
                    "GPU core count": "N/A",  # Hard to get from rocm-smi
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
            pass
    
    # Fallback: Use lspci
    if not shutil.which("lspci"):
        gpus.append({"Error": "lspci not found. Install pciutils package."})
        return gpus
    
    try:
        result = subprocess.run(
            ["lspci", "-nn", "-D"],
            capture_output=True,
            text=True,
            check=True
        )
        
        for line in result.stdout.strip().split("\n"):
            if "VGA compatible controller" in line or "Display controller" in line:
                gpu_info = {}
                
                # Extract device address
                parts = line.split(" ")
                device_addr = parts[0]
                
                # Get detailed info
                detail_result = subprocess.run(
                    ["lspci", "-vvs", device_addr],
                    capture_output=True,
                    text=True,
                    check=True
                )
                output = detail_result.stdout
                
                # Determine vendor
                if "NVIDIA" in output:
                    gpu_info["GPU vendor"] = "NVIDIA"
                elif "AMD" in output or "ATI" in output:
                    gpu_info["GPU vendor"] = "AMD"
                elif "Intel" in output:
                    gpu_info["GPU vendor"] = "Intel"
                else:
                    gpu_info["GPU vendor"] = "Unknown"
                
                # Extract name
                name_line = output.split("\n")[0]
                gpu_info["GPU name"] = name_line.split(device_addr)[1].split("(")[0].strip()
                
                # Try to extract memory size
                gpu_info["GPU memory"] = "N/A"
                for detail_line in output.split("\n"):
                    if "Memory" in detail_line and "size=" in detail_line:
                        try:
                            size_part = detail_line.split("size=")[1].split("]")[0]
                            gpu_info["GPU memory"] = size_part
                        except:
                            pass
                        break
                
                # Try to get more info from /sys/class/drm/
                if gpu_info["GPU vendor"] == "AMD":
                    try:
                        # Look for amdgpu info
                        for drm_file in os.listdir("/sys/class/drm/"):
                            if drm_file.startswith("card") and "-VGA" in drm_file:
                                gpu_path = f"/sys/class/drm/{drm_file}/device/"
                                if os.path.exists(gpu_path + "pp_dpm_sclk"):
                                    with open(gpu_path + "pp_dpm_sclk", "r") as f:
                                        clocks = f.read()
                                        # Extract highest clock
                                        gpu_info["GPU clock frequency"] = clocks.strip().split("\n")[-1].split(":")[1].strip()
                                break
                    except:
                        pass
                
                # Fill remaining fields
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
    """Get GPU information on Windows."""
    gpus = []
    
    try:
        # Use PowerShell to get detailed GPU info
        ps_command = """
        Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM, VideoProcessor, CurrentClockSpeed, MaxClockSpeed | ConvertTo-Json
        """
        
        result = subprocess.run(
            ["powershell", "-Command", ps_command],
            capture_output=True,
            text=True,
            check=True
        )
        
        data = json.loads(result.stdout)
        if isinstance(data, dict):
            data = [data]  # Convert single GPU to list
        
        for controller in data:
            gpu_info = {}
            
            # Name and vendor
            name = controller.get("Name", "Unknown")
            gpu_info["GPU name"] = name
            
            # Determine vendor
            if "NVIDIA" in name.upper():
                gpu_info["GPU vendor"] = "NVIDIA"
            elif "AMD" in name.upper() or "ATI" in name.upper():
                gpu_info["GPU vendor"] = "AMD"
            elif "INTEL" in name.upper():
                gpu_info["GPU vendor"] = "Intel"
            else:
                gpu_info["GPU vendor"] = "Unknown"
            
            # Memory
            adapter_ram = controller.get("AdapterRAM", 0)
            if adapter_ram:
                gpu_info["GPU memory"] = f"{adapter_ram // 1024**2} MB"
            else:
                gpu_info["GPU memory"] = "N/A"
            
            # Clock frequency (in MHz)
            clock = controller.get("MaxClockSpeed", 0) or controller.get("CurrentClockSpeed", 0)
            if clock:
                gpu_info["GPU clock frequency"] = f"{clock / 1000:.2f} GHz"
            else:
                gpu_info["GPU clock frequency"] = "N/A"
            
            # Try to get more details from registry
            gpu_info["GPU system level cache"] = "N/A"
            try:
                # This is a simplified approach - real implementation would need proper registry parsing
                pass
            except:
                pass
            
            # Other fields
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
    """Print GPU information in a formatted way."""
    if not gpus:
        print("No GPU information available.")
        return
    
    for i, gpu in enumerate(gpus):
        if i > 0:
            print()  # Empty line between GPUs
        
        if "Error" in gpu:
            print(f"Error: {gpu['Error']}")
            continue
        
        # Print each field in consistent order
        fields = [
            "GPU name", "GPU vendor", "GPU core count", "GPU clock frequency",
            "GPU bandwidth", "GPU FLOPS", "GPU IPS", "GPU system level cache",
            "GPU memory", "GPU family"
        ]
        
        for field in fields:
            print(f"{field}: {gpu.get(field, 'N/A')}")

def main():
    """Main function to detect platform and get GPU info."""
    start_time = time.time()
    
    # Detect platform
    system = platform.system()
    
    if system == "Darwin":
        gpus = get_macos_gpu_info()
    elif system == "Linux":
        gpus = get_linux_gpu_info()
    elif system == "Windows":
        gpus = get_windows_gpu_info()
    else:
        print(f"Unsupported platform: {system}")
        sys.exit(1)
    
    # Print build completion message
    elapsed = get_elapsed_time(start_time)
    print(f"Build of product 'gpuinfo' complete! ({elapsed})")
    print()
    
    # Print GPU information
    print_gpu_info(gpus)

if __name__ == "__main__":
    main()
