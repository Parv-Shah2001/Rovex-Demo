# Rovex Hospital Stretcher Robots Backend Platform

Welcome to the **Rovex Fleet Orchestration Backend**. This prototype is designed as a modular, scalable, production-ready backend system to manage hospital stretcher robots. Built using **Python and FastAPI**, it simulates concurrent robot data streams, provides Role-Based Access Control (RBAC) security, and performs macro-route optimizations.

---

## 🚀 Tech Stack & Tradeoffs

1. **FastAPI & Python 3.11**: Leverages high-performance asynchronous event-loops to serve concurrent REST API requests.
2. **Pydantic v2**: Handles and strictly validates incoming concurrent synthetic telemetry payloads sent by robots.
3. **Dual Mock Storage Engine** (No external database installation required):
   - **Relational SQL Database (SQLite in-memory)**: Emulates a transactional PostgreSQL OLTP system using genuine, production-standard **SQLAlchemy ORM** configurations for users, roles, and scheduled task records.
   - **Document NoSQL Database (Custom PyMongo Mock)**: A thread-safe, in-memory collection-based document database emulating MongoDB/PyMongo. Stores and queries flexible unstructured fleet registries, robot profiles, telemetry streams, and system alerts.
4. **Lightweight HMAC-SHA256 Token Sessions**: Cryptographically signed access credentials with zero external OAuth library bloat, ensuring maximum system independence and speed.
5. **Tailwind CSS & Canvas JS Frontend**: Serves interactive, responsive administrative panels and an AI chat workspace with zero node/npm dependency overhead. The Core Platform shell also uses a small amount of custom CSS to guarantee a sticky, collapsible Gemini-style sidebar and a fully scrollable main workspace without introducing a frontend build step.

---

## 📐 System Architecture: Modular Monolithic

The directory is structured to represent a **Modular Monolith**, ensuring that each domain is self-contained with its own schemas, database tables, and endpoints. Decoupling and breaking individual services out into separate standalone microservices in the future is a zero-rewrite operation.

```text
app/
├── core/
│   ├── config.py           # Configuration variables, seed user base & layout graph nodes
│   ├── database.py         # Mock SQLAlchemy SQLite engine, PyMongo clients & DB seed engines
│   └── auth.py             # HMAC crypt token sessions & RBAC Dependency Injection
├── services/
│   ├── user/               # User Management Service (SQL, register, login, RBAC shifts)
│   ├── robot/              # Robot Management Service (NoSQL, fleet-aware robot registry, A* routing)
│   ├── notification/       # Notification Service (Alerts, category priority, physical logs)
│   ├── organization/       # Organization domain (controller trees, fleet views, org metadata/history)
│   ├── admin/              # Admin Platform (dashboard stats, drill-down metrics, advanced sandbox)
│   └── core_platform/      # Core Platform (router + service layer for scheduling and mission orchestration)
├── static/
│   └── js/                 # Shared/page-specific browser bundles served via FastAPI StaticFiles
├── templates/              # HTML frontend templates served directly from FastAPI file reads
│   ├── index.html               # Dynamic login panel & RBAC account credentials card
│   ├── admin.html               # Main admin dashboard, metrics, fleet registry, onboarding actions
│   ├── admin_organizations.html # Dedicated organization management page with trees/history/fleets
│   ├── admin_sandbox.html       # Dedicated advanced SQL/NoSQL sandbox explorer
│   └── core_platform.html       # Gemini-style chat portal and live 2D canvas navigation map
├── main.py                 # Core application entrypoint and module mounters
tests/
└── test_platform.py        # Complete unit test suite (Seeded auth, A*, NoSQL & SQL operations)
```

---

## 🌟 Key Features & Demonstrations

### 🧑‍💼 1. Hierarchical User Management & RBAC
Five pre-configured seed users demonstrate both role hierarchy and organization scoping:
- **Rovex Admin (James Whitfield)**: Platform-wide rights across every hospital organization, including the admin dashboard, robot sanction controls, sandbox query tools, and full cross-organization user provisioning.
- **Supervisor (Dr. Sarah Mitchell / St. Jude Hospital)**: Hospital manager rights inside St. Jude, including fleet oversight, staff visibility, and scoped account provisioning for that institution through the Core Platform.
- **Sub-Supervisor (Nurse Thomas Kelly / St. Jude Hospital)**: Dispatch rights for scheduling missions, reviewing live status, and adjusting corridor priorities.
- **Employee (Orderly John Doe / St. Jude Hospital)**: Viewer-only rights plus service-request filing.
- **Supervisor (Dr. Alan Grant / City General Hospital)**: A second hospital supervisor used to validate organization scoping and admin cross-organization visibility.

### 🤖 2. Fleet-Aware Robot Telemetry Ingestion (Pydantic Validation)
Supports high-frequency telemetry packets, validating physical speed and steering parameters, battery mah capacities, 2D coordinates, safety proximity obstacles, and camera/lidar diagnostics.
Each robot is explicitly attached to an organization-scoped fleet, and fleet summaries are recomputed from robot state so the platform reflects true hospital fleet operations rather than treating each robot as its own fleet.

