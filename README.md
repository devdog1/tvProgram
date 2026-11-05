# WCGtv Metadata & Media Management Platform

A Django-based media management platform built to modernize the WCGtv metadata tool. The application features a NetBox-inspired interface, program CRUD with ownership permissions, episodic TV series management, custom metadata fields, change log auditing, file attachments, and sign-off verification workflows. It uses SQLite (`db.sqlite3`) as the default database engine.

---

## Features

- **NetBox-Inspired UI**: Sidebar navigation, dashboard widgets, and change log tables styled after the NetBox administrative interface.
- **Program Metadata Management**: Create, view, edit, and delete programs with field validations (`HH:MM:SS` duration, `YYYY-MM-DD` dates, filename extensions, comments length limits).
- **Episodic Linkage**: Organize programs under parent TV Series, Mini-Series, or Multi-Part titles with season, episode, and part numbering.
- **Creator Ownership & Permissions**: Users can edit programs they created but cannot delete them. Only privileged editors/administrators may delete programs.
- **Full Versioning & Change Log**: Comprehensive audit trail recording user, action (Created, Updated, Deleted, Signed Off, Rejected), object type, and delta details.
- **File Attachments**: Upload supplementary documents (broadcast cue sheets, release forms, cue notes) to programs.
- **Custom Metadata Fields**: Administrators can create custom program attributes (Text, Textarea, Integer, Boolean, Date, URL) dynamically rendered on forms.
- **Sign-off / Review Workflow**: Editorial validation workflow (`Draft`, `Pending Review`, `Signed Off`, `Rejected`) with reviewer notes.
- **Preloaded Metadata Options**: Pre-seeded with categories, communities, source codes, and share regions from original PHP specifications, with toggle and management capabilities.

---

## Python Virtual Environment Setup

### 1. Prerequisites
- Python 3.10+ (Python 3.12 recommended)
- `pip` and `python3-venv`

### 2. Creating and Activating the Virtual Environment

#### On Linux / macOS:
```bash
# Create the virtual environment in the project directory
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate
```

#### On Windows (PowerShell / Command Prompt):
```powershell
# Create the virtual environment
python -m venv venv

# Activate (PowerShell)
.\venv\Scripts\Activate.ps1

# Or activate (cmd.exe)
.\venv\Scripts\activate.bat
```

### 3. Installing Dependencies

With the virtual environment activated:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Running in Development & Testing

### 1. Database Setup & Migrations
SQLite is configured by default (`db.sqlite3`):
```bash
python manage.py migrate
```

### 2. Preloading Defaults & Groups
Populate the system metadata options and user groups:
```bash
python manage.py preload_defaults
python manage.py setup_groups
```

### 3. Creating an Admin User
```bash
python manage.py createsuperuser
```

### 4. Running the Test Suite
Execute the comprehensive automated test suite inside the virtual environment:
```bash
python manage.py test
```

### 5. Running the Development Server
```bash
python manage.py runserver 0.0.0.0:8000
```
Visit `http://127.0.0.1:8000/` in your browser.

---

## Running in Production

### 1. Production Settings Checklist
- Set `DEBUG = False` in `wcgtv_project/settings.py` or use environment variables.
- Set a strong secret key via `SECRET_KEY`.
- Configure `ALLOWED_HOSTS` with your domain/IP:
  ```python
  ALLOWED_HOSTS = ["metadata.wcgtv.ca", "127.0.0.1"]
  ```

### 2. Static and Media Files
Collect static files for production web server delivery (Nginx/Apache):
```bash
python manage.py collectstatic --noinput
```
Ensure directory permissions for uploads:
```bash
mkdir -p media/program_attachments
chmod -R 755 media
```

### 3. Production WSGI Server (Gunicorn)
Install Gunicorn inside the virtual environment:
```bash
pip install gunicorn
```

Run Gunicorn using the virtual environment's executable:
```bash
/path/to/project/venv/bin/gunicorn wcgtv_project.wsgi:application \
    --bind 127.0.0.1:8000 \
    --workers 4 \
    --timeout 60 \
    --access-logfile /var/log/wcgtv/access.log \
    --error-logfile /var/log/wcgtv/error.log
```

### 4. Systemd Service Example (`/etc/systemd/system/wcgtv.service`)
```ini
[Unit]
Description=WCGtv Metadata Gunicorn Daemon
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/wcgtv
ExecStart=/var/www/wcgtv/venv/bin/gunicorn \
          --workers 3 \
          --bind unix:/run/wcgtv.sock \
          wcgtv_project.wsgi:application

Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### 5. Nginx Reverse Proxy Configuration Example
```nginx
server {
    listen 80;
    server_name metadata.wcgtv.ca;

    location = /favicon.ico { access_log off; log_not_found off; }

    location /static/ {
        alias /var/www/wcgtv/staticfiles/;
    }

    location /media/ {
        alias /var/www/wcgtv/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## User Roles & Permissions Summary

- **Creator Users (`Program Creators`)**:
  - Add new programs and TV series.
  - Edit programs they have created.
  - Cannot delete programs.
  - Submit programs for editorial sign-off review.
  - Attach files to their programs.

- **Editor Users (`Program Editors`)**:
  - Full CRUD permissions on all programs and series.
  - Sign off, approve, or reject program and series submissions.
  - Manage system metadata options (categories, communities, source codes, share options).
  - Manage custom metadata attributes.

- **Superusers / Administrators**:
  - Full access including Django Admin site and custom field definitions.
