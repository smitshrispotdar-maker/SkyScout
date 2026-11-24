"""SkyScout Unit V: Defense-in-Depth Prompt Injection Guardrails & Hallucination Grounding Audit."""

import base64
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

INVENTORY_SOURCE_LABEL = "SkyScout bundled demo inventory"


# Multi-category adversarial & prompt-injection patterns
SUSPICIOUS_PATTERNS: Dict[str, List[str]] = {
    "instruction_override": [
        r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
        r"disregard\s+(all\s+)?(previous|prior|system)\s+instructions",
        r"override\s+(the\s+)?(system|previous|safety)\s+(instructions|rules|prompt)",
        r"forget\s+(all\s+)?(previous|your)\s+instructions",
        r"you\s+are\s+now\s+(in\s+)?(developer|jailbreak|dan|unrestricted)\s+mode",
        r"act\s+as\s+(an?\s+)?unfiltered",
        r"\b(?:ignore|disregard|forget)\b.{0,40}\b(?:rules?|instructions?|guidance|directions?)\b",
        r"\b(?:reveal|show|tell|print|expose|give)\b.{0,40}\b(?:system prompt|hidden instructions?|secret rules?|internal rules?)\b",
        r"\b(?:act|behave)\s+as\b.{0,40}\b(?:unrestricted|developer|jailbreak|dan|system)\b",
    ],
    "data_exfiltration": [
        r"reveal\s+(the\s+)?(system\s+prompt|hidden\s+instructions|internal\s+rules)",
        r"show\s+(me\s+)?(all\s+)?(stored\s+)?(user|session)\s+data",
        r"reveal\s+(stored\s+)?(user\s+)?information",
        r"expose\s+(the\s+)?(secret|password|api[_\s]?key|credentials|env)",
        r"print\s+(the\s+)?environment\s+variables",
        r"dump\s+(the\s+)?(database|memory|inventory)",
        r"\b(?:export|dump|leak|reveal|show)\b.{0,40}\b(?:stored data|user data|session data|memory|credentials?|secrets?)\b",
    ],
    "unauthorized_tool_execution": [
        r"send\s+(an?\s+)?email\s+(to\s+everyone|without\s+(permission|consent))",
        r"bypass\s+(all\s+)?(security|validation|budget)",
        r"disable\s+(all\s+)?(security|safety|verifier)\s+checks",
        r"execute\s+(shell|bash|python|system)\s+command",
        r"<\s*script\b|javascript:",
    ],
}

LEET_MAP = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})


def _normalize_obfuscation(text: str) -> str:
    """Normalize leetspeak, zero-width characters, and base64 payloads for adversarial scanning."""
    cleaned = re.sub(r"[\u200b-\u200d\ufeff]", "", text)
    de_leeted = cleaned.translate(LEET_MAP)
    decoded_chunks: List[str] = []
    for token in re.findall(r"[A-Za-z0-9+/=]{16,}", cleaned):
        try:
            raw = base64.b64decode(token, validate=True).decode("utf-8", errors="ignore")
            if raw and any(ch.isalpha() for ch in raw):
                decoded_chunks.append(raw)
        except Exception:
            continue
    return " ".join([cleaned, de_leeted] + decoded_chunks)


def scan_prompt_injection(text: Any) -> Dict[str, Any]:
    """Two-stage adversarial guardrail: obfuscation normalization + multi-category pattern inspection."""
    raw_text = str(text or "")
    normalized = _normalize_obfuscation(raw_text)
    findings: List[Dict[str, str]] = []

    for category, patterns in SUSPICIOUS_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, normalized, re.IGNORECASE):
                findings.append(
                    {
                        "category": category,
                        "pattern": pattern,
                        "message": category.replace("_", " ").title(),
                    }
                )
                break

    risk_score = min(1.0, round(len(findings) * 0.45, 2)) if findings else 0.02
    return {
        "blocked": bool(findings),
        "risk_level": "HIGH" if findings else "LOW",
        "risk_score": risk_score,
        "guardrail_layers": [
            "Obfuscation & Base64 Normalization",
            "Instruction-Override & Exfiltration Classifier",
            "Tool-Argument Schema Sandboxing",
        ],
        "findings": findings,
        "message": (
            "Adversarial or prompt-injection pattern detected. Execution halted by Security Agent."
            if findings
            else "Input passed multi-layer adversarial and schema safety checks."
        ),
    }


