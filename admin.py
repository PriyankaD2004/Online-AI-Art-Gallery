from flask import Blueprint, render_template, session, redirect, url_for
import sqlite3

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ---------------- DB ----------------
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


# ---------------- ADMIN CHECK ----------------
def is_admin():
    return int(session.get("is_admin", 0)) == 1


# ---------------- DASHBOARD ----------------
@admin_bp.route("/")
def admin_dashboard():
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()

    users = conn.execute("SELECT * FROM users").fetchall()
    images = conn.execute("SELECT * FROM images").fetchall()
    comments = conn.execute("SELECT * FROM comments").fetchall()

    conn.close()

    stats = {
        "total_users": len(users),
        "total_images": len(images),
        "total_comments": len(comments)
    }

    # ✅ FIX: provide missing variables used in template
    ai_user_data = {
        "ai": [len(images)],      # AI images (you can refine later)
        "user": [len(images)]     # placeholder (same for now)
    }

    chart_labels = ["Users", "Images", "Comments"]
    chart_data = [stats["total_users"], stats["total_images"], stats["total_comments"]]

    return render_template(
        "admin/dashboard.html",
        users=users,
        images=images,
        comments=comments,
        stats=stats,
        ai_user_data=ai_user_data,
        chart_labels=chart_labels,
        chart_data=chart_data
    )


# ---------------- DELETE IMAGE ----------------
@admin_bp.route("/delete_image/<int:id>")
def delete_image(id):
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute("DELETE FROM images WHERE id=?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for("admin.admin_dashboard"))


# ---------------- DELETE USER ----------------
@admin_bp.route("/delete_user/<int:id>")
def delete_user(id):
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for("admin.admin_dashboard"))


# ---------------- DELETE COMMENT ----------------
@admin_bp.route("/delete_comment/<int:id>")
def delete_comment(id):
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute("DELETE FROM comments WHERE id=?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for("admin.admin_dashboard"))