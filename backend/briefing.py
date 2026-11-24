"""Structured itinerary briefing and verification metadata for SkyScout."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

INVENTORY_SOURCE = "SkyScout bundled demo inventory"
SIMULATION_SOURCE = "SkyScout local fare simulation (not live monitoring)"
SESSION_SOURCE = "session preferences and current request"

NOT_PROVIDED = "Not provided in demo inventory"
NOT_APPLICABLE = "Not available for this itinerary"
PENDING = "Pending verification"


def _display(item: Dict[str, Any]) -> str:
    return str(item.get("value") or item.get("reason") or "Unavailable")


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower().startswith("not provided"):
        return None
    return text


def _field(label: str, value: Any, source: Optional[str] = None, reason: Optional[str] = None) -> Dict[str, Any]:
    cleaned = _clean(value)
    return {
        "label": label,
        "value": cleaned,
        "status": "available" if cleaned else "unavailable",
        "source": source if cleaned else None,
        "reason": None if cleaned else (reason or PENDING),
    }


def _money(value: Any) -> Optional[str]:
    try:
        return f"INR {int(value):,}"
    except (TypeError, ValueError):
        return None


def _weight_percent(value: Any) -> Optional[str]:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not -1e-9 <= numeric <= 100.0 + 1e-9:
        return None
    return f"{round(numeric):.0f}%"


def _first_available(*values: Any) -> Optional[str]:
    for value in values:
        cleaned = _clean(value)
        if cleaned:
            return cleaned
    return None


def _leg_brief(leg: Optional[Dict[str, Any]], direction: str, travel_date: Any, applicable: bool = True) -> Dict[str, Any]:
    leg = leg if isinstance(leg, dict) else {}
    inventory_reason = NOT_APPLICABLE if not applicable else NOT_PROVIDED
    fields = [
        _field("Travel date", travel_date, SESSION_SOURCE, NOT_APPLICABLE if not applicable else PENDING),
        _field("Airline", leg.get("airline"), INVENTORY_SOURCE, inventory_reason),
        _field("Flight number", leg.get("flight_no"), INVENTORY_SOURCE, inventory_reason),
        _field("Departure time", leg.get("dep_time") or leg.get("departure_time"), INVENTORY_SOURCE, inventory_reason),
        _field("Arrival time", leg.get("arr_time") or leg.get("arrival_time"), INVENTORY_SOURCE, inventory_reason),
        _field("Duration", leg.get("duration"), INVENTORY_SOURCE, inventory_reason),
        _field("Stops", leg.get("stops"), INVENTORY_SOURCE, inventory_reason),
        _field("Layover", leg.get("layover") or leg.get("layovers"), INVENTORY_SOURCE, inventory_reason),
        _field("Cabin baggage", leg.get("cabin_baggage") or leg.get("baggage"), INVENTORY_SOURCE, inventory_reason),
        _field("Check-in baggage", leg.get("checkin_baggage"), INVENTORY_SOURCE, inventory_reason),
    ]
    return {
        "direction": direction,
        "available": any(item["status"] == "available" for item in fields if item["label"] != "Travel date"),
        "fields": fields,
    }


def _preference_brief(result: Dict[str, Any], memory_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    fields = result.get("fields") if isinstance(result.get("fields"), dict) else {}
    ranking_weights = result.get("ranking_weights") if isinstance(result.get("ranking_weights"), dict) else {}
    preferences = memory_data.get("preferences") if isinstance(memory_data.get("preferences"), dict) else {}
    short_term = memory_data.get("short_term") if isinstance(memory_data.get("short_term"), dict) else {}
    labels = {
        "origin": "Preferred origin",
        "destination": "Preferred destination",
        "date": "Preferred departure date",
        "return_date": "Preferred return date",
        "budget": "Budget",
        "persona": "Ranking persona",
    }
    items = []
    for key, label in labels.items():
        value = _first_available(fields.get(key), preferences.get(key), short_term.get(key))
        items.append(_field(label, value, SESSION_SOURCE))
    notes = result.get("semantic_memories") or []
    if isinstance(notes, list):
        for index, item in enumerate(notes, 1):
            note = item.get("note") if isinstance(item, dict) else item
            cleaned = _clean(note)
            if cleaned:
                items.append({"label": f"Preference rule {index}", "value": cleaned, "status": "available", "source": "saved lexical preference rules"})
    return items


def _watcher_brief(memory_data: Dict[str, Any], watcher_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    result = watcher_result if isinstance(watcher_result, dict) and watcher_result else None
    rule = None
    if isinstance(result, dict) and isinstance(result.get("rule"), dict):
        rule = result["rule"]
    elif isinstance(memory_data.get("watch_rule"), dict):
        rule = memory_data["watch_rule"]
    if not rule:
        return {
            "status": "UNAVAILABLE",
            "is_live": False,
            "source": None,
            "disclosure": "No watcher rule is saved for this session.",
            "fields": [_field(label, None, reason=PENDING) for label in ("Origin", "Destination", "Target fare", "Travel date")],
        }
    alert = result.get("alert") if isinstance(result, dict) and isinstance(result.get("alert"), dict) else {}
    fields = [
        _field("Origin", rule.get("origin"), SIMULATION_SOURCE, PENDING),
        _field("Destination", rule.get("destination"), SIMULATION_SOURCE, PENDING),
        _field("Target fare", _money(rule.get("target_price")), SIMULATION_SOURCE, PENDING),
        _field("Travel date", rule.get("date"), SIMULATION_SOURCE, PENDING),
    ]
    fields.append(_field("Simulated alert", alert.get("headline"), SIMULATION_SOURCE, PENDING))
    return {
        "status": "SIMULATED",
        "is_live": False,
        "source": SIMULATION_SOURCE,
        "disclosure": "Watcher information is generated locally for demonstration and is not live airline monitoring.",
        "fields": fields,
    }


def _verification_brief(
    result: Dict[str, Any],
    watcher: Dict[str, Any],
    missing: List[str],
    warnings: List[str],
    availability: str,
) -> Dict[str, Any]:
    safety = result.get("safety_report") if isinstance(result.get("safety_report"), dict) else {}
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    evidence = bool(
        safety.get("passed")
        and int(safety.get("checked_flights") or 0) > 0
        and _clean(safety.get("verified_at"))
    )
    inventory_status = "VERIFIED" if evidence else ("UNAVAILABLE" if availability == "unavailable" else "PREVIEW")
    if watcher["status"] == "SIMULATED":
        overall = "SIMULATED"
    elif inventory_status == "VERIFIED":
        overall = "VERIFIED"
    else:
        overall = inventory_status
    timestamp = _clean(safety.get("verified_at")) if evidence else generated_at
    return {
        "status": overall,
        "inventory_status": inventory_status,
        "timestamp": timestamp,
        "timestamp_kind": "verification" if evidence else "briefing_generation",
        "generated_at": generated_at,
        "source": "SkyScout grounding audit against bundled demo inventory" if evidence else "assembled application state",
        "data_availability": availability,
        "simulation_disclosure": "No live airline verification or live fare monitoring was performed.",
        "warnings": warnings,
        "missing_information": missing,
        "evidence": {
            "passed": bool(safety.get("passed")),
            "checked_flights": int(safety.get("checked_flights") or 0),
            "grounding_score": safety.get("grounding_score", 0),
        },
    }


def build_structured_briefing(
    result: Optional[Dict[str, Any]] = None,
    memory_data: Optional[Dict[str, Any]] = None,
    watcher_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    result = result if isinstance(result, dict) else {}
    memory_data = memory_data if isinstance(memory_data, dict) else {}
    fields = result.get("fields") if isinstance(result.get("fields"), dict) else {}
    ranking_weights = result.get("ranking_weights") if isinstance(result.get("ranking_weights"), dict) else {}
    preferences = memory_data.get("preferences") if isinstance(memory_data.get("preferences"), dict) else {}
    short_term = memory_data.get("short_term") if isinstance(memory_data.get("short_term"), dict) else {}
    flights = result.get("flights") if isinstance(result.get("flights"), list) else []
    selection = result.get("selection") or preferences.get("selected_itinerary") or short_term.get("selected_itinerary")
    selection = selection if isinstance(selection, dict) else {}
    selected_no = str(selection.get("flight_no") or "").strip().upper()
    if selected_no and not any(
        isinstance(flight, dict) and str(flight.get("flight_no", "")).strip().upper() == selected_no for flight in flights
    ):
        selection = {}
    chosen = None
    if selection.get("flight_no"):
        chosen = next((flight for flight in flights if isinstance(flight, dict) and str(flight.get("flight_no", "")).upper() == str(selection["flight_no"]).upper()), None)
    if chosen is None:
        chosen = next((flight for flight in flights if isinstance(flight, dict)), {})
    chosen = chosen if isinstance(chosen, dict) else {}
    is_round_trip = bool(
        fields.get("return_date")
        or str(fields.get("trip_type") or "").lower() == "round_trip"
        or selection.get("return_leg")
    )
    outbound = selection.get("outbound") if isinstance(selection.get("outbound"), dict) else chosen
    inbound = (selection.get("return_leg") if isinstance(selection.get("return_leg"), dict) else chosen.get("paired_return")) if is_round_trip else None

    origin = _first_available(fields.get("origin"), selection.get("origin"), chosen.get("origin"))
    destination = _first_available(fields.get("destination"), selection.get("destination"), chosen.get("destination"))
    departure_date = _first_available(fields.get("date"), selection.get("departure_date"))
    return_date = _first_available(fields.get("return_date"), selection.get("return_date")) if is_round_trip else None
    legs = [
        _leg_brief(outbound, "Outbound", departure_date),
        _leg_brief(inbound, "Return", return_date, applicable=bool(inbound)) if inbound else _leg_brief(None, "Return", return_date, applicable=False),
    ]

    outbound_raw = _first_available(selection.get("outbound_fare"), chosen.get("price"))
    return_raw = _first_available(selection.get("return_fare"), (inbound or {}).get("price")) if is_round_trip else None
    combined_raw = _first_available(selection.get("combined_fare"), chosen.get("combined_fare"))
    outbound_fare = _money(outbound_raw)
    return_fare = _money(return_raw)
    if is_round_trip:
        total_raw = None
        if outbound_raw is not None and return_raw is not None:
            try:
                total_raw = int(outbound_raw) + int(return_raw)
            except (TypeError, ValueError):
                total_raw = None
        if total_raw is not None and combined_raw is not None:
            try:
                total_raw = int(combined_raw) if int(combined_raw) == total_raw else total_raw
            except (TypeError, ValueError):
                pass
    else:
        total_raw = outbound_raw
    combined_fare = _money(total_raw)
    price = {
        "currency": "INR",
        "fields": [
            _field("Outbound fare", outbound_fare, INVENTORY_SOURCE, NOT_PROVIDED if flights else PENDING),
            _field("Return fare", return_fare, INVENTORY_SOURCE, NOT_APPLICABLE if not is_round_trip else NOT_PROVIDED),
            _field("Total fare", combined_fare, INVENTORY_SOURCE, NOT_APPLICABLE if is_round_trip else PENDING),
        ],
    }

    summary = {
        "fields": [
            _field("Origin", origin, SESSION_SOURCE, PENDING),
            _field("Destination", destination, SESSION_SOURCE, PENDING),
            _field("Trip type", _first_available(fields.get("trip_type"), selection.get("trip_type")), SESSION_SOURCE, PENDING),
            _field("Departure date", departure_date, SESSION_SOURCE, PENDING),
            _field("Return date", return_date, SESSION_SOURCE, NOT_APPLICABLE if not is_round_trip else PENDING),
            _field("Selection status", selection.get("status"), "locked itinerary state", NOT_APPLICABLE),
        ]
    }

    conditions = [
        "This briefing is for planning only and is not a confirmed booking.",
        "Flight records originate from bundled demo inventory; live airline availability was not checked.",
    ]
    safety = result.get("safety_report") if isinstance(result.get("safety_report"), dict) else {}
    if safety.get("disclaimer"):
        conditions.append(str(safety["disclaimer"]))
    watcher = _watcher_brief(memory_data, watcher_result)
    preferences = _preference_brief(result, memory_data)

    missing: List[str] = []
    missing_details: List[Dict[str, str]] = []
    required_missing: List[str] = []
    optional_missing: List[str] = []
    missing_groups: List[Dict[str, Any]] = []

    def add_missing(group_name: str, kind: str, label: str, reason: str) -> None:
        if label in missing:
            return
        missing.append(label)
        detail = {"label": label, "reason": reason, "group": group_name, "kind": kind}
        missing_details.append(detail)
        if kind == "optional":
            optional_missing.append(label)
        else:
            required_missing.append(label)
        group = next((item for item in missing_groups if item["group"] == group_name and item["kind"] == kind), None)
        if group:
            group["labels"].append(label)
            group["details"].append(detail)
        else:
            missing_groups.append({"group": group_name, "kind": kind, "labels": [label], "details": [detail]})

    group_specs = [
        (summary, "Travel summary", "required", set()),
        (price, "Price breakdown", "required", set()),
        (watcher, "Watcher information", "optional", set()),
    ]
    for leg in legs:
        leg_kind = "optional" if not leg.get("available") else "required"
        group_specs.append((leg, f"{leg.get('direction', 'Flight')} leg", leg_kind, {"Layover"}))
    for group, group_name, kind, optional_labels in group_specs:
        for item in group.get("fields", []):
            if item.get("status") == "unavailable" and item.get("label"):
                add_missing(
                    group_name,
                    "optional" if item["label"] in optional_labels else kind,
                    item["label"],
                    str(item.get("reason") or PENDING),
                )
    for item in preferences:
        if item.get("status") == "unavailable" and item.get("label"):
            add_missing("Passenger preferences", "optional", item["label"], str(item.get("reason") or PENDING))
    warnings = [
        "Not a booking: no payment, reservation, ticket number, or confirmation reference is included.",
        "Live airline verification is unavailable in this demo environment.",
    ]
    if watcher["status"] == "SIMULATED":
        warnings.append(watcher["disclosure"])
    if "Layover" in missing:
        warnings.append("Layover details are not provided by the demo inventory.")
    if is_round_trip and not inbound:
        conditions.append("No verified return option was found for this itinerary; no return leg or paired fare was added.")
        warnings.append("No verified return option is available for this itinerary; no return leg or paired fare was added.")
    availability = "unavailable" if not origin and not destination and not outbound and not inbound else "partial" if missing else "available"

    verification = _verification_brief(result, watcher, missing, warnings, availability)
    audit = {
        "sources": [
            {
                "item": "Flight schedule, airline and fare",
                "source": INVENTORY_SOURCE,
                "status": verification["inventory_status"],
            },
            {
                "item": "Passenger preferences",
                "source": SESSION_SOURCE,
                "status": "available" if any(item["status"] == "available" for item in preferences) else "unavailable",
            },
            {
                "item": "Watcher information",
                "source": watcher["source"] or "none",
                "status": watcher["status"],
            },
        ],
        "checks": safety.get("checks", []) if isinstance(safety.get("checks"), list) else [],
        "warnings": warnings,
    }

    ranking = {"fields": []}
    if ranking_weights:
        ranking = {"fields": [
            _field("Price weight", _weight_percent(ranking_weights.get("price")), SESSION_SOURCE),
            _field("Speed weight", _weight_percent(ranking_weights.get("speed", ranking_weights.get("duration"))), SESSION_SOURCE),
            _field("Comfort weight", _weight_percent(ranking_weights.get("comfort")), SESSION_SOURCE),
            _field("Timing weight", _weight_percent(ranking_weights.get("timing")), SESSION_SOURCE),
        ]}
    return {
        "summary": summary,
        "legs": legs,
        "price": price,
        "ranking": ranking,
        "preferences": preferences,
        "conditions": conditions,
        "watcher": watcher,
        "verification": verification,
        "audit": audit,
        "missing": missing,
        "missing_details": missing_details,
        "missing_groups": missing_groups,
        "required_missing": required_missing,
        "optional_missing": optional_missing,
        "warnings": warnings,
        "text": build_briefing_text(
            {
                "summary": summary,
                "legs": legs,
                "price": price,
                "preferences": preferences,
                "conditions": conditions,
                "watcher": watcher,
                "verification": verification,
                "missing": missing,
                "missing_details": missing_details,
                "missing_groups": missing_groups,
                "required_missing": required_missing,
                "optional_missing": optional_missing,
                "warnings": warnings,
            }
        ),
    }


def build_briefing_text(briefing: Dict[str, Any]) -> str:
    lines = ["SKYSCOUT FLIGHT BRIEFING", ""]
    verification = briefing.get("verification") or {}
    lines.append(f"Status: {verification.get('status', 'PREVIEW')}")
    lines.append(f"Data availability: {verification.get('data_availability', 'unavailable')}")
    lines.append(f"Timestamp ({verification.get('timestamp_kind', 'generation')}): {verification.get('timestamp', 'unavailable')}")
    lines.append(f"Source: {verification.get('source', 'assembled application state')}")
    lines.append("")
    lines.append("TRAVEL SUMMARY")
    for item in (briefing.get("summary") or {}).get("fields", []):
        lines.append(f"- {item['label']}: {_display(item)}")
    for leg in briefing.get("legs") or []:
        lines.append("")
        lines.append(f"{leg.get('direction', 'FLIGHT').upper()} LEG")
        for item in leg.get("fields", []):
            lines.append(f"- {item['label']}: {_display(item)}")
    lines.append("")
    lines.append("PRICE BREAKDOWN")
    for item in (briefing.get("price") or {}).get("fields", []):
        lines.append(f"- {item['label']}: {_display(item)}")
    lines.append("")
    lines.append("RELEVANT PREFERENCES")
    for item in briefing.get("preferences") or []:
        if item.get("status") == "available":
            lines.append(f"- {item['label']}: {item['value']}")
    lines.append("")
    lines.append("IMPORTANT CONDITIONS")
    for text in briefing.get("conditions") or []:
        lines.append(f"- {text}")
    watcher = briefing.get("watcher") or {}
    lines.append("")
    lines.append("WATCHER INFORMATION")
    lines.append(f"- Status: {watcher.get('status', 'UNAVAILABLE')}")
    lines.append(f"- Disclosure: {watcher.get('disclosure', 'No watcher data available.')}")
    for item in watcher.get("fields", []):
        lines.append(f"- {item['label']}: {_display(item)}")
    lines.append("")
    lines.append("WARNINGS AND MISSING INFORMATION")
    for text in briefing.get("warnings") or []:
        lines.append(f"- {text}")
    groups = briefing.get("missing_groups") or []
    if groups:
        lines.append("UNAVAILABLE INFORMATION BY CATEGORY")
        for group in groups:
            labels = ", ".join(group.get("labels") or [])
            lines.append(f"- Unavailable {group.get('group', 'information')} ({group.get('kind', 'required')}): {labels}")
            for detail in group.get("details") or []:
                lines.append(f"  - {detail['label']}: {detail['reason']}")
    else:
        for label in briefing.get("missing") or []:
            lines.append(f"- Unavailable: {label}")
    return "\n".join(lines)
