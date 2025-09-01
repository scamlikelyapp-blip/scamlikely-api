from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Literal, Dict, Any
import uuid
from datetime import datetime

app = FastAPI(title="Scam Likely Mini API", version="0.3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- In-memory storage (for demo only) ----------------
ENTITIES: Dict[str, Dict[str, Any]] = {}
REPORTS: Dict[str, Dict[str, Any]] = {}

# seed one entity + published report
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
        "incident_location": {"scammer_origin": {"city": "Baltimore", "state": "MD", "country": "US"}},
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

# ---------------- Health ----------------
@app.get("/healthz")
def health():
    return {"ok": True}

# ---------------- Home list (only published/disputed) ----------------
@app.get("/v1/recent-entities")
def recent_entities():
    items = []
    for e in ENTITIES.values():
        count = sum(1 for r in REPORTS.values()
                    if r["entity_id"] == e["id"] and r["status"] in ("published", "disputed"))
        if count:
            items.append({
                "id": e["id"],
                "display_name": e["display_name"],
                "top_identifier": e.get("top_identifier") or (e.get("phones") or e.get("emails") or [""])[0],
                "state": e.get("state"),
                "city": e.get("city"),
                "report_count": count,
                "status": "published",
            })
    return {"items": items}

# ---------------- Search (very simple) ----------------
@app.get("/v1/search")
def search(q: str, state: Optional[str] = None, city: Optional[str] = None):
    q_lower = q.lower()
    results = []
    for e in ENTITIES.values():
        hay = " ".join([e.get("display_name",""),
                        " ".join(e.get("phones", [])),
                        " ".join(e.get("emails", []))]).lower()
        if q_lower in hay:
            if state and e.get("state") != state: 
                continue
            if city and e.get("city") != city:
                continue
            count = sum(1 for r in REPORTS.values()
                        if r["entity_id"] == e["id"] and r["status"] in ("published", "disputed"))
            results.append({
                "id": e["id"],
                "display_name": e["display_name"],
                "top_identifier": e.get("top_identifier") or (e.get("phones") or e.get("emails") or [""])[0],
                "state": e.get("state"),
                "city": e.get("city"),
                "report_count": count or 0
            })
    return {"items": results, "next_page": None}

# ---------------- Submit Report ----------------
@app.post("/v1/reports")
def create_report(payload: ReportCreate):
    # Validate location rules
    if payload.incident_mode == "digital":
        origin = payload.incident_location.get("scammer_origin")
        unknown = payload.incident_location.get("unknown")
        if not origin and not unknown:
            raise HTTPException(400, detail="For digital incidents, include incident_location.scammer_origin or set unknown=true.")
    elif payload.incident_mode == "in_person":
        loc = payload.incident_location
        required = all([loc.get("city"), loc.get("state"), loc.get("country")])
        if not required:
            raise HTTPException(400, detail="For in-person incidents, city/state/country are required.")
    else:
        raise HTTPException(400, detail="incident_mode must be 'digital' or 'in_person'.")

    # Find/create entity (naive demo logic)
    display_name = payload.identifiers.business_name or payload.identifiers.gov_name or "Unknown"
    match_id = None
    for e in ENTITIES.values():
        if any(p in (e.get("phones") or []) for p in payload.identifiers.phones) or \
           any(str(m).lower() in [em.lower() for em in (e.get("emails") or [])] for m in payload.identifiers.emails):
            match_id = e["id"]; break
    if not match_id:
        eid = str(uuid.uuid4())
        ENTITIES[eid] = {
            "id": eid,
            "display_name": display_name,
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
        "status": "pending",  # moderation required
        "reporter_email": str(payload.reporter_email) if payload.reporter_email else None,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    return {"id": rid, "status": "pending", "entity_id": match_id}

# ---------------- My Reports (demo) ----------------
@app.get("/v1/reports/mine")
def my_reports(email: EmailStr):
    items = [r for r in REPORTS.values()
             if r.get("reporter_email") and r["reporter_email"].lower() == str(email).lower()]
    return {"items": items}

# ---------------- NEW: Publish a report (demo moderation) ----------------
@app.post("/v1/reports/{report_id}/publish")
def publish_report(report_id: str):
    r = REPORTS.get(report_id)
    if not r:
        raise HTTPException(404, detail="report not found")
    r["status"] = "published"
    # bump entity report_count
    e = ENTITIES.get(r["entity_id"])
    if e:
        e["report_count"] = sum(1 for rr in REPORTS.values()
                                if rr["entity_id"] == e["id"] and rr["status"] == "published")
    return {"id": r["id"], "status": r["status"]}

# ---------------- NEW: Entity detail with reports ----------------
@app.get("/v1/entities/{entity_id}")
def entity_detail(entity_id: str):
    e = ENTITIES.get(entity_id)
    if not e:
        raise HTTPException(404, detail="entity not found")
    reports = [r for r in REPORTS.values()
               if r["entity_id"] == entity_id and r["status"] in ("published", "disputed")]
    return {
        "id": e["id"],
        "display_name": e.get("display_name"),
        "type": e.get("type"),
        "phones": e.get("phones", []),
        "emails": e.get("emails", []),
        "state": e.get("state"),
        "city": e.get("city"),
        "reports": reports
    }
