import os
import uuid
from datetime import datetime

import boto3
import pymysql
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")

# ---------- Config (from .env) ----------
DB_HOST = os.getenv("RDS_HOST")
DB_USER = os.getenv("RDS_USER")
DB_PASSWORD = os.getenv("RDS_PASSWORD")
DB_NAME = os.getenv("RDS_DB", "complaint_db")

S3_BUCKET = os.getenv("S3_BUCKET")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

# boto3 will automatically use the EC2 instance's IAM Role credentials
# (no access keys needed if launched with the right IAM role attached)
s3_client = boto3.client("s3", region_name=AWS_REGION)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf", "docx", "txt"}
CATEGORIES = ["Billing", "Product Quality", "Delivery", "Customer Service", "Technical Issue", "Other"]


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_db_connection():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
    )


def upload_to_s3(file_obj, filename):
    """Uploads a file object to S3 and returns the object key (path)."""
    unique_name = f"attachments/{uuid.uuid4().hex}_{filename}"
    s3_client.upload_fileobj(
        file_obj,
        S3_BUCKET,
        unique_name,
        ExtraArgs={"ContentType": file_obj.content_type},
    )
    return unique_name


def get_s3_url(key):
    if not key:
        return None
    return f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{key}"


# ---------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html", categories=CATEGORIES)


@app.route("/submit", methods=["POST"])
def submit_complaint():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    file = request.files.get("attachment")

    if not (name and email and category and description):
        flash("Please fill in all required fields.", "danger")
        return redirect(url_for("home"))

    attachment_key = None
    if file and file.filename:
        if allowed_file(file.filename):
            attachment_key = upload_to_s3(file, file.filename)
        else:
            flash("Attachment type not allowed. Allowed: png, jpg, jpeg, pdf, docx, txt.", "warning")

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO complaints (name, email, category, description, attachment_key, status)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (name, email, category, description, attachment_key, "Pending"),
            )
            conn.commit()
            complaint_id = cur.lastrowid
    finally:
        conn.close()

    flash(f"Complaint submitted successfully! Your Complaint ID is #{complaint_id}. Save it to track status.", "success")
    return redirect(url_for("home"))


@app.route("/status", methods=["GET", "POST"])
def check_status():
    complaint = None
    if request.method == "POST":
        complaint_id = request.form.get("complaint_id")
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM complaints WHERE id=%s", (complaint_id,))
                complaint = cur.fetchone()
                if complaint and complaint.get("attachment_key"):
                    complaint["attachment_url"] = get_s3_url(complaint["attachment_key"])
        finally:
            conn.close()
        if not complaint:
            flash("No complaint found with that ID.", "warning")
    return render_template("status.html", complaint=complaint)


@app.route("/admin")
def admin_dashboard():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM complaints ORDER BY created_at DESC")
            complaints = cur.fetchall()
            for c in complaints:
                c["attachment_url"] = get_s3_url(c.get("attachment_key"))
    finally:
        conn.close()
    return render_template("complaints.html", complaints=complaints)


@app.route("/admin/update/<int:complaint_id>", methods=["POST"])
def update_status(complaint_id):
    new_status = request.form.get("status")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE complaints SET status=%s WHERE id=%s", (new_status, complaint_id))
            conn.commit()
    finally:
        conn.close()
    flash(f"Complaint #{complaint_id} updated to '{new_status}'.", "success")
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    # For the assignment/demo this is fine. For a "production" feel on EC2,
    # run it behind gunicorn instead (see README).
    app.run(host="0.0.0.0", port=5000, debug=True)
