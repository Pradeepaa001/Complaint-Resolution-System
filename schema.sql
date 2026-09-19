-- Run this once, connected to your RDS MySQL instance
CREATE DATABASE IF NOT EXISTS complaint_db;
USE complaint_db;

CREATE TABLE IF NOT EXISTS complaints (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    email           VARCHAR(150) NOT NULL,
    category        VARCHAR(50)  NOT NULL,
    description     TEXT         NOT NULL,
    attachment_key  VARCHAR(500),
    status          VARCHAR(20)  DEFAULT 'Pending',
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- Optional: a few seed rows so your demo isn't empty on first run
INSERT INTO complaints (name, email, category, description, status) VALUES
('Ravi Kumar', 'ravi@example.com', 'Delivery', 'Package arrived 5 days late.', 'Pending'),
('Anita Sharma', 'anita@example.com', 'Billing', 'Charged twice for the same order.', 'In Progress'),
('John Mathew', 'john@example.com', 'Product Quality', 'Item received was damaged.', 'Resolved');
