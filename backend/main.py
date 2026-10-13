import sys
import os
import csv
import base64
import traceback
import socket
import tempfile
import time
from pathlib import Path
from datetime import datetime
from urllib.parse import quote_plus

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# 1. Gemini Client Setup
# ---------------------------------------------------------------------------
GEMINI_API_KEY = "genai.configure(api_key="YOUR_API_KEY_HERE")"
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(timeout=60000)
)

# ---------------------------------------------------------------------------
# 2. Path Resolution (PyInstaller Safe)
# ---------------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    # When running as compiled .exe
    base_dir = Path(sys._MEIPASS)
    exe_dir = Path(sys.executable).parent
else:
    # When running as normal python script
    base_dir = Path(__file__).resolve().parent
    exe_dir = base_dir

www_dir = base_dir / "www"
csv_file_path = exe_dir / "inventory_log.csv"

if not csv_file_path.exists():
    with open(csv_file_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Board ID", "Device Type", "Brand", "Model", "Notes"])

# ---------------------------------------------------------------------------
# 3. FastAPI App Configuration
# ---------------------------------------------------------------------------
app = FastAPI(title="Circuit Board Scanner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

class ImageScanRequest(BaseModel):
    image_data: str

def process_gemini_analysis(image_bytes: bytes, mime_type: str) -> str:
    prompt = (
        "Analyze this circuit board image carefully. "
        "Identify the board part number/board ID, the type of device it belongs to (e.g., TV Power Supply, Washer Main Board), "
        "the brand, and the specific model number if visible. "
        "Respond strictly in the following format:\n"
        "Board ID: <id or Unknown>\n"
        "Device Type: <type or Unknown>\n"
        "Brand: <brand or Unknown>\n"
        "Model: <model or Unknown>\n"
        "Notes: <brief descriptive details or component identifiers>"
    )

    ext = ".jpg" if "jpeg" in mime_type else ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_img_file:
        temp_img_file.write(image_bytes)
        temp_path = temp_img_file.name

    try:
        print("\n--> [GEMINI] Uploading image via Google File API...")
        uploaded_file = client.files.upload(file=temp_path)
        print(f"--> [GEMINI] Upload successful! URI: {uploaded_file.uri}")
        
        candidate_models = ["gemini-3.8-flash", "gemini-3.5-flash"]
        max_retries = 2
        last_err = None

        for model_name in candidate_models:
            for attempt in range(max_retries):
                try:
                    print(f"--> [GEMINI] Requesting analysis from '{model_name}' (Attempt {attempt + 1}/{max_retries})...")
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[uploaded_file, prompt]
                    )
                    if response and response.text:
                        print(f"--> [GEMINI] Success using model '{model_name}' on attempt {attempt + 1}!")
                        return response.text
                except Exception as m_err:
                    error_msg = str(m_err)
                    print(f"--> [GEMINI WARN] Model '{model_name}' attempt {attempt + 1} failed: {error_msg}")
                    last_err = m_err
                    
                    if "503" in error_msg or "UNAVAILABLE" in error_msg or "504" in error_msg or "DEADLINE_EXCEEDED" in error_msg:
                        if attempt < max_retries - 1:
                            print("--> [GEMINI] Servers are busy/timeout. Waiting 3 seconds before retrying...")
                            time.sleep(3)
                            continue
                    break # Break retry loop if it's a fatal error or out of retries for this model
            
            print(f"--> [GEMINI] Moving to backup model if available...")

        raise RuntimeError(f"All Gemini models failed. Last error: {last_err}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# ---------------------------------------------------------------------------
# 4. Identification Endpoint
# ---------------------------------------------------------------------------
@app.post("/api/identify-board")
async def identify_board(request: ImageScanRequest):
    print("\n[STEP 1/5] Received identification request from frontend.")
    try:
        raw_data = request.image_data
        if "," in raw_data:
            header, base64_str = raw_data.split(",", 1)
            mime_type = header.split(";")[0].split(":")[1]
        else:
            base64_str = raw_data
            mime_type = "image/jpeg"

        print(f"[STEP 2/5] Image decoded ({len(base64_str)} chars). Moving to Gemini Processing...")
        image_bytes = base64.b64decode(base64_str)

        analysis_text = await run_in_threadpool(process_gemini_analysis, image_bytes, mime_type)

        print("[STEP 3/5] Gemini analysis completed successfully:")
        print("--------------------------------------------------")
        print(analysis_text)
        print("--------------------------------------------------")

        parsed_data = {
            "board_id": "Unknown",
            "device_type": "Unknown",
            "brand": "Unknown",
            "model": "Unknown",
            "notes": "None"
        }

        for line in analysis_text.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                key_clean = key.strip().lower()
                val_clean = val.strip()
                if "board id" in key_clean:
                    parsed_data["board_id"] = val_clean
                elif "device type" in key_clean:
                    parsed_data["device_type"] = val_clean
                elif "brand" in key_clean:
                    parsed_data["brand"] = val_clean
                elif "model" in key_clean:
                    parsed_data["model"] = val_clean
                elif "notes" in key_clean:
                    parsed_data["notes"] = val_clean

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(csv_file_path, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp,
                parsed_data["board_id"],
                parsed_data["device_type"],
                parsed_data["brand"],
                parsed_data["model"],
                parsed_data["notes"]
            ])
        print("[STEP 4/5] Logged scan to inventory_log.csv.")

        search_terms = []
        if parsed_data["brand"] != "Unknown":
            search_terms.append(parsed_data["brand"])
        if parsed_data["board_id"] != "Unknown":
            search_terms.append(parsed_data["board_id"])
        if parsed_data["model"] != "Unknown":
            search_terms.append(parsed_data["model"])

        query_str = " ".join(search_terms) if search_terms else "circuit board replacement"
        encoded_query = quote_plus(query_str)

        search_links = {
            "google": f"https://www.google.com/search?q={encoded_query}",
            "ebay": f"https://www.ebay.com/sch/i.html?_nkw={encoded_query}",
            "shopjimmy": f"https://www.shopjimmy.com/search.php?search_query={encoded_query}"
        }

        print("[STEP 5/5] Returning JSON response to frontend.\n")
        return {
            "status": "success",
            "timestamp": timestamp,
            "board_id": parsed_data["board_id"],
            "device_type": parsed_data["device_type"],
            "brand": parsed_data["brand"],
            "model": parsed_data["model"],
            "notes": parsed_data["notes"],
            "search_links": search_links,
            "raw_analysis": analysis_text
        }

    except Exception as e:
        print("\n================ ERROR TRACEBACK ================")
        traceback.print_exc()
        print("=========================================================\n")
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# 5. Static Files Mounting (Required for Executable)
# ---------------------------------------------------------------------------
if www_dir.exists():
    app.mount("/static", StaticFiles(directory=str(www_dir)), name="static")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        target_file = www_dir / full_path
        if target_file.is_file():
            return FileResponse(target_file)
        return FileResponse(www_dir / "index.html")

# ---------------------------------------------------------------------------
# 6. Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    import webbrowser

    def is_port_in_use(p):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', p)) == 0

    port = 8001
    if is_port_in_use(port):
        port = 8002

    webbrowser.open(f"http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)