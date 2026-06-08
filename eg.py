import os
import uuid
import sqlite3
import requests

from flask import Flask, render_template, request, redirect, session, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# ---------------- SETUP ----------------
load_dotenv()

app = Flask(__name__)
app.secret_key = "secret123"
CORS(app)

UPLOAD_FOLDER = "static/uploads"
GENERATED_FOLDER = "static/generated"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

# ---------------- STABILITY AI ----------------
STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")
STABILITY_URL = "https://api.stability.ai/v2beta/stable-image/generate/core"

if not STABILITY_API_KEY:
    print("⚠️ WARNING: STABILITY_API_KEY not found in .env")


# ---------------- DATABASE ----------------
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        email TEXT UNIQUE,
        password TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        image_url TEXT,
        description TEXT DEFAULT '',
        is_for_sale INTEGER DEFAULT 0,
        contact TEXT DEFAULT '',
        likes INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image_id INTEGER,
        text TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        image_id INTEGER
    )
    """)

    conn.commit()
    conn.close()

init_db()


# ---------------- HELPERS ----------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


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

        conn = get_db()

        exists = conn.execute(
            "SELECT * FROM users WHERE username=? OR email=?",
            (username, email)
        ).fetchone()

        if exists:
            return "User already exists ❌"

        conn.execute(
            "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
            (username, email, generate_password_hash(password))
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


# ---------------- GENERATE IMAGE ----------------
@app.route("/generate", methods=["GET", "POST"])
def generate():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    error = None

    if request.method == "POST":
        prompt = request.form.get("prompt")

        if not prompt:
            error = "Prompt required ❌"

        elif not STABILITY_API_KEY:
            error = "API key missing ❌"

        else:
            try:
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

                    image_url = url_for('static', filename=f'generated/{filename}')

                    conn = get_db()
                    conn.execute(
                        "INSERT INTO images (user_id, image_url, description) VALUES (?, ?, ?)",
                        (session["user_id"], image_url, prompt)
                    )
                    conn.commit()
                    conn.close()

                    return redirect(url_for("gallery"))

                else:
                    error = response.text

            except Exception as e:
                error = str(e)

    return render_template("user/generate.html", error=error)


# ---------------- UPLOAD ----------------
@app.route("/upload", methods=["GET", "POST"])
def upload():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("user/upload.html")

    file = request.files.get("image")
    description = request.form.get("description", "")

    if not file or file.filename == "":
        return "No file selected ❌"

    if not allowed_file(file.filename):
        return "Invalid file type ❌"

    if not description:
        return "Description required ❌"

    filename = secure_filename(file.filename)
    unique_name = f"{uuid.uuid4()}_{filename}"

    filepath = os.path.join(UPLOAD_FOLDER, unique_name)
    file.save(filepath)

    db_path = f"/static/uploads/{unique_name}"

    conn = get_db()
    conn.execute(
        "INSERT INTO images (user_id, image_url, description) VALUES (?, ?, ?)",
        (session["user_id"], db_path, description)
    )
    conn.commit()
    conn.close()

    return redirect(url_for("gallery"))

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

    image_list = []

    for img in images:
        comments = conn.execute(
            "SELECT * FROM comments WHERE image_id=? ORDER BY id DESC",
            (img["id"],)
        ).fetchall()

        img_dict = dict(img)
        img_dict["comments"] = comments

        image_list.append(img_dict)

    conn.close()

    return render_template("user/gallery.html", images=image_list)


# ---------------- PROFILE ----------------
@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    conn = get_db()

    user = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (session["user_id"],)
    ).fetchone()

    images = conn.execute(
        "SELECT * FROM images WHERE user_id=?",
        (session["user_id"],)
    ).fetchall()

    conn.close()

    return render_template("user/profile.html",
                           user=user,
                           images=images,
                           total_posts=len(images),
                           total_likes=sum(i["likes"] for i in images))

# ---------------- LIKE ----------------
@app.route("/like/<int:image_id>")
def like(image_id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    conn = get_db()
    user_id = session["user_id"]

    # check if already liked
    existing = conn.execute(
        "SELECT * FROM likes WHERE user_id=? AND image_id=?",
        (user_id, image_id)
    ).fetchone()

    if existing:
        # UNLIKE
        conn.execute(
            "DELETE FROM likes WHERE user_id=? AND image_id=?",
            (user_id, image_id)
        )

        conn.execute(
            "UPDATE images SET likes = likes - 1 WHERE id=?",
            (image_id,)
        )
    else:
        # LIKE
        conn.execute(
            "INSERT INTO likes (user_id, image_id) VALUES (?, ?)",
            (user_id, image_id)
        )

        conn.execute(
            "UPDATE images SET likes = likes + 1 WHERE id=?",
            (image_id,)
        )

    conn.commit()
    conn.close()

    return redirect(url_for("gallery"))

# ---------------- COMMENT ----------------
@app.route("/comment/<int:image_id>", methods=["POST"])
def comment(image_id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    text = request.form.get("comment")

    if not text:
        return redirect(url_for("gallery"))

    conn = get_db()

    conn.execute(
        "INSERT INTO comments (image_id, text) VALUES (?, ?)",
        (image_id, text)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("gallery"))

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True, port=5001)