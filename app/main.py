from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from app.analysis import analyze_many
from app.schemas import AnalyzeRequest

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="AI Stock Intelligence Platform", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/analyze")
def analyze(payload: AnalyzeRequest) -> dict:
    results = analyze_many(payload.tickers)
    ok_count = sum(1 for r in results if r.get("status") == "ok")
    return {
        "requested": len(payload.tickers),
        "completed": ok_count,
        "results": results,
    }


@app.post("/api/report")
def report(payload: AnalyzeRequest) -> dict:
    results = analyze_many(payload.tickers)

    reports = []
    for item in results:
        if item.get("status") == "ok":
            reports.append(
                {
                    "ticker": item["ticker"],
                    "recommendation": item["recommendation"],
                    "confidence": item["confidence"],
                    "report_markdown": item["report_markdown"],
                }
            )

    if not reports:
        raise HTTPException(status_code=400, detail="No successful reports were generated")

    return {"reports": reports, "count": len(reports)}


@app.post("/api/report/download")
def report_download(payload: AnalyzeRequest, format: str = "json") -> Response:
    results = analyze_many(payload.tickers)

    ok_items = [item for item in results if item.get("status") == "ok"]
    if not ok_items:
        raise HTTPException(status_code=400, detail="No successful report to download")

    if format == "md":
        doc = "\n\n---\n\n".join(item["report_markdown"] for item in ok_items)
        headers = {"Content-Disposition": "attachment; filename=stock_reports.md"}
        return PlainTextResponse(content=doc, headers=headers)

    if format == "json":
        data = json.dumps(ok_items, indent=2)
        headers = {"Content-Disposition": "attachment; filename=stock_reports.json"}
        return Response(content=data, media_type="application/json", headers=headers)

    raise HTTPException(status_code=400, detail="format must be 'json' or 'md'")
