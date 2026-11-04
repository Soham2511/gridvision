# Complaint Center Integration Context

This document captures the complete architectural, functional, and integration context of the **Complaint Center** functionality removed from the current branch. Use this guide when merging the dedicated Complaint Center branch back into GridVision.

---

## 1. Feature Overview and Expected Workflows

The Complaint Center provides a simulated electricity complaint and ticketing workflow across residential, commercial, and government personas.

### Workflows

#### 1. Consumer Workflow (Household & Commercial)
1. **Creation**:
   - The user inputs an issue description (up to 2,000 characters).
   - The backend runs a rule-based classifier (`_classify`) to determine:
     - **Category**: `power_outage`, `billing_discrepancy`, `meter_discrepancy`, `high_consumption`, `low_consumption`, `voltage_fluctuation`, or `other`.
     - **Safety Escalation**: Triggers on emergency keywords (`electric shock`, `shocked`, `sparking`, `smoke`, `burning smell`, `fire`, `exposed wire`). Returns immediate safety guidance advising the user to move away from hazards and call emergency services.
     - **Follow-up Questions**: Specific contextual questions generated per category.
     - **Evidence Outcome**: Defaults to `Inconclusive` in the prototype.
   - **Privacy Policy**: Free-form text is kept in request memory only during classification; only category-level summaries are saved in the database.
2. **Draft State**:
   - The complaint is stored with status `draft`.
3. **Explicit Confirmation**:
   - A draft is only visible to the owner.
   - The consumer must explicitly confirm the draft (`POST /api/v1/ai/complaints/<id>/confirm` with `{"confirm": true}`).
   - Confirmation transitions the status to `submitted_local`.
   - Dispatches notifications to `demo:government` and the consumer's context.

#### 2. Government / Utility Workflow
1. **Queue Inspection**:
   - Government persona accesses `/app/complaints` (labeled **Complaint Queue** in the sidebar).
   - Views all consumer-confirmed submissions across entities (`status != 'draft'`).
2. **Status Progression**:
   - Government operators transition complaints through allowed state steps:
     - `submitted_local` $\rightarrow$ `under_investigation`
     - `submitted_local` $\rightarrow$ `resolved`
     - `under_investigation` $\rightarrow$ `resolved`
     - `resolved` is terminal.
   - Status updates allow an optional operator note (redacted via `redact_sensitive_text` to 500 characters).
   - Status transitions automatically notify the affected consumer.

#### 3. Complaint Investigation Reports
- Report type `complaint_investigation` in `POST /api/v1/ai/reports` allowed generating an investigation report referencing a consumer-confirmed complaint.

---

## 2. Frontend Integration Points

### 1. Navigation Link (`frontend/src/layouts/Sidebar.tsx`)
- **Icon**: `ClipboardList` from `lucide-react`.
- **Path**: `/app/complaints`
- **Label**:
  - Government persona: `'Complaint Queue'`
  - Household/Commercial persona: `'Complaints'`

### 2. Route Definition (`frontend/src/routes/AppRoutes.tsx`)
```tsx
import { ComplaintsPage } from '../pages/ComplaintsPage';
...
<Route path="/app/complaints" element={<ComplaintsPage />} />
```

### 3. Page Component (`frontend/src/pages/ComplaintsPage.tsx`)
- Provides:
  - Issue description form with character count and disclaimer.
  - Active complaint records list with category, severity, status, safety messages, and follow-up prompts.
  - Action buttons based on status:
    - Consumer: "Confirm local submission" (`confirm`)
    - Government: "Start investigation" and "Mark resolved" (`updateStatus`)

### 4. API Service Client (`frontend/src/services/aiLayerService.ts`)
TypeScript interface:
```typescript
export interface ComplaintRecord {
  complaint_id: string;
  persona: string;
  category: string;
  summary: string;
  evidence_outcome: string;
  severity: string;
  status: string;
  payload: {
    entityId?: string;
    followUpQuestions?: string[];
    safetyEscalation?: boolean;
    safetyMessage?: string | null;
    externalSubmission?: boolean;
    limitations?: string[];
  };
}
```
Client methods:
- `createComplaint(persona: string, description: string, entityId?: string)`
- `listComplaints(persona: string, entityId?: string)`
- `confirmComplaint(complaintId: string, persona: string, entityId?: string)`
- `updateComplaint(complaintId: string, status: string, note?: string)`

---

## 3. Backend Integration Points & API Routes

### Blueprint: `backend/app/api/v1/ai_layer.py`

#### 1. Request Validation Models (Pydantic)
- `DraftRequest`:
  - `persona: str`
  - `description: str = Field(min_length=1, max_length=2000)`
  - `building_id: str | None = Field(default=None, min_length=1, max_length=120)`
  - `entity_id: str | None = Field(default=None, min_length=1, max_length=120)`
- `ConfirmRequest`:
  - `confirm: bool`
- `GovernmentUpdateRequest`:
  - `status: str`
  - `note: str | None = Field(default=None, max_length=1000)`

