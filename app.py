from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Literal, Dict, Any
import uuid
from datetime import datetime

app = FastAPI(title="Scam Likely Mini API", version="0.3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- In-memory storage (for demo only) ----------------
ENTITIES: Dict[str, Dict[str, Any]] = {}
REPORTS: Dict[str, Dict[str, Any]] = {}
DISPUTES: Dict[str, Dict[str, Any]] = {}  # key = dispute_id

# ---------------- Seed data ----------------
if not ENTITIES:
    ent_id = "demo-1"
    ENTITIES[ent_id] = {
        "id": ent_id,
        "display_name": "ABC Web Solutions",
        "type": "business",
        "top_identifier": "+1 (443) 555-0123",
        "phones": ["+14435550123"],
        "emails": ["owner@abcweb.co"],
        "state": "MD",
        "city": "Baltimore",
        "report_count": 1,
    }
    seed_rid = str(uuid.uuid4())
    REPORTS[seed_rid] = {
        "id": seed_rid,
        "entity_id": ent_id,
        "category": "Non-delivery",
        "narrative": "Paid $500 for a website; after 6 weeks nothing delivered.",
        "amount_cents": 50000,
        "incident_date": "2025-08-20",
        "incident_mode": "digital",
        "incident_location": {
            "scammer_origin": {"city": "Baltimore", "state": "MD", "country": "US"}
        },
        "reporter_public_anonymous": True,
        "status": "published",
        "created_at": datetime.utcnow().isoformat() + "Z",
    }

# ---------------- Schemas ----------------
class Identifiers(BaseModel):
    gov_name: Optional[str] = None
    business_name: Optional[str] = None
    phones: List[str] = []
    emails: List[EmailStr] = []
    handles: List[str] = []
    websites: List[str] = []

class ReportCreate(BaseModel):
    identifiers: Identifiers
    category: str
    narrative: str = Field(min_length=50)
    amount_cents: Optional[int] = None
    currency: str = "USD"
    incident_date: Optional[str] = None
    incident_mode: Literal["digital", "in_person"]
    incident_location: Dict[str, Any]
    reporter_public_anonymous: bool = True
    reporter_email: Optional[EmailStr] = None  # demo only

class DisputeCreate(BaseModel):
    contact_email: EmailStr
    text: str = Field(min_length=20, max_length=2000)
    public_anonymous: bool = True

# ---------------- Routes ----------------
@app.get("/healthz")
def health():
    return {"ok": True}

@app.get("/v1/recent-entities")
def recent_entities():
    items = []
    for e in ENTITIES.values():
        count = sum(
            1 for r in REPORTS.values()
            if r["entity_id"] == e["id"] and r["status"] in ("published", "disputed")
        )
        if count:
            items.append({
                "id": e["id"],
                "display_name": e["display_name"],
                "state": e["state"],
                "city": e["city"],
                "report_count": count,
            })
    return {"items": items}

@app.post("/v1/reports")
def create_report(payload: ReportCreate):
    match_id = None
    for e in ENTITIES.values():
        if any(p in e.get("phones", []) for p in payload.identifiers.phones):
            match_id = e["id"]
            break
    if not match_id:
        eid = str(uuid.uuid4())
        ENTITIES[eid] = {
            "id": eid,
            "display_name": payload.identifiers.business_name or payload.identifiers.gov_name or "Unknown",
            "type": "business" if payload.identifiers.business_name else "person",
            "phones": payload.identifiers.phones,
            "emails": [str(e) for e in payload.identifiers.emails],
            "state": payload.incident_location.get("state"),
            "city": payload.incident_location.get("city"),
        }
        match_id = eid

    rid = str(uuid.uuid4())
    REPORTS[rid] = {
        "id": rid,
        "entity_id": match_id,
        "category": payload.category,
        "narrative": payload.narrative,
        "amount_cents": payload.amount_cents,
        "incident_date": payload.incident_date,
        "incident_mode": payload.incident_mode,
        "incident_location": payload.incident_location,
        "reporter_public_anonymous": payload.reporter_public_anonymous,
        "status": "pending",
        "reporter_email": str(payload.reporter_email) if payload.reporter_email else None,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    return {"id": rid, "status": "pending", "entity_id": match_id}

@app.post("/v1/reports/{report_id}/publish")
def publish_report(report_id: str):
    r = REPORTS.get(report_id)
    if not r:
        raise HTTPException(404, detail="report not found")
    r["status"] = "published"
    return {"id": r["id"], "status": r["status"]}

@app.get("/v1/entities/{entity_id}")
def entity_detail(entity_id: str):
    e = ENTITIES.get(entity_id)
    if not e:
        raise HTTPException(404, detail="entity not found")
    reports = [r for r in REPORTS.values() if r["entity_id"] == entity_id and r["status"] in ("published", "disputed")]
    for rr in reports:
        rr["disputes_count"] = len([d for d in DISPUTES.values() if d["report_id"] == rr["id"]])
    return {
        "id": e["id"],
        "display_name": e.get("display_name"),
        "type": e.get("type"),
        "phones": e.get("phones", []),
        "emails": e.get("emails", []),
        "state": e.get("state"),
        "city": e.get("city"),
        "reports": reports,
    }

@app.post("/v1/reports/{report_id}/dispute")
def create_dispute(report_id: str, payload: DisputeCreate):
    r = REPORTS.get(report_id)
    if not r:
        raise HTTPException(404, detail="report not found")
    did = str(uuid.uuid4())
    DISPUTES[did] = {
        "id": did,
        "report_id": report_id,
        "entity_id": r["entity_id"],
        "contact_email": str(payload.contact_email),
        "text": payload.text.strip(),
        "public_anonymous": bool(payload.public_anonymous),
        "status": "open",
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    r["status"] = "disputed"
    return {"id": did, "report_id": report_id, "status": "open"}

@app.get("/v1/reports/{report_id}/disputes")
def list_disputes(report_id: str):
    if report_id not in [rr["id"] for rr in REPORTS.values()]:
        raise HTTPException(404, detail="report not found")
    items = [d for d in DISPUTES.values() if d["report_id"] == report_id]
    items.sort(key=lambda d: d["created_at"], reverse=True)
    return {"items": items}

@app.get("/v1/reports/{report_id}")
def get_report(report_id: str):
    r = REPORTS.get(report_id)
    if not r:
        raise HTTPException(404, detail="report not found")
    disputes = [d for d in DISPUTES.values() if d["report_id"] == report_id]
    return {"report": r, "disputes": disputes}
