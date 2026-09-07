"""Dependency-light HTTP command center for the Fraud War Room demo."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from threading import RLock
from urllib.parse import urlparse

from coded_tools.fraud_defense.benchmark import run_benchmark
from coded_tools.fraud_defense.orchestration import FraudDefenseEngine


ROOT = Path(__file__).parent
ENGINE = FraudDefenseEngine()
ENGINE_LOCK = RLock()


def _neuro_san_status() -> dict[str, Any]:
    """Report whether the optional Neuro SAN runtime is installed locally."""
    try:
        import neuro_san  # type: ignore

        return {"available": True, "version": getattr(neuro_san, "__version__", "installed")}
    except ImportError:
        return {"available": False, "version": None}


NETWORK_TOPOLOGY = {
    "nodes": [
        {"id": "fraud_commander", "label": "Fraud Commander", "group": "command"},
        {"id": "case_intake", "label": "Signal Intake", "group": "intake"},
        {"id": "triage_router", "label": "Triage Router", "group": "triage"},
        {"id": "run_case_review", "label": "Deterministic Case Packet", "group": "investigate"},
        {"id": "behavioral_signals", "label": "Behavioral Signal Lab", "group": "investigate"},
        {"id": "relationship_forensics", "label": "Relationship Forensics", "group": "investigate"},
        {"id": "customer_baseline", "label": "Customer Baseline", "group": "investigate"},
        {"id": "evidence_synthesizer", "label": "Evidence Librarian", "group": "understand"},
        {"id": "hypothesis_lab", "label": "Competing Hypothesis Lab", "group": "challenge"},
        {"id": "adversary_in_residence", "label": "Adversary in Residence", "group": "challenge"},
        {"id": "defense_architect", "label": "Defense Architect", "group": "defend"},
        {"id": "counterfactual_simulator", "label": "Counterfactual Simulator", "group": "simulate"},
        {"id": "model_jury", "label": "Independent Model Jury", "group": "jury"},
        {"id": "governance_gate", "label": "Governance Gate", "group": "govern"},
        {"id": "decision_passport", "label": "Decision Passport", "group": "audit"},
        {"id": "human_approval_gate", "label": "Human Approval Gate", "group": "approve"},
        {"id": "shadow_observer", "label": "Shadow Observer", "group": "shadow"},
        {"id": "outcome_learner", "label": "Outcome Learning Loop", "group": "learn"},
    ],
    "edges": [
        {"source": "fraud_commander", "target": "case_intake"},
        {"source": "case_intake", "target": "triage_router"},
        {"source": "triage_router", "target": "run_case_review"},
        {"source": "triage_router", "target": "behavioral_signals"},
        {"source": "triage_router", "target": "relationship_forensics"},
        {"source": "triage_router", "target": "customer_baseline"},
        {"source": "triage_router", "target": "evidence_synthesizer"},
        {"source": "evidence_synthesizer", "target": "hypothesis_lab"},
        {"source": "hypothesis_lab", "target": "adversary_in_residence"},
        {"source": "adversary_in_residence", "target": "defense_architect"},
        {"source": "defense_architect", "target": "counterfactual_simulator"},
        {"source": "counterfactual_simulator", "target": "model_jury"},
        {"source": "model_jury", "target": "governance_gate"},
        {"source": "governance_gate", "target": "decision_passport"},
        {"source": "decision_passport", "target": "human_approval_gate"},
        {"source": "human_approval_gate", "target": "shadow_observer"},
        {"source": "shadow_observer", "target": "outcome_learner"},
    ],
}


def _json_response(handler: BaseHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    """Write a JSON response with safe browser defaults."""
    body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


class FraudWarRoomHandler(BaseHTTPRequestHandler):
    """Serve dashboard assets and investigator API endpoints."""

    server_version = "FraudWarRoom/1.0"

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def handle_one_request(self) -> None:
        self.connection.settimeout(15)
        # The workbench's mutable cache and lifecycle transitions are single writer.
        with ENGINE_LOCK:
            super().handle_one_request()

    def log_message(self, format_string: str, *args: Any) -> None:
        """Keep terminal output concise and free of request bodies."""
        print(f"[war-room] {format_string % args}")

    def do_GET(self) -> None:  # noqa: N802
        """Handle dashboard and read-only API requests."""
        path = urlparse(self.path).path
        try:
            if path == "/" or path == "/index.html":
                return self._file("index.html", "text/html; charset=utf-8")
            if path.startswith("/static/"):
                return self._file(path.removeprefix("/"), None)
            if path == "/api/health":
                return _json_response(self, {"status": "ok", "service": "fraud-war-room", "neuro_san_network": "registries/industry/fraud_defense.hocon", "neuro_san_runtime": _neuro_san_status(), "execution_mode": "deterministic_coded_tool_workbench"})
            if path == "/api/network":
                return _json_response(self, NETWORK_TOPOLOGY)
            if path == "/api/cases":
                return _json_response(self, {"cases": ENGINE.list_cases(40)})
            if path == "/api/bootstrap":
                return _json_response(self, {"network": NETWORK_TOPOLOGY, "cases": ENGINE.list_cases(40), "investigation": ENGINE.investigate("CASE-0001")})
            if path.startswith("/api/cases/"):
                case_id = path.split("/")[-1]
                return _json_response(self, ENGINE.investigate(case_id))
            return _json_response(self, {"error": "not_found"}, 404)
        except (KeyError, ValueError, OSError) as exc:
            return _json_response(self, {"error": str(exc), "recoverable": True}, 400)

    def do_POST(self) -> None:  # noqa: N802
        """Handle human approval, shadow advancement, and benchmark requests."""
        path = urlparse(self.path).path
        try:
            origin = self.headers.get("Origin")
            if self.headers.get("Sec-Fetch-Site") == "cross-site" or (origin and urlparse(origin).netloc != self.headers.get("Host")):
                return _json_response(self, {"error": "cross_origin_request_denied"}, 403)
            if path == "/api/benchmark":
                return _json_response(self, run_benchmark(output_path=Path("artifacts") / "fraud_benchmark.json"))
            if path.startswith("/api/cases/") and path.endswith("/approve"):
                case_id = path.split("/")[-2]
                payload = self._body()
                if type(payload.get("approved")) is not bool:
                    raise ValueError("approved must be an explicit boolean")
                return _json_response(self, ENGINE.approve(case_id, payload["approved"]))
            if path.startswith("/api/cases/") and path.endswith("/reject"):
                case_id = path.split("/")[-2]
                return _json_response(self, ENGINE.approve(case_id, False))
            if path.startswith("/api/cases/") and path.endswith("/more-investigation"):
                case_id = path.split("/")[-2]
                return _json_response(self, ENGINE.request_more_investigation(case_id))
            if path.startswith("/api/cases/") and path.endswith("/shadow-advance"):
                case_id = path.split("/")[-2]
                return _json_response(self, ENGINE.advance_shadow(case_id))
            return _json_response(self, {"error": "not_found"}, 404)
        except (KeyError, ValueError, OSError) as exc:
            return _json_response(self, {"error": str(exc), "recoverable": True}, 400)

    def _body(self) -> dict[str, Any]:
        """Read a small JSON request body."""
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > 100_000:
            raise ValueError("request body too large")
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Transfer-Encoding is unsupported")
        raw = self.rfile.read(length) if length else b"{}"
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def _file(self, relative: str, content_type: str | None) -> None:
        """Serve a static file constrained to the app directory."""
        target = (ROOT / relative).resolve()
        if ROOT.resolve() not in target.parents and target != ROOT.resolve():
            return _json_response(self, {"error": "invalid_path"}, 400)
        if not target.is_file():
            return _json_response(self, {"error": "not_found"}, 404)
        body = target.read_bytes()
        mime = content_type or {
            ".css": "text/css; charset=utf-8",
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }.get(target.suffix, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    """Start the local command center."""
    parser = argparse.ArgumentParser(description="Run the local Fraud War Room command center")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("This investigator workbench requires loopback binding; remote access needs an authenticated gateway.")
    server = ThreadingHTTPServer((args.host, args.port), FraudWarRoomHandler)
    print(f"Fraud War Room: http://{args.host}:{args.port}")
    print("Synthetic data only. High-risk controls remain in SHADOW after human approval.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Fraud War Room.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
