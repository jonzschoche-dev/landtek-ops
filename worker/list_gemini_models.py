"""List Gemini models accessible by the configured API key."""
import sys, requests, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from config import GEMINI_API_KEY

r = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}",
                 timeout=30)
r.raise_for_status()
models = r.json().get("models", [])
print(f"{len(models)} models accessible:\n")
for m in models:
    name = m.get("name", "")
    methods = m.get("supportedGenerationMethods", [])
    if "generateContent" in methods:
        print(f"  {name}")
print("\n(only models supporting generateContent listed)")
