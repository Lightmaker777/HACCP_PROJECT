# app.py
from flask import Flask, render_template, request, redirect, url_for, session, Response, send_file, flash, jsonify
import sqlite3
import bcrypt
import openpyxl 
from io import BytesIO
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Confirmation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_name = db.Column(db.String(100), nullable=False)
    confirmation_date = db.Column(db.String(10), nullable=False)
    employee_number = db.Column(db.String(50), nullable=False)
    signature = db.Column(db.Text, nullable=False)


app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Geheimen Schlüssel für Sessions

# Passwort-Hashing und Überprüfung
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def check_password(stored_password, password):
    return bcrypt.checkpw(password.encode('utf-8'), stored_password)

def authenticate(username, password):
    conn = sqlite3.connect('haccp.db')
    c = conn.cursor()
    c.execute('SELECT password FROM users WHERE username = ?', (username,))
    user = c.fetchone()
    conn.close()

    if user and check_password(user[0], password):  # Überprüfe, ob das Passwort übereinstimmt
        return True
    return False

# Datenbank initialisieren und Tabelle erstellen
def init_db():
    conn = sqlite3.connect('haccp.db')
    c = conn.cursor()
    c.execute(''' 
        CREATE TABLE IF NOT EXISTS produkte (
            id INTEGER PRIMARY KEY,
            produkt TEXT,
            temperatur REAL,
            lagerort TEXT,
            status TEXT,          -- NEU: z. B. "OK" oder "WARNUNG"
            risikostufe TEXT      -- NEU: z. B. "hoch", "mittel", "niedrig"
        )
    ''')
    
    # Erstelle die Sicherheitstabelle
    c.execute('''
        CREATE TABLE IF NOT EXISTS sicherheit (
            id INTEGER PRIMARY KEY,
            faktor TEXT,
            überprüfung TEXT
        )
    ''')
    
    conn.commit()
    conn.close()