### 🗺️ 3. A* Macro-Routing & Orchestration
Implements the **A\* Search Algorithm** on a 2D graph representing hospital zones (Reception, ICU, Pharmacy, Wards, etc.).
- **Euclidean Heuristic**: Computes straight-line distances.
- **Dynamic Traffic Priority**: Supervisors can increase the cost weight of specific corridors (e.g. to bypass busy hallways during peak periods), dynamically forcing robots onto alternative optimal routes.
- **Diagnostics Output**: Traces A\* computations step-by-step (g-score, h-score, f-score) to display "how the algorithm works" transparently.

### 📢 4. Multi-Priority Notifications Service
Categorizes all alerts into **CRITICAL, GENERAL, ANALYTICS, SUGGESTIONS, and MARKETING** with strict numerical priorities. 
- Alerts are appended to a persistent local log file `data_pool_notifications.log` on disk to simulate a unified data pool (ready for future ELT ingestion).
- Alerts are also written to a MongoDB-like index enabling instant rendering on frontend cards.
- Notification records now carry organization scope so hospital users only see alerts from their own institution, while Rovex admins retain global visibility.

### 🚚 5. Fleet Registry & Robot Governance
Hospital organizations operate fleets, and each fleet is the real grouping that owns multiple robots.
- **Fleet Registry**: The admin dashboard surfaces organization-scoped fleet entries, assigned robot counts, dispatchable robot counts, and sanctioned vs. unsanctioned totals.
- **Robot Governance**: Individual robots still carry live telemetry, sanction state, and maintenance history, but they are now shown as members of fleets instead of being treated as standalone fleets.
- **Admin Controls**: Rovex admins can onboard new robots, remove inactive robots, and sanction / un-sanction robots from the admin dashboard while seeing the resulting effect on fleet readiness.

### 🏥 6. Organization Control Center
Rovex admins can inspect dedicated organization pages that expose:
- full controller trees grouped into supervisor / sub-supervisor / employee branches,
- organization metadata such as location, service tier, controller device, contract owner, and deployment notes,
- Rovex deployment history timelines,
- fleet-wise robot status panels including recent alert snippets and telemetry timestamps.
Supervisors can also open a lighter organization-structure popup from the Core Platform for their own hospital.

### 🛠️ 7. Admin Sandboxed Database Query Workspace
The admin portal now includes a dedicated advanced sandbox page rather than embedding the whole explorer in the dashboard.
- **SQL Console**: Supports read-oriented inspection commands such as `SHOW TABLES`, `DESCRIBE users`, `PRAGMA table_info(...)`, `SELECT ...`, and read-only CTEs.
- **NoSQL Console**: Supports `db.listCollections()`, `find`, `find_one`, `distinct`, `aggregate`, and `countDocuments` commands.
- **Blocked Commands**: destructive or schema-mutating actions like DELETE and ALTER remain explicitly disallowed.

### 💬 8. Gemini-Style Chat Assistant & Canvas Visualizer
The face-to-face employee workspace is styled with a sleek **Gemini-like AI Chat Input**. 
- Users can type commands in natural language: e.g. **"schedule from Reception to ICU"** or **"list active robots"**.
- The frontend parses commands programmatically to trigger underlying REST APIs.
- A live **2D HTML5 Canvas** renders the hospital layout, highlighting optimal paths and showing robot movements coordinate-by-coordinate in real-time.
- On desktop screens, the Core Platform behaves like a sticky app shell: a collapsible left operations rail stays pinned while the chat/map workspace scrolls independently.
- Supervisors can open a non-prominent organization-structure modal to review controller hierarchy and fleet readiness for their hospital.

---

## 🛠️ Installation & Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt --user --break-system-packages
   ```

2. **Run the Unit Test Suite** (Verifies and validates all sub-modules):
   ```bash
   python3 -m unittest -v
   ```
   *Output showing `OK` confirms that cryptographic, relational, document, routing, organization scoping, static frontend bundle wiring, file-based template loading, and Core Platform layout checks are all passing.*

3. **Start the FastAPI Application Server**:
   ```bash
   python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **Navigate to the Platform**:
   Open your browser and navigate to: `http://localhost:8000/`

5. **When validating frontend HTML/layout changes locally**:
   - restart the active `uvicorn` process after pulling the newest branch updates,
   - then do a hard refresh in the browser (`Ctrl+Shift+R` / `Cmd+Shift+R`).

   This project serves HTML templates directly from FastAPI, so restarting the local process is the safest way to guarantee the browser is testing the newest frontend markup during iteration.

---

## 🔍 Code Reliability & Best Practices
- **DRY & YAGNI**: Modular design keeps components focused on single domains with no unnecessary abstractions.
- **Fully Documented**: Every module, route, and function begins with an extensive descriptive block explaining its role and implementation specs in detail.
- **Error Boundaries**: High defensive programming practices with validation checks on indices, empty values, and non-existing paths.
