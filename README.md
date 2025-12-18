# Reazy Python API (reazy-papi)

This is the Python-based backend for the Reazy application, migrated from the legacy Node.js API. It is built using FastAPI and SQLModel, providing a high-performance, async-ready REST API.

## Tech Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/)
- **Database ORM**: [SQLModel](https://sqlmodel.tiangolo.com/) (SQLAlchemy + Pydantic)
- **Database Driver**: `asyncpg` (PostgreSQL)
- **Migrations**: [Alembic](https://alembic.sqlalchemy.org/)
- **Authentication**: JWT (JSON Web Tokens) with `python-multipart` and `passlib[bcrypt]`
- **Server**: Uvicorn

## Features

- **Authentication**: Secure Login, Signup, Logout (HttpOnly Cookies), Password Updates.
- **User Management**: Profile updates with support for detailed financial parameters.
- **Retirement Planning**:
  - Full CRUD for retirement plans.
  - Generates comprehensive financial projections (Snapshots) and Milestones.
  - Supports multiple scenarios (Primary vs. alternative plans).
- **Dashboard**: Aggregated financial metrics for user homepage.
- **Multi-Step Form**: Tracks user onboarding progress.

## Prerequisites

- Python 3.9+
- PostgreSQL database
- Git

## Installation & Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd reazy-papi
   ```

2. **Create a Virtual Environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**
   Create a `.env` file in the root directory:
   ```env
   PORT=8000
   DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/reazy_db
   SECRET_KEY=your_super_secret_key_change_this_in_production
   ACCESS_TOKEN_EXPIRE_MINUTES=10080
   CLIENT_URL=http://localhost:3000
   BACKEND_CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
   ```

5. **Database Migration**
   Apply the database schema:
   ```bash
   alembic upgrade head
   ```

## Running the Server

Start the development server with live reload:

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.
Automatic API documentation (Swagger UI) is available at `http://127.0.0.1:8000/docs`.

## Project Structure

```
reazy-papi/
├── alembic/              # Database migration scripts
├── app/
│   ├── api/              # API Route handlers
│   │   ├── auth.py
│   │   ├── retirement.py
│   │   ├── users.py
│   │   └── ...
│   ├── core/             # Config and Security settings
│   ├── models/           # SQLModel database models
│   ├── services/         # Business logic (e.g., calculations)
│   ├── database.py       # Database connection setup
│   └── main.py           # Application entry point
├── .env                  # Environment variables (gitignored)
├── .gitignore
├── alembic.ini           # Alembic config
└── requirements.txt      # Python dependencies
```

## Migration Status

See `migration_status.md` for a detailed breakdown of endpoints migrated from the legacy Node.js system.