# Erstelle eine Tabelle für die Bestätigungen
def init_confirmation_db():
    conn = sqlite3.connect('haccp.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS confirmations (
            id INTEGER PRIMARY KEY,
            employee_name TEXT,
            confirmation_date TEXT,
            signature TEXT,  -- Diese Spalte speichert die Unterschrift
            employee_number TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Überprüfe und aktualisiere die Datenbankstruktur, wenn nötig
def update_db_schema():
    conn = sqlite3.connect('haccp.db')
    c = conn.cursor()

    # Versuche, die 'status'-Spalte hinzuzufügen
    try:
        c.execute("ALTER TABLE produkte ADD COLUMN status TEXT")
        print("Spalte 'status' wurde hinzugefügt.")
    except sqlite3.OperationalError:
        print("Spalte 'status' existiert bereits.")

    # Versuche, die 'risikostufe'-Spalte hinzuzufügen
    try:
        c.execute("ALTER TABLE produkte ADD COLUMN risikostufe TEXT")
        print("Spalte 'risikostufe' wurde hinzugefügt.")
    except sqlite3.OperationalError:
        print("Spalte 'risikostufe' existiert bereits.")

    conn.commit()
    conn.close()

# Benutzer-Datenbank initialisieren und Tabelle erstellen
def init_user_db():
    conn = sqlite3.connect('haccp.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT DEFAULT 'mitarbeiter'
        )
    ''')
    conn.commit()
    conn.close()

# Initialisierung beim Start der Anwendung
def initialize():
    init_db()  # Initialisiere die Tabellen
    init_user_db()  # Initialisiere die Benutzertabelle
    update_db_schema()  # Aktualisiere die Tabellen, falls Spalten fehlen
    create_default_admin()  # Erstelle einen standardmäßigen Admin-Benutzer
    init_confirmation_db()  # Initialisiere die Bestätigungstabelle
# Standard-Admin erstellen
def create_default_admin():
    conn = sqlite3.connect('haccp.db')
    c = conn.cursor()
    
    # Überprüfe, ob bereits ein Admin-Benutzer existiert
    c.execute('SELECT * FROM users WHERE username = "admin"')
    if c.fetchone() is None:  # Wenn kein Admin vorhanden ist
        hashed_password = hash_password('admin123')  # Beispiel-Passwort
        c.execute('''
            INSERT INTO users (username, password, role)
            VALUES (?, ?, ?)
        ''', ('admin', hashed_password, 'admin'))
        conn.commit()
    conn.close()

# Aufruf beim Start der Anwendung
initialize()

@app.route('/register', methods=['GET', 'POST'])
def register():
    # Wenn der Benutzer bereits eingeloggt ist, leite ihn zur Index-Seite oder einer anderen Seite weiter
    if 'user' in session:  # Überprüft, ob der Benutzer eingeloggt ist
        return redirect(url_for('index'))  # oder eine andere Seite deiner Wahl
    
    # Wenn die Anfrage eine POST-Anfrage ist, verarbeite die Registrierung
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Überprüfe, ob der Benutzername schon existiert
        conn = sqlite3.connect('haccp.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE username = ?', (username,))
        if c.fetchone():
            error = "Benutzername ist bereits vergeben."
            return render_template('register.html', error=error)

        # Speichern des neuen Benutzers
        hashed_password = hash_password(password)  # Passwort hashen
        c.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
        conn.commit()
        conn.close()

        flash("Registrierung erfolgreich! Sie können sich jetzt anmelden.", "success")
        # Weiterleitung zur Login-Seite nach erfolgreicher Registrierung
        return redirect(url_for('login'))

    # Rückgabe der Registrierungsseite, wenn keine POST-Anfrage vorliegt
    return render_template('register.html')

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # Überprüfung der Benutzeranmeldedaten
        conn = sqlite3.connect('haccp.db')
        c = conn.cursor()
        c.execute('SELECT username, password FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password(user[1], password):  # Überprüfe das gehashte Passwort
            session['user'] = user[0]  # Session speichern
            return redirect(url_for('dashboard'))  # Weiter zum Dashboard
        else:
            flash("Ungültige Anmeldedaten!", "danger")
            return render_template('login.html')

    return render_template('login.html')

@app.route("/dashboard")
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    return render_template('dashboard.html')  # Hier wird das Dashboard angezeigt

@app.route("/logout")
def logout():
    # Löschen der Benutzersitzung
    session.pop('user', None)  # Entfernt den 'user' Key aus der Session

    # Weiterleitung zur Login-Seite
    return redirect(url_for('login'))

# Authentifizierungsmiddleware
@app.before_request
def require_login_and_admin():
    # Liste der Seiten, die ohne Login zugänglich sind
    public_routes = ['login', 'register', 'static']
    
    # Überprüfe, ob der Benutzer zu einer öffentlichen Seite zugreift
    if request.endpoint in public_routes:
        return None

    # Wenn der Benutzer nicht eingeloggt ist, leite ihn zur Login-Seite weiter
    if 'user' not in session:
        return redirect(url_for('login'))
    else:
        # Wenn der Benutzer eingeloggt ist, überprüfe, ob er ein Admin ist, falls erforderlich
        admin_routes = ['admin_dashboard', 'admin_settings']
        
        if request.endpoint in admin_routes:
            conn = sqlite3.connect('haccp.db')
            c = conn.cursor()
            c.execute('SELECT role FROM users WHERE username = ?', (session['user'],))
            user = c.fetchone()
            conn.close()

            if not user or user[0] != 'admin':
                return redirect(url_for('dashboard'))

@app.route("/", methods=["GET", "POST"])
def index():
    # Überprüfen, ob der Benutzer eingeloggt ist
    if 'user' not in session:  # Wenn der Benutzer nicht eingeloggt ist
        print("Benutzer nicht eingeloggt. Weiterleitung zur Login-Seite.")  # Debugging-Ausgabe
        return redirect(url_for('login'))  # Weiterleitung zur Login-Seite
    
    # Wenn der Benutzer eingeloggt ist, zeige die Startseite an und ermögliche das Eintragen von Produkten
    if request.method == "POST":
        produkt = request.form["produkt"]
        temperatur = float(request.form["temperatur"])
        lagerort = request.form["lagerort"]

        produkt_risiko = {
            "Fleisch": {"min_temp": 2, "max_temp": 7, "risiko": "hoch"},
            "Milch": {"min_temp": 0, "max_temp": 4, "risiko": "hoch"},
            "Gemüse": {"min_temp": 4, "max_temp": 12, "risiko": "mittel"},
            "Honig": {"min_temp": -99, "max_temp": 99, "risiko": "niedrig"},
        }

        status = "OK"
        risikostufe = "unbekannt"

        if produkt in produkt_risiko:
            limits = produkt_risiko[produkt]
            risikostufe = limits["risiko"]
            if temperatur < limits["min_temp"] or temperatur > limits["max_temp"]:
                status = "WARNUNG"

        # Speichern des Produkts in der Datenbank
        conn = sqlite3.connect('haccp.db')
        c = conn.cursor()
        c.execute(''' 
            INSERT INTO produkte (produkt, temperatur, lagerort, status, risikostufe)
            VALUES (?, ?, ?, ?, ?)
        ''', (produkt, temperatur, lagerort, status, risikostufe))
        conn.commit()
        conn.close()

        # Weiterleitung zur Bestätigungsseite mit den relevanten Werten als URL-Parameter
        return redirect(url_for('confirmation', produkt=produkt, temperatur=temperatur, status=status, risikostufe=risikostufe))

    # Hier geben wir die HTML-Seite zurück, wenn die Anfrage eine GET-Anfrage ist
    return render_template("index.html")

@app.route("/confirmation", methods=["GET", "POST"])
def confirmation():
    produkt = request.args.get('produkt')
    temperatur = request.args.get('temperatur')
    status = request.args.get('status')
    risikostufe = request.args.get('risikostufe')

    if request.method == "POST":
        if request.is_json:
            data = request.get_json()
            employee_name = data['employee_name']
            confirmation_date = data['confirmation_date']
            signature_data = data['signature']
            employee_number = data['employee_number']

            # Signatur & Daten speichern
            print("Unterschrift gespeichert:", signature_data)

            conn = sqlite3.connect('haccp.db')
            c = conn.cursor()
            c.execute('''
                INSERT INTO confirmations (employee_name, confirmation_date, signature, employee_number)
                VALUES (?, ?, ?, ?)
            ''', (employee_name, confirmation_date, signature_data, employee_number))
            conn.commit()
            conn.close()

            return jsonify({"message": "Bestätigung gespeichert"}), 200
        else:
            return jsonify({"error": "Erwarte JSON-Daten"}), 400

    # GET-Anfrage
    return render_template("confirmation.html", 
                           produkt=produkt, 
                           temperatur=temperatur, 
                           status=status, 
                           risikostufe=risikostufe)


@app.route("/confirmations")
def confirmations():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('haccp.db')
    c = conn.cursor()
    c.execute('SELECT * FROM confirmations')
    rows = c.fetchall()
    conn.close()

    return render_template("confirmations.html", rows=rows)


# Anzeige der gespeicherten Produkte
@app.route("/produkte", methods=["GET", "POST"])
def produkte():
    if 'user' not in session:
        return redirect(url_for('login'))

    # Abrufen der Produkte aus der Datenbank
    conn = sqlite3.connect('haccp.db')
    c = conn.cursor()
    c.execute('SELECT * FROM produkte')  # Hole alle Produkte aus der Tabelle
    rows = c.fetchall()  # Alle Zeilen abrufen
    conn.close()

    print(rows)  # Debugging-Ausgabe

    if request.method == "POST":
        produkt = request.form["produkt"]
        temperatur = float(request.form["temperatur"])
        lagerort = request.form["lagerort"]

        # Hier kannst du eine detaillierte Validierung durchführen
        produkt_risiko = {
            "Fleisch": {"min_temp": 2, "max_temp": 7, "risiko": "hoch"},
            "Milch": {"min_temp": 0, "max_temp": 4, "risiko": "hoch"},
            "Gemüse": {"min_temp": 4, "max_temp": 12, "risiko": "mittel"},
            "Honig": {"min_temp": -99, "max_temp": 99, "risiko": "niedrig"},
        }

        status = "OK"
        risikostufe = "unbekannt"

        if produkt in produkt_risiko:
            limits = produkt_risiko[produkt]
            risikostufe = limits["risiko"]
            if temperatur < limits["min_temp"] or temperatur > limits["max_temp"]:
                status = "WARNUNG"

        # Speichern in der Datenbank
        conn = sqlite3.connect('haccp.db')
        c = conn.cursor()
        c.execute('''INSERT INTO produkte (produkt, temperatur, lagerort, status, risikostufe) 
                     VALUES (?, ?, ?, ?, ?)''',
                  (produkt, temperatur, lagerort, status, risikostufe))
        conn.commit()
        conn.close()

        flash(f"{produkt} erfolgreich validiert!", "success")
        return redirect(url_for('produkte'))

    # Übergebe die abgerufenen Produkt-Daten an das Template
    return render_template("produkte.html", rows=rows)

@app.route("/produkte_validierung", methods=["GET", "POST"])
def produkte_validierung():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == "POST":
        produkt = request.form["produkt"]
        temperatur = float(request.form["temperatur"])
        lagerort = request.form["lagerort"]

        # Hier kannst du eine detaillierte Validierung durchführen
        produkt_risiko = {
            "Fleisch": {"min_temp": 2, "max_temp": 7, "risiko": "hoch"},
            "Milch": {"min_temp": 0, "max_temp": 4, "risiko": "hoch"},
            "Gemüse": {"min_temp": 4, "max_temp": 12, "risiko": "mittel"},
            "Honig": {"min_temp": -99, "max_temp": 99, "risiko": "niedrig"},
        }

        status = "OK"
        risikostufe = "unbekannt"

        if produkt in produkt_risiko:
            limits = produkt_risiko[produkt]
            risikostufe = limits["risiko"]
            if temperatur < limits["min_temp"] or temperatur > limits["max_temp"]:
                status = "WARNUNG"

        # Speichern der Daten in der Datenbank
        conn = sqlite3.connect('haccp.db')
        c = conn.cursor()
        c.execute('''INSERT INTO produkte (produkt, temperatur, lagerort, status, risikostufe) 
                     VALUES (?, ?, ?, ?, ?)''',
                  (produkt, temperatur, lagerort, status, risikostufe))
        conn.commit()
        conn.close()

        flash(f"Produkt {produkt} erfolgreich validiert!", "success")
        return redirect(url_for('produkte_validierung'))

    return render_template("produkte_validierung.html")

@app.route("/sicherheit", methods=["GET", "POST"])
def sicherheit():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == "POST":
        sicherheitsfaktor = request.form["sicherheitsfaktor"]
        überprüfung = request.form["überprüfung"]

        # Speichern der Daten in der Datenbank (z.B. 'sicherheit' Tabelle)
        conn = sqlite3.connect('haccp.db')
        c = conn.cursor()
        c.execute('''INSERT INTO sicherheit (faktor, überprüfung) VALUES (?, ?)''',
                  (sicherheitsfaktor, überprüfung))
        conn.commit()
        conn.close()

        flash(f"Sicherheitsüberprüfung für {sicherheitsfaktor} abgeschlossen!", "success")
        return redirect(url_for('sicherheit'))

    return render_template("sicherheit.html")

# Export der Daten in CSV
@app.route("/export")
def export_csv():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    conn = sqlite3.connect('haccp.db')
    c = conn.cursor()
    c.execute('SELECT * FROM produkte')
    rows = c.fetchall()
    conn.close()

    # Verbessert den CSV-Export um alle Spalten zu berücksichtigen
    output = "ID,Produkt,Temperatur,Lagerort,Status,Risikostufe\n"
    for row in rows:
        # Schützt vor Fehlern, wenn Spalten fehlen
        rowData = []
        for i in range(min(6, len(row))):  # Maximal 6 Spalten (ID, Produkt, Temperatur, Lagerort, Status, Risikostufe)
            rowData.append(str(row[i] if i < len(row) else ""))
        output += ",".join(rowData) + "\n"

    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=produkte.csv"}
    )

# Export der Daten in Excel
@app.route("/export_excel")
def export_excel():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    conn = sqlite3.connect('haccp.db')
    c = conn.cursor()
    c.execute('SELECT * FROM produkte')
    rows = c.fetchall()
    conn.close()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ID", "Produkt", "Temperatur", "Lagerort", "Status", "Risikostufe"])

    for row in rows:
        # Stellt sicher, dass alle Spalten eingeschlossen werden
        row_data = list(row)
        while len(row_data) < 6:  # Fülle fehlende Spalten mit leeren Werten
            row_data.append("")
        ws.append(row_data)

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(output, as_attachment=True, download_name="produkte.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# Anzeige von Statistiken
@app.route("/statistiken")
def statistiken():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    conn = sqlite3.connect('haccp.db')
    c = conn.cursor()
    
    # Durchschnittstemperatur abrufen
    c.execute('SELECT AVG(temperatur) FROM produkte')
    avg_temp = c.fetchone()[0]
    
    # Anzahl der Warnungen zählen
    c.execute('SELECT COUNT(*) FROM produkte WHERE status = "WARNUNG"')
    warning_count = c.fetchone()[0]
    
    # Gesamtzahl der Produkte abrufen
    c.execute('SELECT COUNT(*) FROM produkte')
    total_count = c.fetchone()[0]
    
    conn.close()
    
    return render_template("statistiken.html", 
                          avg_temp=avg_temp, 
                          warning_count=warning_count, 
                          total_count=total_count)

if __name__ == "__main__":
    app.run(debug=True)