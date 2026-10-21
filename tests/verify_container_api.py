"""Automated End-to-End Container API Verification Test Suite.

Verifies every frontend API request and response schema through the
Nginx reverse proxy at http://localhost:3000/api/v1/.
"""

import sys
import json
import urllib.request
import urllib.error
import urllib.parse
from typing import Any, Tuple, Dict

DEFAULT_BASE_URL = "http://127.0.0.1:3000"


class VerificationRunner:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.passed = 0
        self.failed = 0
        self.results = []

    def log_result(self, name: str, success: bool, message: str = ""):
        if success:
            self.passed += 1
            print(f"  [PASS] {name} {message}", flush=True)
        else:
            self.failed += 1
            print(f"  [FAIL] {name} {message}", flush=True)
        self.results.append({"name": name, "success": success, "message": message})

    def request(
        self,
        path: str,
        method: str = "GET",
        body: Any = None,
        params: Dict[str, Any] = None,
    ) -> Tuple[int, Any, Dict[str, str]]:
        url = f"{self.base_url}{path}"
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if query:
                url = f"{url}?{query}"

        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_body = resp.read().decode("utf-8")
                content_type = resp.headers.get("Content-Type", "")
                parsed = json.loads(resp_body) if "application/json" in content_type else resp_body
                return resp.status, parsed, dict(resp.headers)
        except urllib.error.HTTPError as e:
            resp_body = e.read().decode("utf-8")
            try:
                parsed = json.loads(resp_body)
            except Exception:
                parsed = resp_body
            return e.code, parsed, dict(e.headers)
        except Exception as e:
            return 0, str(e), {}

    def run_all(self):
        print(f"\n========================================================")
        print(f"  Starting GridVision Container API Verification Suite")
        print(f"  Target: {self.base_url}")
        print(f"========================================================\n")

        # 1. Frontend Web & SPA Fallback Checks
        print("[1] Verifying Frontend & Static Asset Routing:")
        status, body, _ = self.request("/")
        self.log_result("Frontend Root (GET /)", status == 200 and "GridVision" in str(body))

        status, body, _ = self.request("/nginx-health")
        self.log_result("Nginx Health (GET /nginx-health)", status == 200 and "healthy" in str(body))

        status, body, _ = self.request("/dashboard/commercial")
        self.log_result("SPA Routing Fallback (GET /dashboard/commercial)", status == 200 and "html" in str(body).lower())

        # 2. Health & Diagnostic Endpoints
        print("\n[2] Verifying Health & Platform Endpoints:")
        status, body, _ = self.request("/api/v1/health")
        self.log_result("Liveness Check (GET /api/v1/health)", status == 200 and body.get("data", {}).get("status") in ("alive", "live"))

        status, body, _ = self.request("/api/v1/ready")
        self.log_result("Readiness Check (GET /api/v1/ready)", status == 200 and body.get("data", {}).get("status") == "ready")

        status, body, _ = self.request("/api/v1/platform/health")
        self.log_result("Platform Health Summary (GET /api/v1/platform/health)", status == 200 and "models" in body.get("data", {}))

        # 3. Overview Endpoint
        print("\n[3] Verifying Executive Overview:")
        status, body, _ = self.request("/api/v1/overview")
        data = body.get("data", {}) if isinstance(body, dict) else {}
        self.log_result(
            "Overview Endpoint (GET /api/v1/overview)",
            status == 200 and "kpis" in data and "peakAnalysis" in data
        )

        # 4. Entities Endpoints
        print("\n[4] Verifying Entity Discovery Endpoints:")
        status, body, _ = self.request("/api/v1/entities/commercial")
        data = body.get("data", [])
        self.log_result("Commercial Entities (GET /api/v1/entities/commercial)", status == 200 and len(data) > 0)

        status, body, _ = self.request("/api/v1/entities/residential")
        data = body.get("data", [])
        self.log_result("Residential Entities (GET /api/v1/entities/residential)", status == 200 and len(data) > 0)

        status, body, _ = self.request("/api/v1/entities/government")
        data = body.get("data", [])
        self.log_result("Government Entities (GET /api/v1/entities/government)", status == 200 and len(data) > 0)

        # 5. Forecast Horizons
        print("\n[5] Verifying Forecast Prediction Horizons:")
        status, body, _ = self.request("/api/v1/forecast/commercial/Panther_office_1")
        data = body.get("data", {})
        self.log_result("Commercial Forecast (GET /api/v1/forecast/commercial/Panther_office_1)", status == 200 and "horizon" in data)

        status, body, _ = self.request("/api/v1/forecast/residential/Green_house_1")
        data = body.get("data", {})
        self.log_result("Residential Forecast (GET /api/v1/forecast/residential/Green_house_1)", status == 200 and "horizon" in data)

        # 6. Dashboard Endpoints
        print("\n[6] Verifying Dashboard Data Endpoints:")
        status, body, _ = self.request("/api/v1/dashboard/commercial", params={"tab": "building", "time_range": "1D", "building_id": "Panther_office_1"})
        data = body.get("data", {})
        self.log_result("Commercial Dashboard (GET /api/v1/dashboard/commercial)", status == 200 and "curve" in data)

        status, body, _ = self.request("/api/v1/dashboard/household", params={"household_id": "Green_house_1"})
        data = body.get("data", {})
        self.log_result("Household Dashboard (GET /api/v1/dashboard/household)", status == 200 and "consumptionCurve" in data)

        status, body, _ = self.request("/api/v1/dashboard/government/regions")
        data = body.get("data", [])
        self.log_result("Government Regions (GET /api/v1/dashboard/government/regions)", status == 200 and len(data) > 0)

        status, body, _ = self.request("/api/v1/dashboard/government", params={"view_type": "overall", "time_range": "1D"})
        data = body.get("data", {})
        self.log_result("Government Dashboard (GET /api/v1/dashboard/government)", status == 200 and "curve" in data)

        # 7. Historical Analysis
        print("\n[7] Verifying Historical Demand Analysis:")
        status, body, _ = self.request("/api/v1/historical", params={"persona": "commercial", "time_range": "30D", "entity_id": "Panther_office_1"})
        data = body.get("data", {})
        self.log_result("Historical Analysis (GET /api/v1/historical)", status == 200 and "historyCurve" in data)

        # 8. Peak Demand & Curtailment
        print("\n[8] Verifying Peak Demand & Dispatch:")
        status, body, _ = self.request("/api/v1/peak-demand")
        data = body.get("data", {})
        self.log_result("Peak Demand Analysis (GET /api/v1/peak-demand)", status == 200 and "currentLoadMw" in data)

        status, body, _ = self.request("/api/v1/peak-demand/curtail", method="POST", body={"curtailment_mw": 25.0, "duration_hours": 2.0})
        data = body.get("data", {})
        self.log_result("Curtailment Dispatch (POST /api/v1/peak-demand/curtail)", status == 200 and data.get("dispatchConfirmed") is True)

        # 9. Anomalies Management
        print("\n[9] Verifying Anomaly Detection & Updates:")
        status, body, _ = self.request("/api/v1/anomalies", params={"severity": "all", "status": "all"})
        data = body.get("data", [])
        first_event_id = data[0].get("id") if data else "evt-001"
        self.log_result("Get Anomalies (GET /api/v1/anomalies)", status == 200 and len(data) > 0)

        status, body, _ = self.request(f"/api/v1/anomalies/{first_event_id}", method="PATCH", body={"status": "resolved"})
        data = body.get("data", {})
        self.log_result(f"Update Anomaly Status (PATCH /api/v1/anomalies/{first_event_id})", status == 200 and data.get("status") == "resolved")

        # 10. Customer Segmentation & Diurnal Curves
        print("\n[10] Verifying Customer Analytics:")
        status, body, _ = self.request("/api/v1/customers/segments")
        self.log_result("Customer Segments (GET /api/v1/customers/segments)", status == 200 and len(body.get("data", [])) > 0)

        status, body, _ = self.request("/api/v1/customers/diurnal-curves")
        self.log_result("Diurnal Curves (GET /api/v1/customers/diurnal-curves)", status == 200 and len(body.get("data", [])) > 0)

        status, body, _ = self.request("/api/v1/customers/segmentation-matrix")
        self.log_result("Segmentation Matrix (GET /api/v1/customers/segmentation-matrix)", status == 200 and "totalCustomers" in body.get("data", {}))

        # 11. Business Insights & AI Assistant
        print("\n[11] Verifying Energy Insights & Domain Assistant:")
        status, body, _ = self.request("/api/v1/energy-insights")
        self.log_result("Energy Insights (GET /api/v1/energy-insights)", status == 200 and len(body.get("data", [])) > 0)

        status, body, _ = self.request("/api/v1/assistant/chat", method="POST", body={"prompt": "How can I reduce peak load?", "persona": "commercial", "entity_id": "Panther_office_1"})
        data = body.get("data", {})
        self.log_result("AI Assistant Chat (POST /api/v1/assistant/chat)", status == 200 and "answer" in data)

        # 12. Negative & Edge Case Validation
        print("\n[12] Verifying Negative & Error Handling:")
        status, body, _ = self.request("/api/v1/nonexistent-endpoint")
        self.log_result("Route Not Found (GET /api/v1/nonexistent-endpoint -> 404)", status == 404)

        status, body, _ = self.request("/api/v1/overview", method="POST", body={"invalid": "payload"})
        self.log_result("Method Not Allowed (POST /api/v1/overview -> 405)", status == 405)

        status, body, _ = self.request("/api/v1/peak-demand/curtail", method="POST", body={"curtailment_mw": "invalid_type"})
        self.log_result("Validation Failure (POST /api/v1/peak-demand/curtail with invalid body -> 422)", status == 422)

        # Final Summary
        total = self.passed + self.failed
        print("\n========================================================")
        print(f"  Container Verification Results: {self.passed}/{total} Passed")
        if self.failed == 0:
            print("  ALL CONTAINER ENDPOINTS VERIFIED SUCCESSFULLY!")
        else:
            print(f"  {self.failed} CHECKS FAILED.")
        print("========================================================\n")
        return self.failed == 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    runner = VerificationRunner(target)
    success = runner.run_all()
    sys.exit(0 if success else 1)
