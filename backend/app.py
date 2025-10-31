from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import google.generativeai as genai
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import re

# --- Initialize Flask ---
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*", "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"], "allow_headers": ["Content-Type"]}})

# --- Load environment variables ---
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY not found in .env file")

genai.configure(api_key=api_key)

# --- Database connection (Neon) ---
DB_URL = "postgresql://neondb_owner:npg_YZD7mnW5MsRE@ep-tiny-dream-a1q6t4ge-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

def get_db_connection():
    conn = psycopg2.connect(DB_URL)
    return conn

# --- Create table if not exists ---
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS extracted_data (
            id SERIAL PRIMARY KEY,
            amount FLOAT,
            currency VARCHAR(20),
            date VARCHAR(20),
            time VARCHAR(20),
            paid_to VARCHAR(100),
            paid_to_email VARCHAR(100),
            payment_status VARCHAR(50),
            payment_method VARCHAR(50),
            site VARCHAR(100)
        );
    """)
    # Add site column if it doesn't exist (for existing tables)
    cur.execute("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'extracted_data' AND column_name = 'site'
            ) THEN
                ALTER TABLE extracted_data ADD COLUMN site VARCHAR(100);
            END IF;
        END $$;
    """)
    conn.commit()
    cur.close()
    conn.close()

init_db()  # ✅ Auto-create table on startup

# --- Gemini model setup ---
model = genai.GenerativeModel("models/gemini-2.0-flash")

# --- Routes ---
@app.route("/extract", methods=["POST"])
def extract_data():
    if "images" not in request.files:
        return jsonify({"error": "No images uploaded"}), 400

    files = request.files.getlist("images")
    results = []

    prompt = """
    Extract the following details from the payment screenshot and return ONLY valid JSON.
    Ensure your response strictly follows this format:
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
    Do not include explanations or additional text.
    """

    conn = get_db_connection()
    cur = conn.cursor()

    for file in files:
        try:
            image_data = file.read()
            response = model.generate_content(
                [prompt, {"mime_type": file.mimetype, "data": image_data}]
            )

            raw_output = response.text.strip()
            match = re.search(r"\{.*\}", raw_output, re.DOTALL)
            if not match:
                print(f"⚠️ No JSON detected in {file.filename}")
                continue

            json_text = match.group(0)
            try:
                data = json.loads(json_text)
            except json.JSONDecodeError:
                print(f"⚠️ Invalid JSON after cleaning for {file.filename}")
                continue

            # Insert extracted data into database
            cur.execute(
                """
                INSERT INTO extracted_data 
                (amount, currency, date, time, paid_to, paid_to_email, payment_status, payment_method, site)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    data.get("amount"),
                    data.get("currency"),
                    data.get("date"),
                    data.get("time"),
                    data.get("paid_to"),
                    data.get("paid_to_email"),
                    data.get("payment_status"),
                    data.get("payment_method"),
                    None,  # site is NULL by default, user can fill it manually
                ),
            )

            results.append({
                "filename": file.filename,
                "data": data
            })

        except Exception as e:
            print(f"❌ Error processing {file.filename}: {e}")
            continue

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "Extraction complete", "results": results})


@app.route("/data", methods=["GET"])
def get_data():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM extracted_data ORDER BY id DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(rows)


@app.route("/data/<int:record_id>/site", methods=["PUT", "OPTIONS"])
def update_site(record_id):
    if request.method == "OPTIONS":
        response = jsonify({})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "PUT, OPTIONS")
        return response
    
    try:
        data = request.get_json()
        site = data.get("site", "")
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE extracted_data SET site = %s WHERE id = %s",
            (site, record_id)
        )
        conn.commit()
        
        if cur.rowcount == 0:
            cur.close()
            conn.close()
            return jsonify({"error": "Record not found"}), 404
        
        cur.close()
        conn.close()
        return jsonify({"message": "Site updated successfully", "id": record_id, "site": site})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/data/<int:record_id>", methods=["PUT", "OPTIONS", "DELETE"])
def update_or_delete_record(record_id):
    if request.method == "OPTIONS":
        response = jsonify({})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "PUT, DELETE, OPTIONS")
        return response, 200
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        if request.method == "DELETE":
            cur.execute("DELETE FROM extracted_data WHERE id = %s", (record_id,))
            conn.commit()
            
            if cur.rowcount == 0:
                cur.close()
                conn.close()
                return jsonify({"error": "Record not found"}), 404
            
            cur.close()
            conn.close()
            return jsonify({"message": "Record deleted successfully", "id": record_id})
        
        elif request.method == "PUT":
            data = request.get_json()
            
            cur.execute(
                """
                UPDATE extracted_data 
                SET amount = %s, currency = %s, date = %s, time = %s,
                    paid_to = %s, paid_to_email = %s, payment_status = %s,
                    payment_method = %s, site = %s
                WHERE id = %s
                """,
                (
                    data.get("amount"),
                    data.get("currency"),
                    data.get("date"),
                    data.get("time"),
                    data.get("paid_to"),
                    data.get("paid_to_email"),
                    data.get("payment_status"),
                    data.get("payment_method"),
                    data.get("site"),
                    record_id,
                ),
            )
            conn.commit()
            
            if cur.rowcount == 0:
                cur.close()
                conn.close()
                return jsonify({"error": "Record not found"}), 404
            
            # Get updated record
            cur.execute("SELECT * FROM extracted_data WHERE id = %s", (record_id,))
            updated_record = cur.fetchone()
            
            cur.close()
            conn.close()
            return jsonify({"message": "Record updated successfully", "data": updated_record})
    except Exception as e:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
