import google.generativeai as genai
from dotenv import load_dotenv
import os

# Load API key
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
api_key = os.getenv("GEMINI_API_KEY") or os.getenv("api_key")
genai.configure(api_key=api_key)

# List all available models
print("✅ Available Gemini models:\n")
for model in genai.list_models():
    if "generateContent" in model.supported_generation_methods:
        print(f"- {model.name}")