#### 2. REST Endpoints
| HTTP Method | Endpoint | Description | Status Code |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/ai/complaints/drafts` | Create a new complaint draft. Runs classification and safety checks. | `201 Created` |
| `GET` | `/api/v1/ai/complaints` | List complaints for active persona and entity context. | `200 OK` |
| `POST` | `/api/v1/ai/complaints/<complaint_id>/confirm` | Confirm submission of a draft complaint to the local queue. | `200 OK` |
| `PATCH` | `/api/v1/ai/complaints/<complaint_id>/status` | Update status (`under_investigation`, `resolved`). Government persona only. | `200 OK` |

#### 3. Report Integration
- Handled under `POST /api/v1/ai/reports` with `report_type == "complaint_investigation"`.

---

## 4. Database Models & Storage

### Storage Engine: `backend/app/ai/application_store.py` (`AIApplicationStore`)

#### SQLite Tables
```sql
CREATE TABLE IF NOT EXISTS ai_complaints (
    complaint_id TEXT PRIMARY KEY,
    owner_context TEXT NOT NULL,
    persona TEXT NOT NULL,
    category TEXT NOT NULL,
    summary TEXT NOT NULL,
    evidence_outcome TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_complaint_history (
    history_id TEXT PRIMARY KEY,
    complaint_id TEXT NOT NULL REFERENCES ai_complaints(complaint_id),
    actor_context TEXT NOT NULL,
    action TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ai_complaints_queue_idx
    ON ai_complaints(status, severity, created_at);
```

#### ApplicationStore Methods
- `create_complaint(complaint: dict[str, Any]) -> dict[str, Any]`
- `get_complaint(complaint_id: str) -> dict[str, Any] | None`
- `list_complaints(*, owner_context: str | None = None, status: str | None = None) -> list[dict[str, Any]]`
- `transition_complaint(complaint_id: str, *, action: str, new_status: str, actor_context: str, note: str | None = None, expected_status: str | None = None) -> dict[str, Any] | None`
- `complaint_history(complaint_id: str) -> list[dict[str, Any]]`
- `_history(connection, complaint_id, actor_context, action, old_status, new_status, note)`
- `_complaint_dict(row: sqlite3.Row) -> dict[str, Any]`

---

## 5. Shared Services and External Integrations

When restoring Complaint Center, ensure compatibility with these shared infrastructure components:
1. **`AIApplicationStore`**: Shared SQLite database that also persists `ai_reports` and `ai_notifications`. Do not replace the entire store; merge the complaint tables and methods alongside reports and notifications.
2. **Notification Service**: Uses `store.notify(recipient_context, event_key, notification_type, title, body)` for event deduplication.
3. **PII Redaction**: Uses `backend/app/ai/redaction.py::redact_sensitive_text` to mask contact details and account numbers.
4. **Persona & Entity Scoping**: Uses `_entity_context(persona, building_id)` for multi-tenant isolation across `demo:household`, `demo:commercial`, and `demo:government`.

---

## 6. Files and Modules to Restore From Complaint Center Branch

| File Path | Description of Changes to Restore |
| :--- | :--- |
| `frontend/src/pages/ComplaintsPage.tsx` | Restore complete page component. |
| `frontend/src/routes/AppRoutes.tsx` | Add import and `<Route path="/app/complaints" element={<ComplaintsPage />} />`. |
| `frontend/src/layouts/Sidebar.tsx` | Add `ClipboardList` to `lucide-react` import and restore navigation item `/app/complaints`. |
| `frontend/src/services/aiLayerService.ts` | Restore `ComplaintRecord` interface and client methods (`createComplaint`, `listComplaints`, etc.). |
| `backend/app/api/v1/ai_layer.py` | Restore `DraftRequest`, `ConfirmRequest`, `GovernmentUpdateRequest`, `_classify`, endpoints, and `complaint_investigation` report handler. |
| `backend/app/ai/application_store.py` | Restore `ai_complaints` and `ai_complaint_history` tables and query methods. |
| `tests/backend/test_ai_foundation.py` | Restore complaint lifecycle and API tests. |

---

## 7. Potential Merge Conflicts and Integration Steps

1. **`backend/app/api/v1/ai_layer.py`**:
   - *Risk*: `ai_layer.py` contains the Monthly Consumption Report endpoint (`/ai/reports`) and Report Generator bindings recently improved on this branch.
   - *Resolution*: Merge only the complaint endpoints (`/ai/complaints/*`) and models without overwriting the consumption report logic.
2. **`backend/app/ai/application_store.py`**:
   - *Risk*: Table creation script and store methods.
   - *Resolution*: Append the `ai_complaints` and `ai_complaint_history` tables to the existing `executescript` statement, leaving `ai_reports` and `ai_notifications` intact.
3. **`frontend/src/services/aiLayerService.ts`**:
   - *Risk*: Contains report generation methods (`createReport`, `downloadReport`, `emailReport`).
   - *Resolution*: Re-add `ComplaintRecord` and complaint methods without altering report methods.
4. **`frontend/src/layouts/Sidebar.tsx`**:
   - *Risk*: Nav item ordering and persona handling.
   - *Resolution*: Reinsert the `/app/complaints` link between `/app/assistant` and `/app/reports`.

---

## 8. Items Requiring Confirmation From the Target Branch

> [!NOTE]
> The following items require confirmation from the engineers maintaining the other branch:
> 1. **External Integration**: Verify whether the other branch integrates with real CRM/utility ticketing systems (e.g., Salesforce, SAP, Zendesk) or retains the local SQLite demo queue.
> 2. **AI Classification Agent**: Verify whether the incoming branch replaces the rule-based `_classify` regex matcher with an LLM/agent-based classification pipeline.
> 3. **Database Migrations**: Check if the other branch migrated `ai_complaints` to PostgreSQL/SQLAlchemy or maintains the SQLite `AIApplicationStore`.

