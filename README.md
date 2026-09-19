# Complaint Resolution System — BDA AWS Assignment

A minimal 3-tier web app (Flask + MySQL on RDS + S3 for attachments), deployed on
a custom VPC, to demonstrate the full AWS networking + compute + storage workflow.

**Tech stack:** Python Flask, MySQL (Amazon RDS), Amazon S3, Bootstrap (CDN only, no build step).

---

## Architecture

```
                         Internet
                            |
                     [Internet Gateway]
                            |
                    Public Route Table
                            |
   VPC (10.0.0.0/16)  ──────────────────────────────
   │                                                │
   │   Public Subnet (10.0.1.0/24)                  │
   │   ┌─────────────────────────┐                  │
   │   │  EC2 (Flask App)        │◄── SSH (22)       │
   │   │  Security Group: web-sg │◄── HTTP (80/5000) │
   │   └───────────┬─────────────┘                  │
   │               │ SQL (3306)                     │
   │   Private Subnet(s) (10.0.2.0/24, 10.0.3.0/24) │
   │   ┌─────────────────────────┐                  │
   │   │  RDS MySQL               │                 │
   │   │  Security Group: db-sg   │                 │
   │   └─────────────────────────┘                  │
   └────────────────────────────────────────────────┘
                            │
                     Amazon S3 (attachments + dataset)
                     via IAM Role attached to EC2
```

---

## Step 1 – Create the VPC

1. AWS Console → **VPC** → **Your VPCs** → **Create VPC**.
2. Choose **VPC only**.
   - Name: `complaint-vpc`
   - IPv4 CIDR: `10.0.0.0/16`
3. Create.

## Step 2 – Create the Public Subnet

1. **VPC → Subnets → Create subnet**.
2. VPC: `complaint-vpc`
   - Name: `public-subnet`
   - AZ: e.g. `ap-south-1a`
   - CIDR: `10.0.1.0/24`
3. After creation, select it → **Actions → Edit subnet settings** → enable **Auto-assign public IPv4 address**.

## Step 3 – Create the Private Subnets

RDS requires **at least 2 subnets in 2 different AZs** (a "DB subnet group"), even for a single-AZ instance.

