# ROTC Excusal Website

Simple Flask app to submit cadet excusal requests, manage roster, and track attendance.

Setup (macOS, zsh):

1. Create a virtual environment and activate it:

```bash
python3 -m venv venv
source venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the app:

```bash
python app.py
```

The app will be available at http://127.0.0.1:5000

Notes:
- Default staff password is read from the `STAFF_PASSWORD` environment variable or falls back to `noelleketo`.
- Use the staff interface to approve/deny excusals and manage the roster.
