# Project: BB (ready-to-run)

Quick steps to run locally (Windows PowerShell):

1. Create and activate a virtual environment:

```powershell
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
```

2. Install dependencies (optional — heavy models like `transformers` and `torch` are large):

```powershell
pip install -r requirements.txt
```

3. Run the test runner:

```powershell
& .\.venv\Scripts\python.exe run_translation_test.py
```

Notes:
- The code gracefully falls back to lightweight TF-IDF summarization and `googletrans` if heavy libs are not installed.
- If you want GPU acceleration, install a CUDA-enabled `torch` build per your GPU.
