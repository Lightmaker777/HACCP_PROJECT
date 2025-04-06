from flask import Flask, render_template, request, redirect, url_for, session, Response, send_file, flash
import sqlite3
import bcrypt
import openpyxl 
from io import BytesIO

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
            status TEXT,          -- NEU: z. B. "OK" oder "WARNUNG"
            risikostufe TEXT      -- NEU: z. B. "hoch", "mittel", "niedrig"
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

# Initialisiere die Datenbank und aktualisiere die Struktur bei jedem Start
def initialize():
    init_db()  # Initialisiere die Tabelle
    update_db_schema()  # Aktualisiere die Tabelle, falls Spalten fehlen

# Aufruf beim Start der Anwendung
initialize()

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

# Initialisierung
init_db()
init_user_db()

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
        c.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))
        user = c.fetchone()
        conn.close()

        if user:
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
    # Überprüfe, ob der Benutzer zur Login- oder Registrierungsseite zugreift
    if request.endpoint in ['login', 'register']:
        return None

    # Wenn der Benutzer nicht eingeloggt ist, leite ihn zur Login-Seite weiter
    if 'user' not in session:
        if request.endpoint not in ['login', 'static']:
            return redirect(url_for('login'))
    else:
        # Wenn der Benutzer eingeloggt ist, überprüfe, ob er ein Admin ist, falls erforderlich
        conn = sqlite3.connect('haccp.db')
        c = conn.cursor()
        c.execute('SELECT role FROM users WHERE username = ?', (session['user'],))
        user = c.fetchone()
        conn.close()

        if user and user[0] != 'admin' and request.endpoint in ['admin_dashboard', 'admin_settings']:
            return redirect(url_for('index'))


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

# Rufe die Funktion beim Start der Anwendung auf
create_default_admin()

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


def reset_db():
    conn = sqlite3.connect('haccp.db')
    c = conn.cursor()
    
    # Lösche die existierende Tabelle, falls notwendig
    c.execute('DROP TABLE IF EXISTS produkte')

    # Erstelle die Tabelle mit den neuen Spalten
    c.execute('''
        CREATE TABLE produkte (
            id INTEGER PRIMARY KEY,
            produkt TEXT,
            temperatur REAL,
            lagerort TEXT,
            status TEXT,           -- z. B. "OK" oder "WARNUNG"
            risikostufe TEXT       -- z. B. "hoch", "mittel", "niedrig"
        )
    ''')

    conn.commit()
    conn.close()


@app.route("/confirmation")
def confirmation():
    produkt = request.args.get('produkt')
    temperatur = request.args.get('temperatur')
    status = request.args.get('status')
    risikostufe = request.args.get('risikostufe')

    # Bestätigungsseite mit Bootstrap-Styling
    return render_template("confirmation.html", produkt=produkt, temperatur=temperatur, status=status, risikostufe=risikostufe)




# Anzeige der gespeicherten Produkte
@app.route("/produkte", methods=["GET", "POST"])
def produkte():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == "POST":
        produkt = request.form["produkt"]
        temperatur = float(request.form["temperatur"])
        lagerort = request.form["lagerort"]

        # Hier kannst du eine detaillierte Validierung durchführen:
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
        c.execute('''INSERT INTO produkte (produkt, temperatur, lagerort, status, risikostufe) VALUES (?, ?, ?, ?, ?)''',
                  (produkt, temperatur, lagerort, status, risikostufe))
        conn.commit()
        conn.close()

        flash(f"{produkt} erfolgreich validiert!", "success")
        return redirect(url_for('produkte'))

    return render_template("produkte.html")

@app.route("/produkte_validierung", methods=["GET", "POST"])
def produkte_validierung():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == "POST":
        produkt = request.form["produkt"]
        temperatur = float(request.form["temperatur"])
        lagerort = request.form["lagerort"]

        # Speichern der Daten in der Datenbank (z.B. 'produkte' Tabelle)
        conn = sqlite3.connect('haccp.db')
        c = conn.cursor()
        c.execute('''INSERT INTO produkte (produkt, temperatur, lagerort) VALUES (?, ?, ?)''',
                  (produkt, temperatur, lagerort))
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
    conn = sqlite3.connect('haccp.db')
    c = conn.cursor()
    c.execute('SELECT * FROM produkte')
    rows = c.fetchall()
    conn.close()

    output = "ID,Produkt,Temperatur,Lagerort\n"
    for row in rows:
        output += f"{row[0]},{row[1]},{row[2]},{row[3]}\n"

    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=produkte.csv"}
    )

# Export der Daten in Excel
@app.route("/export_excel")
def export_excel():
    conn = sqlite3.connect('haccp.db')
    c = conn.cursor()
    c.execute('SELECT * FROM produkte')
    rows = c.fetchall()
    conn.close()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ID", "Produkt", "Temperatur", "Lagerort"])

    for row in rows:
        ws.append(row)

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(output, as_attachment=True, download_name="produkte.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# Anzeige von Statistiken
@app.route("/statistiken")
def statistiken():
    conn = sqlite3.connect('haccp.db')
    c = conn.cursor()
    c.execute('SELECT AVG(temperatur) FROM produkte')
    avg_temp = c.fetchone()[0]
    conn.close()
    return render_template("statistiken.html", avg_temp=avg_temp)

if __name__ == "__main__":
    app.run(debug=True)



