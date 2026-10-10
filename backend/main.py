import sqlite3
import csv
import io
import base64
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image
from pyzbar.pyzbar import decode as pyzbar_decode

# 1. Initialize the FastAPI app
app = FastAPI(title="Inventory Scanner API")

# 2. Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Database setup
DB_FILE = "inventory.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            barcode TEXT PRIMARY KEY,
            name TEXT,
            description TEXT,
            image_url TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# 4. Data Models
class ImagePayload(BaseModel):
    image_data: str

# --- API ROUTES ---

@app.post("/api/identify-board")
async def identify_board(payload: ImagePayload):
    print("\n--- NEW IMAGE RECEIVED ---")
    try:
        print("1. Decoding base64 string...")
        if "," in payload.image_data:
            header, encoded_str = payload.image_data.split(",", 1)
        else:
            encoded_str = payload.image_data
            
        image_bytes = base64.b64decode(encoded_str)
        
        print("2. Opening image with Pillow...")
        image = Image.open(io.BytesIO(image_bytes))
        
        print("3. Scanning for barcodes with pyzbar... (This might be where it freezes)")
        decoded_objects = pyzbar_decode(image)
        
        print(f"4. Scan complete! Found {len(decoded_objects)} barcodes.")
        
        if not decoded_objects:
            return {"status": "error", "message": "No barcode or QR code detected. Try getting closer or adjusting the focus."}
            
        scanned_code = decoded_objects[0].data.decode("utf-8").strip()
        print(f"5. Barcode read: {scanned_code}")
        
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM items WHERE barcode = ?", (scanned_code,))
        item = cursor.fetchone()
        conn.close()
        
        if item:
            print("6. Match found in database!")
            return {
                "status": "success",
                "board_id": scanned_code,
                "message": f"Identified as: {item['name']}",
                "data": {"name": item["name"], "description": item["description"], "image_url": item["image_url"]}
            }
        else:
            print("6. No match found in database.")
            return {"status": "error", "board_id": scanned_code, "message": f"Barcode '{scanned_code}' was read, but it is not in your inventory database."}
            
    except Exception as e:
        print(f"!!! Vision Error: {e}")
        return {"status": "error", "message": "Failed to process image."}


@app.post("/api/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    """Handles CSV uploads and updates the inventory database."""
    try:
        contents = await file.read()
        decoded = contents.decode('utf-8-sig') 
        csv_reader = csv.DictReader(io.StringIO(decoded))
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        added_count = 0
        updated_count = 0
        
        for row in csv_reader:
            barcode = row.get("barcode", "").strip()
            name = row.get("name", "").strip()
            description = row.get("description", "").strip()
            image_url = row.get("image_url", "").strip()
            
            if not barcode:
                continue 
                
            cursor.execute("SELECT barcode FROM items WHERE barcode = ?", (barcode,))
            exists = cursor.fetchone()
            
            if exists:
                updated_count += 1
            else:
                added_count += 1
                
            cursor.execute('''
                REPLACE INTO items (barcode, name, description, image_url)
                VALUES (?, ?, ?, ?)
            ''', (barcode, name, description, image_url))
            
        conn.commit()
        conn.close()
        
        return {
            "status": "success", 
            "added": added_count, 
            "updated": updated_count
        }
        
    except Exception as e:
        print(f"CSV Upload Error: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/scan")
async def scan_barcode(scanned_code: str):
    """Looks up a scanned barcode string in the database."""
    code = scanned_code.strip()
    
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM items WHERE barcode = ?", (code,))
    item = cursor.fetchone()
    conn.close()
    
    if item:
        return {
            "match_found": True,
            "scanned_item": code,
            "data": {
                "name": item["name"],
                "description": item["description"],
                "image_url": item["image_url"]
            }
        }
    else:
        return {
            "match_found": False,
            "scanned_item": code,
            "error": f"Item {code} not found in database."
        }