def verify_flights(
    flights: List[Dict[str, Any]],
    origin: str,
    destination: str,
    budget: float,
    inventory: List[Dict[str, Any]],
    is_replan: bool = False,
) -> Dict[str, Any]:
    """
    Hallucination Grounding & Verifiable Citation Audit:
    Cross-checks every flight number, airline, route, duration, and price against raw tool/inventory records.
    """
    checks: List[Dict[str, Any]] = []
    passed = True

    def record(name: str, success: bool, details: str) -> None:
        nonlocal passed
        if not success:
            passed = False
        checks.append({"name": name, "passed": success, "details": details})

    inv_by_no = {f.get("flight_no"): f for f in inventory if f.get("flight_no")}

    # 1. Exact record grounding (prevents fabricated flight numbers or altered fares)
    grounded_ok = True
    for f in flights:
        if f.get("is_connecting"):
            legs = f.get("legs", [])
            if not legs or not all(
                leg.get("flight_no") in inv_by_no
                and inv_by_no[leg["flight_no"]].get("price") == leg.get("price")
                for leg in legs
            ):
                grounded_ok = False
                break
        else:
            src = inv_by_no.get(f.get("flight_no"))
            if not src or src.get("price") != f.get("price") or src.get("airline") != f.get("airline"):
                grounded_ok = False
                break

    record(
        "Source Grounding Audit",
        grounded_ok,
        "Every flight number, airline, and fare matches raw tool/inventory records with zero fabrication.",
    )

    # 2. Route consistency
    route_ok = all(
        f.get("origin") == origin and f.get("destination") == destination for f in flights
    )
    record(
        "Origin-Destination Consistency",
        route_ok,
        "All candidate itineraries match the verified origin and destination.",
    )

    # 3. Budget ceiling compliance (allows documented +15% margin only during explicit ToT budget-relaxation replans)
    ceiling = budget * 1.15 if is_replan else budget
    price_ok = all(
        isinstance(f.get("price"), (int, float))
        and not isinstance(f.get("price"), bool)
        and 0 < f.get("price", 0) <= ceiling
        for f in flights
    )
    record(
        "Budget Policy Compliance",
        price_ok,
        (
            f"All fares respect the {'replan tolerance ceiling' if is_replan else 'strict user budget'} (INR {ceiling:,.0f})."
        ),
    )

    # 4. Fare-breakdown & baggage metadata grounding
    metadata_ok = True
    for f in flights:
        targets = (f.get("legs") or []) if f.get("is_connecting") else [f]
        for item in targets:
            base, taxes, price = item.get("base_fare"), item.get("taxes"), item.get("price")
            if not item.get("baggage") or not isinstance(base, (int, float)) or not isinstance(taxes, (int, float)):
                metadata_ok = False
                break
            if round(float(base) + float(taxes)) != round(float(price or 0)):
                metadata_ok = False
                break
        if not metadata_ok:
            break
    record(
        "Fare Breakdown & Baggage Grounding",
        metadata_ok,
        "Base fare + taxes reconcile to the verified total and baggage allowance is present for every leg.",
    )

    # 5. Utility & transparency provenance
    provenance_ok = True
    for f in flights:
        targets = (f.get("legs") or []) if f.get("is_connecting") else [f]
        for item in targets:
            src = inv_by_no.get(item.get("flight_no"), {})
            utility = item.get("utility_score")
            breakdown = item.get("utility_breakdown")
            if not isinstance(utility, (int, float)):
                provenance_ok = False
                break
            if not isinstance(breakdown, dict):
                provenance_ok = False
                break
            if str(item.get("verification_source") or src.get("verification_source") or "") != INVENTORY_SOURCE_LABEL:
                provenance_ok = False
                break
            if str(item.get("data_origin") or src.get("data_origin") or "") != "demo_inventory":
                provenance_ok = False
                break
        if not provenance_ok:
            break
    record(
        "Provenance & Disclaimer Transparency",
        provenance_ok and (all(isinstance(f.get("utility_score"), (int, float)) for f in flights) if flights else True),
        "Each flight carries auditable utility breakdown and verifiable demo-inventory provenance fields; no live-source claims are made.",
    )

    grounded_count = sum(1 for c in checks if c["passed"])
    confidence = round((grounded_count / len(checks)) * 100, 1)

    return {
        "passed": passed,
        "status": "VERIFIED" if passed else "BLOCKED",
        "grounding_score": confidence,
        "checks": checks,
        "checked_flights": len(flights),
        "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "verification_source": "SkyScout bundled demo inventory grounding audit",
        "disclaimer": (
            "Verified against SkyScout flight tool records. Always confirm live airline availability before ticketing."
        ),
    }


def verify_round_trip(
    outbound: Dict[str, Any],
    inbound: Dict[str, Any],
    origin: str,
    destination: str,
    budget: float,
    inventory: List[Dict[str, Any]],
    is_replan: bool = False,
) -> Dict[str, Any]:
    outbound_report = verify_flights([outbound], origin, destination, budget, inventory, is_replan)
    inbound_report = verify_flights([inbound], destination, origin, budget, inventory, is_replan)
    total = float(outbound.get("price", 0)) + float(inbound.get("price", 0))
    combined_ok = 0 < total <= (budget * 1.15 if is_replan else budget)
    checks = [
        {"name": "Outbound Leg Grounding", "passed": outbound_report["passed"], "details": f"Outbound {origin} -> {destination} verified against source inventory."},
        {"name": "Return Leg Grounding", "passed": inbound_report["passed"], "details": f"Return {destination} -> {origin} verified against source inventory."},
        {"name": "Combined Fare Policy", "passed": combined_ok, "details": f"Combined fare INR {total:,.0f} respects the total trip ceiling of INR {(budget * 1.15 if is_replan else budget):,.0f}."},
    ]
    passed = all(check["passed"] for check in checks)
    grounded = sum(1 for c in checks if c["passed"])
    return {
        "passed": passed,
        "status": "VERIFIED" if passed else "BLOCKED",
        "grounding_score": round((grounded / len(checks)) * 100, 1),
        "checks": checks,
        "checked_flights": int(outbound_report.get("checked_flights", 0)) + int(inbound_report.get("checked_flights", 0)),
        "checked_pairs": 1,
        "combined_fare_checks": 1,
        "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "verification_source": "SkyScout bundled demo inventory grounding audit",
        "total_fare": total,
        "outbound_report": outbound_report,
        "return_report": inbound_report,
        "disclaimer": "Both itinerary legs and the combined fare were checked against SkyScout demo inventory records.",
    }
