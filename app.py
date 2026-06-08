import os
import uuid
import sqlite3
import requests

from flask import Flask, render_template, request, redirect, session, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = "secret123"
CORS(app)

from admin import admin_bp
app.register_blueprint(admin_bp, url_prefix="/admin")

# ---------------- FOLDERS ----------------
UPLOAD_FOLDER = "static/uploads"
GENERATED_FOLDER = "static/generated"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_FOLDER, exist_ok=True)

# ---------------- API ----------------
STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")
STABILITY_URL = "https://api.stability.ai/v2beta/stable-image/generate/core"

# ---------------- DB ----------------
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        email TEXT UNIQUE,
        password TEXT,
        is_admin INTEGER DEFAULT 0
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        image_url TEXT,
        description TEXT DEFAULT '',
        likes INTEGER DEFAULT 0,
        image_type TEXT DEFAULT 'user'
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image_id INTEGER,
        text TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        image_id INTEGER
    )""")

    conn.commit()
    conn.close()


init_db()

# ---------------- LOGIN ----------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? OR email=?",
            (username, username)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["is_admin"] = user["is_admin"]

            if user["is_admin"] == 1:
                return redirect(url_for("admin.admin_dashboard"))

            return redirect(url_for("index"))

        return "Invalid credentials ❌"

    return render_template("user/login.html")


# ---------------- SIGNUP ----------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]

        # 🔥 ADD THIS BACK
        is_admin = 1 if request.form.get("make_admin") == "on" else 0

        conn = get_db()

        exists = conn.execute(
            "SELECT * FROM users WHERE username=? OR email=?",
            (username, email)
        ).fetchone()

        if exists:
            return "User already exists ❌"

        conn.execute(
            "INSERT INTO users (username, email, password, is_admin) VALUES (?, ?, ?, ?)",
            (username, email, generate_password_hash(password), is_admin)
        )

        conn.commit()
        conn.close()

        return redirect(url_for("login"))

    return render_template("user/signup.html")

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------- INDEX ----------------
@app.route("/index")
def index():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("user/index.html")


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    conn = get_db()

    user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()

    images = conn.execute("SELECT * FROM images WHERE user_id=?", (session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "user/profile.html",
        user=user,
        images=images,
        total_posts=len(images),
        total_likes=sum(i["likes"] for i in images)
    )


# ---------------- UPLOAD ----------------
@app.route("/upload", methods=["GET", "POST"])
def upload():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("user/upload.html")

    file = request.files.get("image")
    description = request.form.get("description", "")

    if not file:
        return "No file selected ❌"

    filename = secure_filename(file.filename)
    unique = f"{uuid.uuid4()}_{filename}"
    path = os.path.join(UPLOAD_FOLDER, unique)

    file.save(path)

    db_path = f"/static/uploads/{unique}"

    conn = get_db()
    conn.execute(
        "INSERT INTO images (user_id, image_url, description, image_type) VALUES (?, ?, ?, 'user')",
        (session["user_id"], db_path, description)
    )
    conn.commit()
    conn.close()

    return redirect(url_for("gallery"))


# ---------------- AI GENERATE ----------------
@app.route("/generate", methods=["GET", "POST"])
def generate():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    error = None
    image_url = None

    if request.method == "POST":
        prompt = request.form.get("prompt")

        if not prompt:
            error = "Prompt required ❌"

        elif not STABILITY_API_KEY:
            error = "API key missing ❌"

        else:
            response = requests.post(
                STABILITY_URL,
                headers={
                    "Authorization": f"Bearer {STABILITY_API_KEY}",
                    "Accept": "image/*"
                },
                files={
                    "prompt": (None, prompt),
                    "output_format": (None, "webp")
                },
                timeout=60
            )

            if response.status_code == 200:
                filename = f"{uuid.uuid4()}.webp"
                filepath = os.path.join(GENERATED_FOLDER, filename)

                with open(filepath, "wb") as f:
                    f.write(response.content)

                image_url = f"/static/generated/{filename}"

                conn = get_db()
                conn.execute(
                    "INSERT INTO images (user_id, image_url, description, image_type) VALUES (?, ?, ?, 'ai')",
                    (session["user_id"], image_url, prompt)
                )
                conn.commit()
                conn.close()

            else:
                error = response.text

    return render_template("user/generate.html", error=error, image_url=image_url)


# ---------------- GALLERY ----------------
@app.route("/gallery")
def gallery():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    conn = get_db()

    images = conn.execute("""
        SELECT images.*, users.username
        FROM images
        JOIN users ON images.user_id = users.id
        ORDER BY images.id DESC
    """).fetchall()

    conn.close()

    return render_template("user/gallery.html", images=images)


# ---------------- LIKE ----------------
@app.route("/like/<int:image_id>")
def like(image_id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    conn = get_db()

    exists = conn.execute(
        "SELECT * FROM likes WHERE user_id=? AND image_id=?",
        (session["user_id"], image_id)
    ).fetchone()

    if not exists:
        conn.execute("INSERT INTO likes (user_id, image_id) VALUES (?, ?)",
                     (session["user_id"], image_id))

        conn.execute("UPDATE images SET likes = likes + 1 WHERE id=?",
                     (image_id,))

    conn.commit()
    conn.close()

    return redirect(url_for("gallery"))


# ---------------- COMMENT ----------------
@app.route("/comment/<int:image_id>", methods=["POST"])
def comment(image_id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    text = request.form.get("comment")

    conn = get_db()
    conn.execute("INSERT INTO comments (image_id, text) VALUES (?, ?)",
                 (image_id, text))
    conn.commit()
    conn.close()

    return redirect(url_for("gallery"))


# ---------------- DELETE (FIXED) ----------------
@app.route("/delete/<int:image_id>", methods=["GET"])
def delete_image(image_id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    conn = get_db()

    img = conn.execute("SELECT * FROM images WHERE id=?", (image_id,)).fetchone()

    if not img:
        return "Not found ❌"

    if img["user_id"] != session["user_id"] and session.get("is_admin") != 1:
        return "Not allowed ❌"

    conn.execute("DELETE FROM images WHERE id=?", (image_id,))
    conn.execute("DELETE FROM likes WHERE image_id=?", (image_id,))
    conn.execute("DELETE FROM comments WHERE image_id=?", (image_id,))

    conn.commit()
    conn.close()

    return redirect(url_for("gallery"))


# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True, port=5001)