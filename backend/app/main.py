from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any

app = FastAPI(
    title="Scanner API",
    version="0.1.0",
    description="Backend API for the scanner application",
)


class ScanItem(BaseModel):
    id: str
    name: str
    status: str = "pending"
    metadata: Dict[str, Any] | None = None


@app.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "ok", "service": "scanner-api"}


@app.get("/api/scans", response_model=List[ScanItem])
def list_scans() -> List[ScanItem]:
    return [
        ScanItem(
            id="scan-001",
            name="Inventory scan",
            status="completed",
            metadata={"records": 1042, "location": "Warehouse A"},
        ),
        ScanItem(
            id="scan-002",
            name="Asset audit",
            status="pending",
            metadata={"records": 320, "location": "North Wing"},
        ),
    ]


@app.post("/api/scans")
def create_scan(scan: ScanItem) -> ScanItem:
    return scan


@app.get("/")
def root() -> Dict[str, str]:
    return {"message": "Welcome to the Scanner API"}
