# VistaLock — Vehicle Access Management System

VistaLock is a vehicle access management system designed to help manage vehicle entry and exit, verify number plates against a registered vehicle database, handle visitor passes, and monitor access-related alerts across multiple sites.

The project combines computer vision, backend APIs, database management, and a web dashboard to support vehicle verification using recorded video or a webcam with a simulated gate environment.

## Key Features

- **License Plate Recognition:** Detect vehicle number plates and extract plate text using computer vision and OCR.
- **Vehicle Registry:** Maintain registered vehicle information for access verification.
- **Entry and Exit Management:** Record vehicle movements and track vehicles currently inside a site.
- **Visitor Passes:** Support visitor access management through the backend.
- **Alert Management:** Apply rule-based checks to flag suspicious or unusual access events.
- **Multi-Site Support:** Organize access records and management data by site.
- **Web Dashboard:** View vehicle logs, current occupancy, and alerts.
- **Local Development:** Run the application components on a laptop using a simulated gate and recorded videos or a webcam.

## Technology Stack

| Component | Technology |
|---|---|
| Backend API | Python, FastAPI |
| Database | PostgreSQL |
| Computer Vision | YOLO-based plate detection, OpenCV, EasyOCR |
| Dashboard | React |
| Database Environment | Docker Compose |
| Testing | Pytest |

## Project Structure

```text
VistaLock/
├── backend/       # FastAPI backend and access management logic
├── cv/            # Plate detection, OCR, and plate processing
├── dashboard/     # React dashboard
├── db/            # Database schema, migrations, and seed data
├── data/          # Local test videos and generated plate crops
├── .gitignore
├── docker-compose.yml
└── README.md
```

## Getting Started

### Prerequisites

Install the following tools before running the project:

- Python 3.12 or a compatible version
- Docker Desktop with Docker Compose
- Git
- Node.js and npm, if running the React dashboard

### 1. Clone the Repository

```bash
git clone https://github.com/Mohammedazam007/VistaLock.git
cd VistaLock
```

### 2. Configure Environment Variables

Create your local `.env` file using the project's example file, if provided:

```bash
cp .env.example .env
```

On Windows PowerShell, use:

```powershell
Copy-Item .env.example .env
```

Configure the required database credentials and application settings according to `docker-compose.yml` and the backend configuration. Never commit your real `.env` file or credentials.

### 3. Start the Database

```bash
docker compose up -d
docker compose ps
```

Confirm that the PostgreSQL container is running and healthy before starting the backend.

The database schema and seed data may be initialized automatically when the database volume is created for the first time. Existing volumes are not necessarily updated automatically when the schema changes. Apply any required migrations before using an existing database.

### 4. Set Up the Computer Vision Pipeline

Open a terminal in the project root and run:

```powershell
cd cv
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest -q
```

To process a test video, place it in the configured test-video directory and run:

```powershell
python read_video.py ..\data\videos\entry.mp4 --verbose
```

The video path is an example; use a video that exists on your machine.

The first run may download OCR model files. Processing speed depends on the hardware, video resolution, and detection settings.

### 5. Run the Backend and Dashboard

The backend and dashboard have their own dependencies and startup procedures. Follow the configuration and instructions in their respective directories.

- `backend/` — API and vehicle access management.
- `dashboard/` — Web interface for access logs, current occupancy, and alerts.

Ensure the database is available and the required environment variables are configured before starting the application.

## Testing

Run the computer vision tests from the `cv/` directory:

```bash
python -m pytest -q
```

These tests cover plate-processing logic and confidence-weighted voting.

## Project Goals

VistaLock explores how computer vision and backend systems can work together to improve vehicle access verification and monitoring.

The project focuses on:

- Reliable number-plate processing.
- Database-backed vehicle verification.
- Structured entry and exit records.
- Rule-based access anomaly detection.
- Separation of the computer vision, backend, database, and dashboard components.

## Future Improvements

Potential areas for further development include improving OCR accuracy under different lighting conditions, strengthening vehicle-to-plate mismatch detection, expanding automated testing, and improving dashboard usability.

## Repository

GitHub: https://github.com/Mohammedazam007/VistaLock