1. Create subnet: `private-subnet-1`, AZ `ap-south-1a`, CIDR `10.0.2.0/24`.
2. Create subnet: `private-subnet-2`, AZ `ap-south-1b`, CIDR `10.0.3.0/24`.
3. Leave auto-assign public IP **disabled** for both (they're private).

## Step 4 – Create Internet Gateway

1. **VPC → Internet Gateways → Create internet gateway**. Name: `complaint-igw`.
2. Select it → **Actions → Attach to VPC** → choose `complaint-vpc`.

## Step 5 – Configure Public Route Table

1. **VPC → Route Tables → Create route table**. Name: `public-rt`, VPC: `complaint-vpc`.
2. Select it → **Routes → Edit routes → Add route**:
   - Destination: `0.0.0.0/0`
   - Target: your Internet Gateway (`complaint-igw`)
3. **Subnet associations → Edit subnet associations** → associate `public-subnet`.

*(Private subnets stay on the default/main route table — no route to the internet gateway, so they're not internet-reachable. This is normal and correct for RDS.)*

## Step 6 – Create Security Groups

Create two:

**`web-sg`** (attached to EC2)
| Type | Port | Source |
|---|---|---|
| SSH | 22 | Your IP only (My IP) |
| HTTP | 80 | 0.0.0.0/0 |
| Custom TCP | 5000 | 0.0.0.0/0 *(Flask dev port, optional if you proxy via 80)* |

**`db-sg`** (attached to RDS)
| Type | Port | Source |
|---|---|---|
| MySQL/Aurora | 3306 | `web-sg` (select the security group, not an IP) |

This ensures only your EC2 instance can talk to the database — nothing else on the internet can.

## Step 7 – Launch EC2

1. **EC2 → Launch Instance**.
   - Name: `complaint-app-server`
   - AMI: **Ubuntu Server 22.04 LTS**
   - Instance type: `t2.micro` (free tier)
   - Key pair: create/download a new `.pem` key
   - Network: `complaint-vpc`, subnet: `public-subnet`, **Auto-assign public IP: Enable**
   - Security group: `web-sg`
2. Under **Advanced details → IAM instance profile**: leave blank for now — you'll attach the S3 role in Step 14 (or create it now if you want to do it in one shot; see Step 14).
3. Launch.

## Step 8 – Connect to EC2

From your local machine:

```bash
chmod 400 your-key.pem
ssh -i your-key.pem ubuntu@<EC2-PUBLIC-IP>
```

## Step 9 – Install Web Application

On the EC2 instance:

```bash
sudo apt update && sudo apt install -y python3-pip python3-venv git

# Get your code onto the instance — either scp it from your laptop or git clone it.
# Example using scp from your LOCAL machine (run this locally, not on EC2):
#   scp -i your-key.pem -r complaint-app ubuntu@<EC2-PUBLIC-IP>:~/

cd ~/complaint-app
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env   # fill in RDS_HOST, RDS_PASSWORD, S3_BUCKET etc. (do Steps 10 & 13 first, then come back)
```

## Step 10 – Create RDS Database

1. **RDS → Subnet groups → Create DB subnet group**:
   - Name: `complaint-db-subnet-group`
   - VPC: `complaint-vpc`
   - Add `private-subnet-1` and `private-subnet-2`
2. **RDS → Databases → Create database**:
   - Engine: **MySQL** (8.0)
   - Template: **Free tier**
   - DB instance identifier: `complaint-db`
   - Master username: `admin`, set a master password (save it)
   - Instance class: `db.t3.micro`
   - VPC: `complaint-vpc`
   - DB subnet group: `complaint-db-subnet-group`
   - Public access: **No**
   - VPC security group: `db-sg`
3. Create. Wait ~5–10 min for status **Available**.
4. Copy the **Endpoint** (e.g. `complaint-db.xxxx.ap-south-1.rds.amazonaws.com`) into your `.env` as `RDS_HOST`.

## Step 11 – Connect EC2 to RDS

On the EC2 instance:

```bash
sudo apt install -y mysql-client
mysql -h <RDS_ENDPOINT> -u admin -p
```

If this connects, your security groups and subnet routing are correct. Type `exit` to leave the MySQL prompt.

## Step 12 – Create Database

Still connected (or reconnect), run the schema:

```bash
mysql -h <RDS_ENDPOINT> -u admin -p < schema.sql
```

This creates the `complaint_db` database and the `complaints` table, with a few seed rows.

## Step 13 – Create S3 Bucket

1. **S3 → Create bucket**.
   - Name: something globally unique, e.g. `complaint-app-<yourname>-2026`
   - Region: same as your EC2/RDS (e.g. `ap-south-1`)
   - Block all public access: **keep this ON** (we'll serve files via presigned/direct HTTPS URLs; for a class demo you *can* turn this off and add a public-read bucket policy if you want direct links to work without extra code — see note below)
2. Create.
3. Put the bucket name into `.env` as `S3_BUCKET`.

> **Note on public access:** The app builds direct S3 URLs (`https://bucket.s3.region.amazonaws.com/key`) for simplicity. For those links to open in a browser, either (a) uncheck "Block all public access" and add a bucket policy allowing `s3:GetObject` on `arn:aws:s3:::your-bucket/*`, or (b) keep it private and just demonstrate upload success in the DB record (perfectly fine for grading — the point is the EC2→S3 integration via IAM role).

## Step 14 – Give EC2 Access to S3

Don't use access keys in code — use an **IAM Role** attached to the EC2 instance.

1. **IAM → Roles → Create role**.
   - Trusted entity: **AWS service → EC2**
   - Permissions: attach `AmazonS3FullAccess` (for the assignment; in real life you'd scope this to just your bucket)
   - Name: `EC2-S3-Access-Role`
2. **EC2 → select your instance → Actions → Security → Modify IAM role** → attach `EC2-S3-Access-Role`.
3. No code changes needed — `boto3` automatically picks up credentials from the instance's role.

## Step 15 – Upload Dataset to S3

This demonstrates bulk/dataset ingestion into your data lake layer.

From your EC2 instance (after `aws configure` isn't even needed since you have the IAM role):

```bash
sudo apt install -y awscli
aws s3 cp sample_dataset/historical_complaints.csv s3://<your-bucket-name>/datasets/historical_complaints.csv
aws s3 ls s3://<your-bucket-name>/datasets/
```

This CSV represents a "historical complaints" dataset — you can reference it in your report as the raw data lake input, separate from the live attachments users upload through the app (which land under `attachments/`).

## Step 16 – Application Workflow

Now bring it all together.

```bash
cd ~/complaint-app
source venv/bin/activate
python3 app.py
```

Visit `http://<EC2-PUBLIC-IP>:5000` in your browser.

**End-to-end flow:**
1. User opens the site → submits a complaint (name, email, category, description, optional file).
2. Flask app on EC2 inserts the complaint row into **RDS MySQL** (private subnet).
3. If a file was attached, Flask uploads it to **S3** using the EC2 IAM role, and stores the S3 key in the DB row.
4. User can check status anytime at `/status` using their Complaint ID.
5. Admin visits `/admin` to see all complaints (pulled from RDS) and update status (Pending → In Progress → Resolved).
6. The `historical_complaints.csv` dataset in S3 represents bulk/legacy data you could later load into RDS with a script, for analytics.

### (Optional) Running as a proper background service with Nginx + Gunicorn

For a more "production" demo instead of the Flask dev server:

```bash
pip install gunicorn
gunicorn -w 2 -b 127.0.0.1:8000 app:app --daemon

sudo apt install -y nginx
sudo tee /etc/nginx/sites-available/complaint-app <<'EOF'
server {
    listen 80;
    server_name _;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF
sudo ln -s /etc/nginx/sites-available/complaint-app /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo systemctl restart nginx
```

Now the app is reachable on plain `http://<EC2-PUBLIC-IP>` (port 80).

---

## File Structure

```
complaint-app/
├── app.py                  # Flask application (all routes)
├── requirements.txt        # Python dependencies
├── schema.sql              # MySQL table + seed data
├── .env.example            # Config template (copy to .env on EC2)
├── sample_dataset/
│   └── historical_complaints.csv   # Dataset for Step 15 (S3 upload)
├── static/
│   └── style.css
└── templates/
    ├── base.html
    ├── index.html           # Complaint submission form
    ├── status.html          # Public status lookup
    └── complaints.html      # Admin dashboard
```

## Troubleshooting

- **Can't connect to RDS from EC2:** check `db-sg` inbound rule allows port 3306 from `web-sg` (as a security group source, not an IP). Also confirm both are in the same VPC.
- **S3 upload fails / AccessDenied:** confirm the IAM role is attached to the *instance* (Step 14) and the bucket name in `.env` matches exactly.
- **Site not loading in browser:** check `web-sg` allows inbound on the port you're using (5000 or 80), and that you're using the EC2's **public** IP.
- **`ModuleNotFoundError`:** make sure you activated the venv (`source venv/bin/activate`) before running `pip install` / `python3 app.py`.
