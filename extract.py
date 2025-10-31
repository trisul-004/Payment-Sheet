import os
from dotenv import load_dotenv
import google.generativeai as genai
import json

# --- Load API key ---
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
api_key = os.getenv("GEMINI_API_KEY") or os.getenv("api_key")

if not api_key:
    raise RuntimeError("Gemini API key not found. Set GEMINI_API_KEY in .env.")

genai.configure(api_key=api_key)

# --- Choose model ---
model = genai.GenerativeModel("models/gemini-2.0-flash")  # note the "models/" prefix


# --- Image path ---
image_path = "/Users/trisul/Desktop/Automation copy/WhatsApp Image 2025-10-31 at 15.18.48.jpeg"

# --- Prompt for extraction ---
prompt = """
Extract the following details from the payment screenshot and return ONLY valid JSON:

{
  "amount": number,
  "currency": "string",
  "date": "YYYY-MM-DD",
  "time": "HH:MM",
  "paid_to": "string",
  "paid_to_email": "string (if any)",
  "payment_status": "string (if any)",
  "payment_method": "string (if any)"
}
"""

# --- Send to Gemini ---
response = model.generate_content(
    [prompt, {"mime_type": "image/jpeg", "data": open(image_path, "rb").read()}]
)


# --- Extract and parse JSON ---
raw_output = response.text.strip()

try:
    data = json.loads(raw_output)
except json.JSONDecodeError:
    print("⚠️ Invalid JSON — raw output below:\n", raw_output)
    data = None

print("\n✅ Extracted JSON Data:")
print(json.dumps(data, indent=2))
