# Windows Benchmarking Setup Guide

Complete guide to clone the repo and run M4 benchmarks on Windows.

---

## 📋 Prerequisites

- **Windows 10/11** (64-bit)
- **Git** (download from https://git-scm.com/download/win)
- **Python 3.11+** (download from https://www.python.org/downloads/)
- **NVIDIA GPU** (optional but recommended) with CUDA support
- **~50GB free disk space** (for models + results)
- **Minimum 16GB RAM**

---

## 🚀 Step 1: Install Requirements

### 1.1 Install Git
```powershell
# Download and install from: https://git-scm.com/download/win
# Run installer with default settings
# Verify installation:
git --version
```

### 1.2 Install Python 3.11+
```powershell
# Download from: https://www.python.org/downloads/
# IMPORTANT: Check "Add Python to PATH" during installation
# Verify installation:
python --version
pip --version
```

### 1.3 Install CUDA Toolkit (Optional but Recommended for GPU)
```powershell
# For NVIDIA GPU support:
# Download from: https://developer.nvidia.com/cuda-toolkit-archive
# Install CUDA 12.x (latest stable)
# Install cuDNN matching your CUDA version
```

---

## 📦 Step 2: Clone Repository

```powershell
# Open PowerShell or Command Prompt
# Navigate to where you want the project (e.g., C:\Projects)
cd C:\Projects

# Clone the repository
git clone https://github.com/yourusername/291_EAI.git
cd 291_EAI

# Verify structure
dir  # Should show: android, scripts, vendor, analysis, etc.
```

---

## 🔧 Step 3: Install Python Dependencies

```powershell
# Create virtual environment (recommended)
python -m venv venv

# Activate virtual environment
# On PowerShell:
.\venv\Scripts\Activate.ps1
# On Command Prompt:
venv\Scripts\activate.bat

# Install requirements
pip install --upgrade pip
pip install numpy scipy matplotlib pandas

# Install llama-cpp-python (CPU by default)
pip install llama-cpp-python

# For GPU support (NVIDIA):
pip install llama-cpp-python --force-reinstall --no-cache-dir --compile=WITH_CUDA
```

---

## 📥 Step 4: Download Models

```powershell
# Create models directory
mkdir local-models\llama3_2_3b_gguf
cd local-models\llama3_2_3b_gguf

# Download Llama-3.2-3B-Instruct GGUF models
# From HuggingFace: https://huggingface.co/lmstudio-community/Llama-3.2-3B-Instruct-GGUF

# Download these files:
# - Llama-3.2-3B-Instruct-Q2_K.gguf  (~800 MB)
# - Llama-3.2-3B-Instruct-Q3_K_M.gguf (~1.0 GB)
# - Llama-3.2-3B-Instruct-Q4_K_S.gguf (~1.3 GB)
# - Llama-3.2-3B-Instruct-Q4_K_M.gguf (~1.5 GB)
# - Llama-3.2-3B-Instruct-Q5_K_M.gguf (~1.8 GB)
# - Llama-3.2-3B-Instruct-Q6_K.gguf  (~2.2 GB)
# - Llama-3.2-3B-Instruct-Q8_0.gguf  (~3.0 GB)

# Using wget (if installed) or PowerShell:
# Example with PowerShell:
$url = "https://huggingface.co/.../Llama-3.2-3B-Instruct-Q2_K.gguf/resolve/main/..."
Invoke-WebRequest -Uri $url -OutFile "Llama-3.2-3B-Instruct-Q2_K.gguf"

# Or download manually via browser and place in this directory
cd ..\..\
```

---

## 🔨 Step 5: Build llama.cpp (Optional but Recommended for Best Performance)

```powershell
# Navigate to vendor directory
cd vendor\llama.cpp

# Build with CMake (if you have CMake installed)
mkdir build
cd build

# For CPU only:
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release

# For NVIDIA GPU:
cmake .. -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON
cmake --build . --config Release

# For AMD GPU (ROCm):
cmake .. -DCMAKE_BUILD_TYPE=Release -DGGML_HIP=ON
cmake --build . --config Release

# Navigate back to project root
cd ..\..\..\
```

---

## 🏃 Step 6: Run Benchmarks

### Option A: CPU Benchmark
```powershell
# GPU disabled, CPU only
$env:LLAMA_CPU = "1"

# Run benchmark
python scripts/benchmark_windows_cpu.py `
  --models local-models/llama3_2_3b_gguf `
  --output results/windows_cpu_benchmark.json `
  --variants Q2_K Q3_K_M Q4_K_M Q5_K_M Q6_K Q8_0 `
  --threads 8
```

### Option B: GPU Benchmark (NVIDIA)
```powershell
# Run with GPU acceleration
python scripts/benchmark_windows_gpu.py `
  --models local-models/llama3_2_3b_gguf `
  --output results/windows_gpu_benchmark.json `
  --variants Q2_K Q3_K_M Q4_K_M Q5_K_M Q6_K Q8_0 `
  --gpu 0
```

### Option C: Create Windows Benchmark Script

If the above scripts don't exist, create one:

**scripts/benchmark_windows_cpu.py:**
```python
#!/usr/bin/env python3
import os
import json
import argparse
from pathlib import Path
from llama_cpp import Llama

def benchmark_variant(model_path, variant, contexts=[256, 512, 1024, 2048]):
    """Benchmark single variant across contexts"""
    results = []
    
    print(f"Loading {variant}...")
    model = Llama(
        model_path=str(model_path),
        n_ctx=2048,
        n_threads=8,
        verbose=False
    )
    
    for ctx in contexts:
        print(f"  Context: {ctx}...", end="", flush=True)
        
        # Run 15 trials
        for trial in range(15):
            output_tokens = 128
            prompt = "The future of artificial intelligence is"
            
            response = model.create_completion(
                prompt=prompt,
                max_tokens=output_tokens,
                temperature=0.7
            )
            
            # Extract timing if available
            if 'usage' in response:
                tokens = response['usage'].get('completion_tokens', output_tokens)
                time_ms = response.get('timings', {}).get('total_ms', 0)
                tps = (tokens / time_ms * 1000) if time_ms > 0 else 0
            else:
                tps = 0
            
            results.append({
                "variant": variant,
                "context": ctx,
                "trial": trial + 1,
                "tps": tps,
                "model": model_path.name
            })
        
        print(" ✓")
    
    model.__del__()
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--variants", nargs="+", default=["Q2_K", "Q3_K_M", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"])
    parser.add_argument("--threads", type=int, default=8)
    args = parser.parse_args()
    
    model_dir = Path(args.models)
    results = []
    
    for variant in args.variants:
        model_file = model_dir / f"Llama-3.2-3B-Instruct-{variant}.gguf"
        if model_file.exists():
            print(f"\nBenchmarking {variant}...")
            results.extend(benchmark_variant(model_file, variant))
        else:
            print(f"⚠️  {model_file} not found - skipping")
    
    # Save results
    output_file = Path(args.output)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✅ Results saved to {output_file}")

if __name__ == "__main__":
    main()
```

Run it:
```powershell
python scripts/benchmark_windows_cpu.py `
  --models local-models/llama3_2_3b_gguf `
  --output results/windows_cpu_benchmark.json `
  --threads 8
```

---

## 📊 Step 7: Monitor & Collect Results

```powershell
# Check results directory
dir results\

# View results
type results\windows_cpu_benchmark.json | more

# Transfer back to Mac (if needed)
# Using SCP or copy to cloud storage
```

---

## 🐛 Troubleshooting

### Issue: Python not found
```powershell
# Make sure Python is in PATH
python --version

# If not, add manually:
# Go to: System Properties → Environment Variables
# Add Python installation path to PATH
```

### Issue: llama-cpp-python installation fails
```powershell
# Try with specific version
pip install llama-cpp-python==0.2.75 --no-cache-dir

# Or use pre-built wheel
pip install https://files.pythonhosted.org/...
```

### Issue: CUDA not detected
```powershell
# Verify CUDA installation
nvcc --version

# If not found, reinstall CUDA toolkit
# Make sure cuDNN is also installed in CUDA path
```

### Issue: Low memory
```powershell
# Use smaller context and batch sizes
# Modify benchmark script to use:
# --ctx-size 512 (instead of 2048)
# --batch-size 128 (instead of 512)
```

---

## ✅ Verification Checklist

- [ ] Git installed and working
- [ ] Python 3.11+ installed
- [ ] Virtual environment activated
- [ ] Dependencies installed
- [ ] Models downloaded (check file sizes)
- [ ] First benchmark test runs without error
- [ ] Results saved to JSON

---

## 📈 Expected Performance

**Windows CPU (typical):**
- Q2_K: 5-15 tok/s
- Q4_K_M: 3-8 tok/s
- Q6_K: 2-5 tok/s
- Q8_0: 1-3 tok/s

**Windows GPU (NVIDIA RTX 3080+):**
- Q2_K: 50-100 tok/s
- Q4_K_M: 30-60 tok/s
- Q6_K: 20-40 tok/s
- Q8_0: 10-20 tok/s

---

## 🔗 Useful Resources

- **llama.cpp:** https://github.com/ggerganov/llama.cpp
- **llama-cpp-python:** https://github.com/abetlen/llama-cpp-python
- **Models:** https://huggingface.co/lmstudio-community/Llama-3.2-3B-Instruct-GGUF
- **CUDA Toolkit:** https://developer.nvidia.com/cuda-toolkit-archive
- **CMake:** https://cmake.org/download/

