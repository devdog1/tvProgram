# WCGtv Metadata Platform

A modern Django-based web application replacing the legacy PHP metadata tool (`index.php` and `programs.php`). The platform allows authenticated users to submit and manage television broadcast programs, complete with form format validations, user permission controls, preloaded default options, and dynamic dropdown administration (Categories, Communities, Source Codes, and Share With options) using a MySQL/MariaDB database.

---

## Features

1. **Authentication & Authorization**
   - **Program Creators (`add_program`)**: Can submit new programs and view program listings.
   - **Program Editors (`change_program`, `delete_program`)**: Can edit, update, and delete programs, as well as create, edit, enable, or disable system-defined dropdown options (Category, Community, Source Code, Share With).
   - Standard Django Admin interface at `/admin/`.

2. **Program Management & Format Validation**
   - Conforms strictly to validation rules from the original PHP code:
     - **Title**: Required non-empty string.
     - **Date Recorded**: Required format `YYYY-MM-DD` (equipped with jQuery UI datepicker).
     - **Expiry Date**: Optional format `YYYY-MM-DD` (equipped with jQuery UI datepicker).
     - **Producer**: Required non-empty string.
     - **Length**: Required format `HH:MM:SS` (regex checked).
     - **Category**: Dynamic single-select dropdown of active categories.
     - **Community**: Dynamic multi-select of active communities (serialized to comma-delimited strings to match PHP database schema).
     - **Source Code**: Dynamic single-select dropdown of active source codes.
     - **Share With**: Dynamic multi-select of active share regions.
     - **Filename**: Required format `^[^\\/:*?"<>|]+\.[a-zA-Z0-9]{1,5}$` (valid filename with extension).
     - **Comments**: Optional string up to 255 characters.
   - Dual-layer validation: Client-side JavaScript validation (matching legacy `validateForm`) and server-side Django Form / Model validation.
   - Optional legacy mode: Checkbox allowing users to download the formatted `.txt` metadata file attachment upon submission.

3. **Dynamic System Options Management**
   - Dashboard accessible at `/options/` for users with edit permissions.
   - Ability to **Create**, **Edit**, **Enable**, and **Disable** choices for:
     - Categories (e.g., Arts/Music, Sports, Religion, etc.)
     - Communities (e.g., Brandon, Birtle, Dauphin, etc.)
     - Source Codes (e.g., Single Camera/No Editing, Studio Production, etc.)
     - Share With options (e.g., All, Brandon, North, South)
   - Only enabled options are displayed to users in the program submission and edit dropdowns (while preserving historical values on existing programs).

4. **Program Directory & DataTables**
   - Responsive list view styled with Bootstrap 5 and DataTables (sorting, instant search, pagination, descending order by ID) reproducing `programs.php`.

5. **Preloaded System Defaults**
   - Automatically preloads all default categories, communities, source codes, and share options into the database via Django migrations and a management command (`python manage.py preload_defaults`).

---

## Database Configuration

The application is configured to use MySQL / MariaDB using the `mysqlclient` backend:

- **Database Name**: `wcgtv` (default, configurable via `DB_NAME` env var)
- **User**: `wcgtv` (default, configurable via `DB_USER` env var)
- **Password**: `hasfjafdhiu790shiod` (default, configurable via `DB_PASSWORD` env var)
- **Host**: `127.0.0.1` (configurable via `DB_HOST` env var)
- **Port**: `3306` (configurable via `DB_PORT` env var)

### Initial MySQL Setup:
```sql
CREATE DATABASE IF NOT EXISTS wcgtv CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'wcgtv'@'localhost' IDENTIFIED BY 'hasfjafdhiu790shiod';
GRANT ALL PRIVILEGES ON wcgtv.* TO 'wcgtv'@'localhost';
FLUSH PRIVILEGES;
```

---

## Installation & Setup

1. **Clone or Navigate to the Repository**:
   ```bash
   cd /path/to/wcgtv
   ```

2. **Install Python Dependencies**:
   ```bash
   pip install django mysqlclient
   ```

3. **Apply Database Migrations**:
   This creates the required database tables and automatically preloads the system defaults from the PHP file:
   ```bash
   python manage.py migrate
   ```

4. **Initialize Permission Groups**:
   Run the custom management command to create the standard `Program Creators` and `Program Editors` groups:
   ```bash
   python manage.py setup_groups
   ```

5. **Create an Admin / Editor User**:
   ```bash
   python manage.py createsuperuser
   ```
   Or via the Django shell:
   ```python
   from django.contrib.auth.models import User, Group
   user = User.objects.create_user("editor_user", password="your_password")
   group = Group.objects.get(name="Program Editors")
   user.groups.add(group)
   ```

6. **Start the Development Server**:
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```

---

## Running Automated Tests

Run the full Django test suite covering form validations, permission constraints, attachment downloads, and option toggling:

```bash
python manage.py test
```

---

## URL Endpoints

| URL Path | View Description | Required Permission |
| :--- | :--- | :--- |
| `/login/` | User Authentication / Sign In | Public |
| `/logout/` | User Sign Out | Authenticated |
| `/` | Programs Table (DataTables list) | Authenticated |
| `/programs/new/` | Submit New Program Form | Program Creators / Editors |
| `/programs/<id>/edit/` | Edit Existing Program | Program Editors |
| `/programs/<id>/delete/` | Delete Program | Program Editors |
| `/options/` | System Defined Options Dashboard | Program Editors |
| `/options/<type>/new/` | Add New Option | Program Editors |
| `/options/<type>/<id>/edit/` | Edit Option Name/Display | Program Editors |
| `/options/<type>/<id>/toggle/` | Enable / Disable Option | Program Editors |
| `/admin/` | Django Admin Console | Staff / Superuser |
