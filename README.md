# Emergency Helper Web Application

A modern, mobile-friendly web app to help users in emergencies. Built with FastAPI (Python backend) and a responsive, Bootstrap-inspired frontend.

## Features
- **Report an attack** (with subtypes: bullets, drones, artillery)
- **Report injury/casualty** (with subtypes: life-threatening, death, minor)
- **Find medical services**
- **Call a helpline**
- **No login required** for basic use; phone number authentication (mocked, regex) for submissions
- **User details** (name, phone, location) and request details are stored in a normalized SQLite database
- **Sensitive fields** (name) are encrypted with Fernet
- **Rate limiting**: 3 requests per hour per user (except medical)
- **Admin dashboard** with HTTP Basic Auth, IP whitelisting, and rate limiting
- **Admin dashboard** includes map and table views, filterable by type, subtype, and date
- **All secrets and API keys** are stored in `.env`

## Quick Start

1. **Install dependencies** (in your virtual environment):
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up your `.env` file** (see below for example)

3. **(Optional) Populate the database with 10,000 rows of dummy data:**
   ```bash
   python insert_dummy_data.py
   ```

4. **Start the server:**
   ```bash
   uvicorn main:app --reload
   ```

5. **Open your browser:**
   Go to [http://localhost:8000](http://localhost:8000)

## Project Structure
- `main.py` — FastAPI backend (all endpoints, models, logic)
- `templates/index.html` — Main user interface (SPA-like, mobile-first)
- `templates/admin.html` — Admin dashboard (map, table, filters)
- `static/` — Static assets (JS, CSS, icons)
- `insert_dummy_data.py` — Script to generate 10,000+ rows of realistic test data
- `migrate_v2.py` — Migration script for normalized DB structure
- `requirements.txt` — Python dependencies
- `../data/emergency.db` — SQLite database (auto-created)

## Admin Dashboard
- **URL:** `/supersecretadmin`
- **Auth:** HTTP Basic Auth (credentials from `.env`)
- **IP Whitelist:** Only allowed IPs (see `.env`)
- **Rate Limiting:** 5 requests per 60 seconds per IP (configurable)
- **Views:**
  - **Map View:** See all requests on a map, filter by type, subtype, and date
  - **Requests Table:** Tabular view, filterable by type, subtype, and date
  - **Users Table:** List of all users
- **Filters:** All type/subtype filters are dynamic, based on DB contents

## Database Structure
- **Users**: `user_id`, `phone`, `name`, `surname`
- **Request Types**: `type_code`, `type_name`
- **Request Subtypes**: `subtype_code`, `subtype_name`, `type_code`
- **Emergency Requests**: `request_id`, `user_id`, `name` (encrypted), `latitude`, `longitude`, `type_code`, `subtype_code`, `details`, `timestamp`

## Dummy Data Generation
- Run `python insert_dummy_data.py` to generate 10,000+ realistic requests, users, types, and subtypes.
- Data is randomized for location, type, subtype, details, and timestamp (last 90 days).
- Useful for demo, testing, and performance evaluation.

## Security Notes
- **Admin credentials** are loaded from `.env`. Never commit your real `.env` to version control.
- **HTTPS**: Enforce HTTPS in production (see code comment for enabling middleware; use a reverse proxy like Nginx for SSL termination).
- **Database location**: The SQLite database is stored outside the web root in a `data/` directory. Set `DATA_DIR` in your `.env` if you want to customize the location.
- **Encryption**: The `name` field is encrypted in the database using Fernet symmetric encryption. Set `FERNET_KEY` in your `.env` for a persistent key.
- **Rate limiting**: The admin route is rate-limited (default: 5 requests per 60 seconds per IP). Configure with `ADMIN_RATE_LIMIT` and `ADMIN_RATE_PERIOD` in `.env`.
- **IP Whitelist**: Only IPs in `ADMIN_ALLOWED_IPS` (comma-separated) can access the admin route. Default is `127.0.0.1`.
- **Dependency audit**: Run `pip-audit` to check for vulnerabilities:
  ```bash
  pip install pip-audit
  pip-audit
  ```

## .env Example
```
ADMIN_USERNAME=youradmin
ADMIN_PASSWORD=yourstrongpassword
FERNET_KEY=your_fernet_key
ADMIN_ALLOWED_IPS=127.0.0.1,192.168.1.100
DATA_DIR=../data
ADMIN_RATE_LIMIT=5
ADMIN_RATE_PERIOD=60
MAPTILER_API_KEY=your_maptiler_key
SESSION_SECRET_KEY=your_session_secret
```

## Developer Notes
- **Database Browsing:** Use DB Browser for SQLite, VS Code SQLite extension, or online tools (sqliteviewer.app, sqliteonline.com) to inspect the DB.
- **Migrations:** Use `migrate_v2.py` to migrate old DBs to the new normalized structure.
- **Testing:** The dummy data script is ideal for stress-testing and UI/UX validation.

--- 