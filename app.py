from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response, send_from_directory
import logging
from logging.handlers import RotatingFileHandler
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import date
import csv
from functools import wraps

# database stuff
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SECRET_KEY'] = 'supersecretkey'  # required for flash messages + sessions
db = SQLAlchemy(app)

STAFF_PASSWORD = os.environ.get("STAFF_PASSWORD", "noelleketo")

def staff_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("staff_logged_in"):
            flash("Staff login required to access this page.")
            return redirect(url_for("staff_login"))
        return f(*args, **kwargs)
    return decorated_function

class Cadet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    rank = db.Column(db.String(50))
    status = db.Column(db.String(20), default="present") 

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    date = db.Column(db.String(20), nullable=False)


class AttendanceOverride(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cadet_id = db.Column(db.Integer, db.ForeignKey('cadet.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False)  # present, pending, excused, unknown


class Excusal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20))
    cpt = db.Column(db.String(50))
    company = db.Column(db.String(100))
    event = db.Column(db.String(200))
    excused_from = db.Column(db.String(200))
    reason = db.Column(db.String(300))
    makeup_plan = db.Column(db.String(300))
    poc = db.Column(db.String(100))
    name = db.Column(db.String(100))
    position = db.Column(db.String(100))
    status = db.Column(db.String(20), default="pending")
    phone = db.Column(db.String(50))
    email = db.Column(db.String(200))


# Landing page
@app.route("/")
def home():
    return render_template("home.html")


# helper: normalize name for case-insensitive matching
def normalize_name(n: str) -> str:
    return (n or "").strip().lower()


@app.context_processor
def inject_now():
    # make today's date available to templates in YYYY-MM-DD
    return {"today": date.today().isoformat()}

# Staff login
@app.route("/staff-login", methods=["GET", "POST"])
def staff_login():
    if request.method == "POST":
        try:
            password = request.form["password"]
            if password == STAFF_PASSWORD:
                session["staff_logged_in"] = True
                return redirect(url_for("staff_dashboard"))
            else:
                flash("Incorrect password, try again.")
                return redirect(url_for("staff_login"))
        except Exception as e:
            app.logger.error(f"Staff login error: {e}")
            flash("Login error occurred. Please try again.")
            return redirect(url_for("staff_login"))
    return render_template("staff_login.html")

# Logout
@app.route("/logout")
def logout():
    session.pop("staff_logged_in", None)
    flash("Logged out successfully.")
    return redirect(url_for("home"))

# Clear session (debugging)
@app.route("/clear-session")
def clear_session():
    session.clear()
    return redirect(url_for("home"))

# (Roster management route defined later)

# Excusal form
@app.route("/excusal", methods=["GET", "POST"])
def excusal():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        # attempt to match name to roster case-insensitively
        cadet = None
        if name:
            norm = normalize_name(name)
            for c in Cadet.query.all():
                if normalize_name(c.name) == norm:
                    cadet = c
                    break

        if not cadet:
            flash("Name not found on roster (check capitalization/spelling). If this is correct, please contact staff to add the cadet.")
            return redirect(url_for("excusal"))

        new_excusal = Excusal(
            date=request.form.get("date", date.today().isoformat()),
            cpt=request.form.get("cpt", ""),
            company=request.form.get("company", ""),
            event=request.form.get("excused_from", ""),  # Use excused_from as the event
            excused_from=request.form.get("excused_from", ""),
            reason=request.form.get("reason", ""),
            makeup_plan=request.form.get("makeup_plan", ""),
            poc=request.form.get("poc", ""),
            phone="",  # No longer collected
            email="",  # No longer collected
            name=name,
            position=request.form.get("position", ""),
            status="pending"
        )
        db.session.add(new_excusal)
        # mark cadet pending
        cadet.status = "pending"
        db.session.commit()
        flash("Excusal submitted and is pending staff approval.")
        return redirect(url_for("pending_excusals"))

    # provide upcoming events for dropdowns
    evs = Event.query.order_by(Event.date).all()
    today_s = date.today().isoformat()
    upcoming = [e for e in evs if e.date >= today_s]
    return render_template("excusal.html", events=upcoming)


# Pending excusals view (for users to see their submitted excusals)
@app.route("/pending_excusals")
def pending_excusals():
    excusals = Excusal.query.filter_by(status="pending").all()
    return render_template("pending_excusals.html", excusals=excusals)


# Edit excusal - redirect back to excusal form with pre-filled data
@app.route("/edit_excusal/<int:excusal_id>", methods=["GET", "POST"])
def edit_excusal(excusal_id):
    excusal = Excusal.query.get_or_404(excusal_id)
    
    if request.method == "GET":
        # Pre-fill the form with existing data
        evs = Event.query.order_by(Event.date).all()
        today_s = date.today().isoformat()
        upcoming = [e for e in evs if e.date >= today_s]
        return render_template("excusal.html", events=upcoming, excusal=excusal)
    
    # Handle form submission for editing
    if request.method == "POST":
        # Update the existing excusal
        excusal.date = request.form.get("date", excusal.date)
        excusal.cpt = request.form.get("cpt", excusal.cpt)
        excusal.company = request.form.get("company", excusal.company)
        excusal.excused_from = request.form.get("excused_from", excusal.excused_from)
        excusal.reason = request.form.get("reason", excusal.reason)
        excusal.makeup_plan = request.form.get("makeup_plan", excusal.makeup_plan)
        excusal.poc = request.form.get("poc", excusal.poc)
        excusal.position = request.form.get("position", excusal.position)
        
        db.session.commit()
        flash("Excusal updated successfully.")
        return redirect(url_for("pending_excusals"))


@app.route('/staff-dashboard', methods=['GET', 'POST'])
@staff_required
def staff_dashboard():
    try:
        # quick approve/deny actions
        if request.method == 'POST':
            action = request.form.get('action')
            excusal_id = request.form.get('excusal_id')
            if action in ('approve', 'deny') and excusal_id:
                exc = Excusal.query.get(excusal_id)
                if exc:
                    exc.status = 'approved' if action=='approve' else 'denied'
                    # update cadet status
                    cadet = Cadet.query.filter(Cadet.name==exc.name).first()
                    if cadet:
                        cadet.status = 'excused' if action=='approve' else 'present'
                    db.session.commit()
                    flash('Updated excusal.')
            # approve all pending for an event
            if request.form.get('bulk_action') == 'approve_event':
                ev = request.form.get('event_id')
                if ev:
                    event = Event.query.get(ev)
                    if event:
                        pending = Excusal.query.filter_by(event=event.name, status='pending').all()
                        for p in pending:
                            p.status = 'approved'
                            cadet = Cadet.query.filter(Cadet.name==p.name).first()
                            if cadet:
                                cadet.status = 'excused'
                        db.session.commit()
                        flash('Approved pending excusals for event.')
            return redirect(url_for('staff_dashboard'))

        # Group pending excusals by event
        pending = Excusal.query.filter_by(status='pending').all()
        events = {}
        for p in pending:
            events.setdefault(p.event or 'Unspecified', []).append(p)
        all_events = Event.query.order_by(Event.date).all()
        return render_template('staff_dashboard.html', events_map=events, all_events=all_events)
    
    except Exception as e:
        app.logger.error(f"Staff dashboard error: {e}")
        flash("Dashboard error occurred. Database may need initialization.")
        return redirect(url_for("home"))


# Who is coming page
@app.route("/whoiscoming", methods=["GET", "POST"])
@staff_required
def whoiscoming():
    # select event for attendance view
    ev_id = request.args.get('event_id') or request.form.get('event_id')
    events = Event.query.order_by(Event.date).all()

    if request.method == "POST" and request.form.get('override_action') == 'update':
        # manual override of cadet status for specific event
        cadet_id = request.form.get("cadet_id")
        new_status = request.form.get("status")
        event_id = request.form.get("event_id")
        if cadet_id and event_id and new_status:
            # upsert override
            ov = AttendanceOverride.query.filter_by(cadet_id=cadet_id, event_id=event_id).first()
            if ov:
                ov.status = new_status
            else:
                db.session.add(AttendanceOverride(cadet_id=cadet_id, event_id=event_id, status=new_status))
            db.session.commit()
            flash("Override saved.")
        return redirect(url_for('whoiscoming', event_id=event_id))

    # determine selected event (default to upcoming first)
    sel_event = None
    if ev_id:
        sel_event = Event.query.get(ev_id)
    else:
        sel_event = Event.query.order_by(Event.date).first()

    cadets = Cadet.query.order_by(Cadet.name).all()

    # Build status per cadet for the selected event
    cadet_rows = []
    for c in cadets:
        status = 'present'  # default green
        # check explicit override
        if sel_event:
            ov = AttendanceOverride.query.filter_by(cadet_id=c.id, event_id=sel_event.id).first()
            if ov:
                status = ov.status
            else:
                # check excusals for this cadet for this event
                exc = Excusal.query.filter(Excusal.name==c.name, Excusal.event==sel_event.name).order_by(Excusal.date.desc()).first()
                if exc:
                    if exc.status == 'pending':
                        status = 'pending'
                    elif exc.status == 'approved' or exc.status == 'excused':
                        status = 'excused'
                    elif exc.status == 'denied':
                        status = 'present'

        cadet_rows.append({'cadet': c, 'status': status})

    return render_template('whoiscoming.html', events=events, sel_event=sel_event, cadet_rows=cadet_rows)


# Roster management (list/add/edit)
@app.route("/roster", methods=["GET", "POST"])
@staff_required
def roster():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            name = request.form.get("name", "").strip()
            if name:
                # avoid duplicates (case-insensitive)
                existing = [c for c in Cadet.query.all() if normalize_name(c.name) == normalize_name(name)]
                if existing:
                    flash("A cadet with that name already exists.")
                else:
                    db.session.add(Cadet(name=name, rank=''))
                    db.session.commit()
                    
                    # Add to CSV file
                    roster_path = os.path.join(app.root_path, 'roster.csv')
                    try:
                        # Read existing CSV
                        names = []
                        if os.path.exists(roster_path):
                            with open(roster_path, 'r', newline='') as f:
                                reader = csv.DictReader(f)
                                for row in reader:
                                    existing_name = (row.get('names') or '').strip()
                                    if existing_name:
                                        names.append(existing_name)
                        
                        # Add new name and sort
                        names.append(name)
                        names.sort()
                        
                        # Write back to CSV
                        with open(roster_path, 'w', newline='') as f:
                            writer = csv.writer(f)
                            writer.writerow(['names'])
                            for n in names:
                                writer.writerow([n])
                        
                        flash("Cadet added to roster and CSV file.")
                    except Exception as e:
                        flash("Cadet added to roster, but failed to update CSV file.")
        elif action == "delete":
            cadet_id = request.form.get("cadet_id")
            cadet = Cadet.query.get(cadet_id)
            if cadet:
                cadet_name = cadet.name
                db.session.delete(cadet)
                db.session.commit()
                
                # Remove from CSV file
                roster_path = os.path.join(app.root_path, 'roster.csv')
                try:
                    # Read existing CSV
                    names = []
                    if os.path.exists(roster_path):
                        with open(roster_path, 'r', newline='') as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                existing_name = (row.get('names') or '').strip()
                                if existing_name and normalize_name(existing_name) != normalize_name(cadet_name):
                                    names.append(existing_name)
                    
                    # Write back to CSV
                    with open(roster_path, 'w', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow(['names'])
                        for n in names:
                            writer.writerow([n])
                    
                    flash("Cadet removed from roster and CSV file.")
                except Exception as e:
                    flash("Cadet removed from roster, but failed to update CSV file.")
        elif action == "edit":
            cadet_id = request.form.get("cadet_id")
            name = request.form.get("name", "").strip()
            cadet = Cadet.query.get(cadet_id)
            if cadet:
                cadet.name = name or cadet.name
                db.session.commit()
                flash("Cadet updated.")
        elif action == "reload_csv":
            # Reload names from roster.csv
            roster_path = os.path.join(app.root_path, 'roster.csv')
            if os.path.exists(roster_path):
                added_count = 0
                with open(roster_path, newline='') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        name = (row.get('names') or row.get('name') or row.get('Name') or '').strip()
                        if name:
                            # avoid duplicates (case-insensitive)
                            existing = [c for c in Cadet.query.all() if normalize_name(c.name) == normalize_name(name)]
                            if not existing:
                                db.session.add(Cadet(name=name, rank=''))
                                added_count += 1
                db.session.commit()
                flash(f"Added {added_count} new cadets from roster.csv")
            else:
                flash("roster.csv file not found")

        return redirect(url_for("roster"))

    cadets = Cadet.query.order_by(Cadet.name).all()
    return render_template("roster.html", cadets=cadets)


# Export roster as CSV
@app.route("/export_roster")
@staff_required
def export_roster():
    cadets = Cadet.query.order_by(Cadet.name).all()
    si = []
    # Use csv.writer on list to build rows
    output = []
    header = ["name", "rank", "status"]
    output.append(header)
    for c in cadets:
        output.append([c.name, c.rank or "", c.status or "present"])

    # build CSV string
    from io import StringIO
    s = StringIO()
    writer = csv.writer(s)
    writer.writerows(output)
    resp = make_response(s.getvalue())
    resp.headers["Content-Disposition"] = "attachment; filename=roster.csv"
    resp.headers["Content-Type"] = "text/csv"
    return resp


@app.route('/export_excusals')
@staff_required
def export_excusals():
    excusals = Excusal.query.order_by(Excusal.date).all()
    output = []
    header = ["id","date","name","event","reason","status","email","phone"]
    output.append(header)
    for e in excusals:
        output.append([e.id, e.date or "", e.name or "", e.event or "", e.reason or "", e.status or "", e.email or "", e.phone or ""])
    from io import StringIO
    s = StringIO()
    writer = csv.writer(s)
    writer.writerows(output)
    resp = make_response(s.getvalue())
    resp.headers["Content-Disposition"] = "attachment; filename=excusals.csv"
    resp.headers["Content-Type"] = "text/csv"
    return resp


@app.route('/export_attendance')
@staff_required
def export_attendance():
    event_id = request.args.get('event_id')
    if not event_id:
        flash('event_id required for attendance export')
        return redirect(url_for('whoiscoming'))

    ev = Event.query.get(event_id)
    if not ev:
        flash('Event not found')
        return redirect(url_for('whoiscoming'))

    cadets = Cadet.query.order_by(Cadet.name).all()
    rows = []
    header = ['name', 'rank', 'status', 'excusal_date', 'excusal_reason']
    rows.append(header)
    for c in cadets:
        status = 'present'
        excusal_date = ''
        excusal_reason = ''
        ov = AttendanceOverride.query.filter_by(cadet_id=c.id, event_id=ev.id).first()
        if ov:
            status = ov.status
        else:
            exc = Excusal.query.filter(Excusal.name==c.name, Excusal.event==ev.name).order_by(Excusal.date.desc()).first()
            if exc:
                if exc.status == 'pending':
                    status = 'pending'
                elif exc.status in ('approved','excused'):
                    status = 'excused'
                elif exc.status == 'denied':
                    status = 'present'
                excusal_date = exc.date or ''
                excusal_reason = exc.reason or ''
        rows.append([c.name, c.rank or '', status, excusal_date, excusal_reason])

    from io import StringIO
    s = StringIO()
    writer = csv.writer(s)
    writer.writerows(rows)
    resp = make_response(s.getvalue())
    fname = f"attendance_{ev.name.replace(' ','_')}_{ev.date}.csv"
    resp.headers['Content-Disposition'] = f'attachment; filename={fname}'
    resp.headers['Content-Type'] = 'text/csv'
    return resp


# Events management
@app.route("/events", methods=["GET", "POST"]) 
def events():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        date_s = request.form.get("date", "").strip()
        if name and date_s:
            db.session.add(Event(name=name, date=date_s))
            db.session.commit()
            flash("Event added.")
        return redirect(url_for("events"))

    evs = Event.query.order_by(Event.date).all()
    # filter out past events for dropdowns
    today_s = date.today().isoformat()
    upcoming = [e for e in evs if e.date >= today_s]
    return render_template("events.html", events=evs, upcoming_events=upcoming)


# Diagnostic routes to help debug deployment/static serving
@app.route('/_health')
def _health():
    return 'OK', 200


@app.route('/test-image')
def test_image():
    # returns the excusal PNG directly so you can confirm static serving
    return send_from_directory(os.path.join(app.root_path, 'static'), 'excusal_form.png')


# Run app
if __name__ == "__main__":
    # initialize DB and logging
    with app.app_context():
        db.create_all()
        # seed roster from roster.csv if DB has no cadets
        if Cadet.query.count() == 0:
            roster_path = os.path.join(app.root_path, 'roster.csv')
            if os.path.exists(roster_path):
                with open(roster_path, newline='') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        name = (row.get('names') or row.get('name') or row.get('Name') or '').strip()
                        if name:
                            # avoid duplicates
                            if not Cadet.query.filter_by(name=name).first():
                                db.session.add(Cadet(name=name, rank=''))
                    db.session.commit()
        # seed default events if none
        if Event.query.count() == 0:
            db.session.add_all([
                Event(name='llab', date='2025-09-17'),
                Event(name='class', date='2025-09-17'),
                Event(name='2025 FTX', date='2025-10-01'),
            ])
            db.session.commit()

    # set up a rotating file handler for easier debugging
    log_file = os.path.join(app.root_path, 'app.log')
    handler = RotatingFileHandler(log_file, maxBytes=1000000, backupCount=3)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')
    handler.setFormatter(formatter)
    if not app.logger.handlers:
        app.logger.addHandler(handler)
    app.logger.setLevel(logging.DEBUG)
    app.logger.info('Starting ROTC Excusal app')

    try:
        # run on localhost explicitly; change host if you need external access
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port)

    except Exception as e:
        app.logger.exception('Unhandled exception while running app:')
        raise
