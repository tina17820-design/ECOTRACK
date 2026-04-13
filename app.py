import os
import sqlite3
import random
from flask import Flask, render_template, request, redirect, url_for, session, flash

# ----------------- CONFIG -----------------
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
app = Flask(__name__, template_folder=template_dir)
app.secret_key = "eco_secret_key"

# Enable enumerate in Jinja2 templates
app.jinja_env.globals.update(enumerate=enumerate)

# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), "../database/ecotrack.db")

# ----------------- POINT SYSTEM -----------------
ACTIVITY_POINTS = {
    "walk": {"base": 10, "eco_bonus": 10},
    "bike": {"base": 15, "eco_bonus": 15},
    "bus": {"base": 8, "eco_bonus": 8},
    "car": {"base": 2, "eco_bonus": 0},
    "electricity": {"base": 5, "eco_bonus": 0},  # per 5 kWh
    "veg_meal": {"base": 7, "eco_bonus": 7},
    "non_veg_meal": {"base": 3, "eco_bonus": 0},
}

# ----------------- EMISSION FACTORS -----------------
EMISSION_FACTORS = {
    "walk": 0.05,         # kg CO2 per km
    "bike": 0.03,         # kg CO2 per km
    "bus": 0.05,          # kg CO2 per km
    "car": 0.21,          # kg CO2 per km
    "electricity": 0.7,   # kg CO2 per kWh
    "veg_meal": 0.5,      # kg CO2 per meal
    "non_veg_meal": 2.0,  # kg CO2 per meal
}

# ----------------- DATABASE -----------------
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password TEXT,
                    points INTEGER DEFAULT 0
                )''')

    # Activities table
    c.execute('''CREATE TABLE IF NOT EXISTS activities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT,
                    activity TEXT,
                    amount REAL,
                    carbon_emission REAL,
                    base_points INTEGER,
                    bonus_points INTEGER,
                    total_points INTEGER,
                    date TEXT
                )''')
    conn.commit()
    conn.close()

init_db()

# ----------------- ROUTES -----------------
@app.route('/')
def home():
    return redirect(url_for('login'))

# ---------- Register ----------
@app.route('/register', methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            flash("Registration successful! Please login.", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Username already exists!", "danger")
        finally:
            conn.close()
    return render_template("register.html")

# ---------- Login ----------
@app.route('/login', methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()

        if user:
            session['username'] = user[1]
            session['user_id'] = user[0]
            flash(f"Welcome {user[1]}!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials!", "danger")

    return render_template("login.html")

# ---------- Dashboard ----------
@app.route('/dashboard')
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Get user points
    c.execute("SELECT points FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    points = user["points"] if user else 0

    # Count activities
    c.execute("SELECT COUNT(*) as count FROM activities WHERE username = ?", (username,))
    activities_count = c.fetchone()["count"]

    conn.close()

    # Random eco tips
    eco_tips = [
        "Turn off lights when not in use 💡",
        "Use reusable bags instead of plastic 🛍️",
        "Save water – fix leaks immediately 🚰",
        "Walk or cycle instead of driving 🚴",
        "Plant a tree this month 🌱"
    ]
    eco_tip = random.choice(eco_tips)

    return render_template("dashboard.html",
                           points=points,
                           activities_count=activities_count,
                           eco_tip=eco_tip)

# ---------- Activity ----------
@app.route('/activity', methods=["GET", "POST"])
def activity():
    if "username" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        activity_type = request.form['activity']
        amount = float(request.form['amount'])

        # Calculate carbon emission
        emission_factor = EMISSION_FACTORS.get(activity_type, 0)
        carbon_emission = round(amount * emission_factor, 2)

        # Calculate points
        mapping = ACTIVITY_POINTS.get(activity_type, {"base": 0, "eco_bonus": 0})
        if activity_type == "electricity":
            base_points = int((amount / 5) * mapping["base"])
        else:
            base_points = int(amount * mapping["base"])

        bonus_points = int(amount * mapping["eco_bonus"]) if mapping["eco_bonus"] > 0 else 0
        total_points = base_points + bonus_points

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT INTO activities (username, activity, amount, carbon_emission, base_points, bonus_points, total_points, date) 
            VALUES (?, ?, ?, ?, ?, ?, ?, date('now'))
        """, (session["username"], activity_type, amount, carbon_emission, base_points, bonus_points, total_points))
        c.execute("UPDATE users SET points = points + ? WHERE username = ?", (total_points, session["username"]))
        conn.commit()
        conn.close()

        flash(f"Activity added! You earned {total_points} points 🌱", "success")
        return redirect(url_for('dashboard'))

    return render_template("activity.html")

# ---------- Leaderboard ----------
@app.route('/leaderboard')
def leaderboard():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT id, username, points FROM users ORDER BY points DESC LIMIT 10")
    top_users = c.fetchall()
    conn.close()
    return render_template("leaderboard.html", users=top_users)

# ---------- User History ----------
@app.route('/user/<int:user_id>')
def user_history(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Get username
    c.execute("SELECT username FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    if not user:
        conn.close()
        return "User not found", 404
    username = user["username"]

    # Get activities
    c.execute("""
        SELECT activity, amount, carbon_emission, base_points, bonus_points, total_points, date
        FROM activities
        WHERE username=?
        ORDER BY date DESC
    """, (username,))
    activities = c.fetchall()
    conn.close()

    return render_template("user_history.html", username=username, activities=activities)

# ---------- Logout ----------
@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

# ----------------- RUN SERVER -----------------
if __name__ == "__main__":
    print("🌱 EcoTrack Backend is running!")
    app.run(debug=True)
