# Emergency Helper Web Application

A simple web application to help users in emergencies. Users can:
- Report a casualty
- Request evacuation
- Find medical services near them

No login required. User's name and GPS location are stored for tracking.

## How to Run

1. **Install dependencies** (in your virtual environment):
   ```bash
   pip install fastapi uvicorn jinja2 sqlalchemy aiosqlite
   ```

2. **Start the server:**
   ```bash
   uvicorn main:app --reload
   ```

3. **Open your browser:**
   Go to [http://localhost:8000](http://localhost:8000)

## Project Structure
- `main.py` - FastAPI backend
- `templates/index.html` - Frontend HTML
- `emergency.db` - SQLite database (auto-created)

## Notes
- Location is auto-filled using browser geolocation.
- All features are available without login.

## Security Notes
- **Admin credentials** are loaded from a `.env` file (see `.env.example`). Never commit your real `.env` to version control.
- The admin view is now at `/supersecretadmin` and is protected by HTTP Basic Auth.
- All failed admin logins are logged.
- The database file is created with restricted permissions (0600).
- Always use HTTPS in production to protect credentials and data in transit.
- Keep your dependencies up to date and review them for vulnerabilities.

## Advanced Security Features
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
```

--- 