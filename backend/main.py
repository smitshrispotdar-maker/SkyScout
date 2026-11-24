"""FastAPI backend serving both the REST API and the frontend."""
from datetime import date
from pathlib import Path
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4
import re

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, field_validator

from .agent import (
    CITY_NAMES,
    PERSONA_WEIGHTS,
    Coordinator,
    build_execution_records,
    code,
    email_configured,
    is_valid_email,
    make_acl_message,
    parse_budget,
)
from .pdf import render_briefing_pdf

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(
    title="SkyScout Autonomous Multi-Agent Travel Platform",
    version="3.0.0",
    description="End-Semester Major Project: Multi-view agentic flight planning, round-trip decomposition, lexical preference memory and grounding audit.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
manager = Coordinator()

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    for err in exc.errors():
        msg = str(err.get("msg", ""))
        if "Date must use YYYY-MM-DD format" in msg or "Watch travel date must use YYYY-MM-DD format" in msg:
            clean = msg.replace("Value error, ", "")
            return JSONResponse(status_code=400, content={"detail": clean})
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

SEARCH_FIELDS = ("origin", "destination", "date", "return_date", "budget", "email")


class SearchRequest(BaseModel):
    session_id: str = Field(min_length=32, max_length=32)
    query: str = Field(default="", max_length=1000)
    origin: Optional[str] = None
    destination: Optional[str] = None
    date: Optional[str] = None
    return_date: Optional[str] = None
    budget: Optional[float] = None
    email: Optional[str] = None
    persona: str = Field(default="balanced", max_length=32)
    reuse_memory: bool = True
    save_memory: bool = False
    rejected_flights: Optional[List[str]] = None
    selected_flight_no: Optional[str] = None
    reset_rejections: bool = False
    weights: Optional[Dict[str, Any]] = None

    @field_validator("date", "return_date")
    @classmethod
    def _validate_search_dates(cls, value: Optional[str]) -> Optional[str]:
        if value is None or str(value).strip() == "":
            return value
        cleaned = str(value).strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
            raise ValueError("Date must use YYYY-MM-DD format.")
        date.fromisoformat(cleaned)
        return cleaned


class FeedbackRequest(BaseModel):
    session_id: str = Field(min_length=32, max_length=64)
    action: str = Field(max_length=32)
    flight_no: str = Field(max_length=20)
    reason: Optional[str] = Field(default=None, max_length=300)
    last_search: SearchRequest

    @field_validator("last_search", mode="before")
    @classmethod
    def _fill_last_search_session(cls, value: Any, info):
        if isinstance(value, dict):
            payload = dict(value)
            session_id = info.data.get("session_id")
            if session_id and not str(payload.get("session_id") or "").strip():
                payload["session_id"] = session_id
            return payload
        return value


class NoteRequest(BaseModel):
    note: str = Field(max_length=300)


class BriefingRequest(BaseModel):
    session_id: str = Field(min_length=32, max_length=32)


class PreferenceRequest(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    value: str = Field(max_length=300)


PREFERENCE_KEYS = ("origin", "destination", "date", "return_date", "budget", "email", "persona")


def validate_preference_value(key: str, value: Any, session_id: Optional[str] = None) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError("Preference value cannot be empty or whitespace-only.")
    if key not in PREFERENCE_KEYS:
        raise ValueError("Unsupported preference field.")
    if key in ("origin", "destination"):
        known = set(CITY_NAMES)
        known.update(flight.get("origin") for flight in manager.inventory if flight.get("origin"))
        known.update(flight.get("destination") for flight in manager.inventory if flight.get("destination"))
        if code(cleaned) not in known:
            raise ValueError("Unsupported city for this preference.")
        if session_id:
            prefs = manager.memory.load(session_id)
            other_key = "destination" if key == "origin" else "origin"
            other = prefs.get(other_key)
            if other and code(other) == code(cleaned):
                raise ValueError("Origin and destination must be different.")
    if key in ("date", "return_date"):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
            raise ValueError("Preference date must use YYYY-MM-DD format.")
        try:
            parsed = date.fromisoformat(cleaned)
        except ValueError as exc:
            raise ValueError("Preference date must use YYYY-MM-DD format.") from exc
        if parsed < date.today():
            raise ValueError("Preference date must be today or a future date.")
    if key == "budget":
        _, error = parse_budget(cleaned)
        if error:
            raise ValueError(error)
    if key == "email" and not is_valid_email(cleaned):
        raise ValueError("Please enter a valid email address.")
    if key == "persona" and cleaned not in PERSONA_WEIGHTS:
        raise ValueError("Unsupported persona preference.")
    return cleaned


class WatchRuleRequest(BaseModel):
    session_id: str = Field(min_length=32, max_length=32)
    origin: str = Field(min_length=2, max_length=40)
    destination: str = Field(min_length=2, max_length=40)
    target_price: float = Field(gt=0)
    date: Optional[str] = None
    persona: str = Field(default="balanced", max_length=32)

    @field_validator("date")
    @classmethod
    def _validate_watch_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return str(value).strip()


class WatchSimulateRequest(BaseModel):
    session_id: str = Field(min_length=32, max_length=32)
    origin: Optional[str] = None
    destination: Optional[str] = None
    target_price: Optional[float] = None
    date: Optional[str] = None
    persona: Optional[str] = None

    @field_validator("date")
    @classmethod
    def _validate_watch_sim_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None or str(value).strip() == "":
            return value
        cleaned = str(value).strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
            raise ValueError("Watch travel date must use YYYY-MM-DD format.")
        date.fromisoformat(cleaned)
        return cleaned


@app.get("/")
def index():
    return FileResponse(ROOT / "frontend" / "index.html")


@app.get("/styles.css")
def styles():
    return FileResponse(ROOT / "frontend" / "styles.css", media_type="text/css")


@app.get("/app.js")
def javascript():
    return FileResponse(ROOT / "frontend" / "app.js", media_type="application/javascript")


def manager_city(code: str) -> str:
    return CITY_NAMES.get(code, code)


def supplied_fields(body: Any) -> Dict[str, Any]:
    return {key: getattr(body, key) for key in SEARCH_FIELDS}


def guarded(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def feedback_error_response(status: str, message: str, action: str, flight_no: str) -> Dict[str, Any]:
    event = make_acl_message(
        manager.name,
        "Email Agent",
        "REJECT",
        message,
        status,
        0.99,
        {"action": action, "flight_no": flight_no},
    )
    events = [event]
    return {
        "status": status,
        "message": message,
        "flights": [],
        "trace": events,
        "execution": build_execution_records(status, events, manager.extractor.last_mode, message=message),
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "provider": "skyscout_agentic_engine_v3",
        "email_mode": "smtp" if email_configured() else "preview",
        "extractor_mode": manager.extractor.last_mode,
        "llm_available": bool(manager.extractor.last_mode == "llm"),
    }


@app.post("/api/briefing")
def briefing(body: BriefingRequest):
    def run():
        return manager.build_briefing(body.session_id)

    return guarded(run)


@app.post("/api/dossier/pdf")
def dossier_pdf(body: BriefingRequest):
    def run():
        briefing_data = manager.build_briefing(body.session_id)
        try:
            pdf_bytes = render_briefing_pdf(briefing_data, body.session_id)
        except ValueError:
            raise
        except Exception as exc:
            logging.getLogger(__name__).exception("PDF dossier generation failed")
            raise ValueError("PDF generation failed. Please retry.") from exc
        filename = "SkyScout_Travel_Dossier.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return guarded(run)


@app.get("/api/routes")
def routes():
    routes_list = []
    for flight in manager.inventory:
        o, d = flight.get("origin"), flight.get("destination")
        if not o or not d:
            continue
        item = {
            "origin_code": o,
            "destination_code": d,
            "origin": manager_city(o),
            "destination": manager_city(d),
        }
        if item not in routes_list:
            routes_list.append(item)
    return {"routes": routes_list}


@app.post("/api/session")
def create_session():
    return {"session_id": uuid4().hex}


@app.get("/api/memory/{session_id}")
def memory_get(session_id: str):
    def run():
        preferences = manager.memory.load(session_id)
        short_term = manager.memory.short_term.get(session_id, {})
        return {
            "preferences": preferences,
            "short_term": short_term,
            "semantic_memories": manager.memory.notes_with_similarity(session_id),
            "watch_rule": manager.memory.get_watch_rule(session_id),
            "selected_itinerary": preferences.get("selected_itinerary") or short_term.get("selected_itinerary"),
            "memory_status": manager.memory.status(session_id),
        }

    return guarded(run)


@app.post("/api/memory/{session_id}/note")
def memory_add_note(session_id: str, body: NoteRequest):
    def run():
        result = manager.memory.append_semantic_note(session_id, body.note)
        result["semantic_memories"] = manager.memory.notes_with_similarity(session_id)
        result["memory_status"] = manager.memory.status(session_id)
        return result

    return guarded(run)


@app.put("/api/memory/{session_id}/note/{index}")
def memory_update_note(session_id: str, index: int, body: NoteRequest):
    def run():
        result = manager.memory.update_semantic_note(session_id, index, body.note)
        result["semantic_memories"] = manager.memory.notes_with_similarity(session_id)
        result["memory_status"] = manager.memory.status(session_id)
        return result

    return guarded(run)


@app.delete("/api/memory/{session_id}/note/{index}")
def memory_delete_note(session_id: str, index: int):
    def run():
        result = manager.memory.delete_semantic_note(session_id, index)
        result["semantic_memories"] = manager.memory.notes_with_similarity(session_id)
        result["memory_status"] = manager.memory.status(session_id)
        return result

    return guarded(run)


@app.put("/api/memory/{session_id}/preference")
def memory_set_preference(session_id: str, body: PreferenceRequest):
    def run():
        value = validate_preference_value(body.key, body.value, session_id=session_id)
        result = manager.memory.set_preference(session_id, body.key, value)
        result["memory_status"] = manager.memory.status(session_id)
        return result

    return guarded(run)


@app.delete("/api/memory/{session_id}/preference/{key}")
def memory_delete_preference(session_id: str, key: str):
    def run():
        result = manager.memory.delete_preference(session_id, key)
        result["memory_status"] = manager.memory.status(session_id)
        return result

    return guarded(run)


@app.delete("/api/memory/{session_id}/selection")
def memory_clear_selection(session_id: str):
    def run():
        result = manager.memory.clear_selected_itinerary(session_id)
        cached = manager.last_results.get(session_id)
        if isinstance(cached, dict):
            cached.pop("selection", None)
            cached.pop("briefing", None)
        result["memory_status"] = manager.memory.status(session_id)
        return result

    return guarded(run)


@app.delete("/api/memory/{session_id}")
def memory_delete(session_id: str):
    def run():
        result = manager.memory.clear(session_id)
        manager.last_results.pop(session_id, None)
        return result

    return guarded(run)


@app.post("/api/search")
def search(body: SearchRequest):
    return guarded(
        manager.run,
        body.session_id,
        body.query,
        supplied_fields(body),
        body.reuse_memory,
        body.save_memory,
        persona=body.persona,
        rejected_flights=body.rejected_flights,
        selected_flight_no=body.selected_flight_no,
        reset_rejections=body.reset_rejections,
        weights=body.weights,
    )


@app.post("/api/feedback")
def feedback(body: FeedbackRequest):
    action = str(body.action or "").strip().lower()
    if action not in {"select", "reject"}:
        return feedback_error_response("invalid_action", "Unsupported feedback action.", action, body.flight_no)
    req = body.last_search
    short_term = manager.memory.short_term.get(body.session_id, {})
    available = [str(no) for no in short_term.get("last_result_flight_nos", []) if no]
    exclusions = [str(no) for no in short_term.get("active_exclusions", short_term.get("rejected_flights", [])) if no]
    if action == "reject" and body.flight_no in exclusions:
        return feedback_error_response("already_rejected", f"Flight {body.flight_no} is already rejected.", action, body.flight_no)
    if available and body.flight_no not in available:
        return feedback_error_response("invalid_selection", f"Flight {body.flight_no} is not an available recommendation.", action, body.flight_no)

    rejected = list(req.rejected_flights or [])
    selected_no = req.selected_flight_no
    if action == "reject":
        rejected.append(body.flight_no)
    else:
        selected_no = body.flight_no

    result = guarded(
        manager.run,
        body.session_id,
        req.query,
        supplied_fields(req),
        req.reuse_memory,
        req.save_memory,
        persona=req.persona,
        rejected_flights=rejected,
        selected_flight_no=selected_no,
        reset_rejections=False,
        weights=req.weights,
    )
    if result.get("status") in {"success", "success_email_failed"}:
        if action == "reject":
            note = f"Rejected {body.flight_no}" + (f": {body.reason}" if body.reason else "")
            manager.memory.append_semantic_note(body.session_id, note)
        elif result.get("selection"):
            manager.memory.append_semantic_note(body.session_id, f"Selected flight {body.flight_no} for briefing")
    return result


@app.post("/api/watch/simulate")
def watch_simulate(body: WatchSimulateRequest):
    def run():
        inline_fields = {
            "origin": body.origin,
            "destination": body.destination,
            "target_price": body.target_price,
            "date": body.date,
            "persona": body.persona,
        }
        has_inline = any(value not in (None, "") for value in inline_fields.values())
        inline = None
        if has_inline:
            if not (body.origin and body.destination and body.target_price is not None and body.date):
                raise ValueError("Inline simulation requires origin, destination, target price, and date.")
            inline = {
                "origin": body.origin,
                "destination": body.destination,
                "target_price": body.target_price,
                "date": body.date,
                "persona": body.persona or "balanced",
            }
            saved = manager.watcher.save_rule(
                body.session_id,
                inline["origin"],
                inline["destination"],
                inline["target_price"],
                inline["date"],
                inline["persona"],
            )
            if saved.get("status") != "saved" or not saved.get("persisted"):
                raise ValueError("Inline watch rule was not persisted.")
        result = manager.watcher.simulate(body.session_id, inline)
        result["rule_source"] = "inline_saved" if inline else "stored"
        return result

    return guarded(run)


@app.post("/api/watch")
def watch_save(body: WatchRuleRequest):
    def run():
        return manager.watcher.save_rule(
            body.session_id,
            body.origin,
            body.destination,
            body.target_price,
            body.date,
            body.persona,
        )

    return guarded(run)


@app.post("/api/watch/{session_id}")
def watch_save_alias(session_id: str, body: WatchRuleRequest):
    body.session_id = session_id
    return watch_save(body)
