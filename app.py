from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Scam Likely Mini API", version="0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # loosened for now so Vibecode works
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz")
def health():
    return {"ok": True}

# --- Demo endpoints for Vibecode screens ---

@app.get("/v1/recent-entities")
def recent_entities():
    return {
        "items": [
            {
                "id": "demo-1",
                "display_name": "ABC Web Solutions",
                "top_identifier": "+1 (443) 555-0123",
                "state": "MD",
                "city": "Baltimore",
                "report_count": 1,
                "status": "published"
            }
        ]
    }

@app.get("/v1/search")
def search(q: str, state: str | None = None, city: str | None = None):
    # Minimal mock so Search screen returns something
    return {
        "items": [
            {
                "id": "demo-1",
                "display_name": "ABC Web Solutions",
                "top_identifier": "+1 (443) 555-0123",
                "report_count": 1,
                "state": "MD",
                "city": "Baltimore"
            }
        ],
        "next_page": None
    }
