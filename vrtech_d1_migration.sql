-- VR Tech Solutions: MySQL 8.0.44 -> Cloudflare D1 (SQLite)
-- Converted from the supplied Dump20261029.sql.
-- Import into the EMPTY D1 database named vrtech-db.
-- Existing MySQL backup is not modified.

-- Create referenced parent table before job_applications.
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    slug TEXT NOT NULL,
    department TEXT,
    location TEXT,
    employment_type TEXT,
    experience TEXT,
    salary_range TEXT,
    short_description TEXT,
    description TEXT,
    requirements TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    closing_date TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_jobs_slug UNIQUE (slug)
);

CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_admins_username UNIQUE (username),
    CONSTRAINT uq_admins_email UNIQUE (email)
);

CREATE TABLE IF NOT EXISTS contact_enquiries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    company TEXT,
    subject TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    admin_notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    current_location TEXT NOT NULL,
    experience TEXT,
    cover_letter TEXT,
    resume_filename TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    admin_notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_job_applications_job
        FOREIGN KEY (job_id) REFERENCES jobs(id)
        ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    slug TEXT NOT NULL,
    category TEXT,
    short_description TEXT,
    description TEXT,
    image_url TEXT,
    project_url TEXT,
    technologies TEXT,
    is_featured INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_projects_slug UNIQUE (slug)
);

CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    slug TEXT NOT NULL,
    short_description TEXT NOT NULL,
    description TEXT NOT NULL,
    icon TEXT,
    image_url TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_services_slug UNIQUE (slug)
);

CREATE TABLE IF NOT EXISTS site_settings (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes converted from the MySQL dump.
CREATE INDEX IF NOT EXISTS idx_enquiries_status ON contact_enquiries(status);
CREATE INDEX IF NOT EXISTS idx_enquiries_created ON contact_enquiries(created_at);
CREATE INDEX IF NOT EXISTS idx_enquiries_email ON contact_enquiries(email);
CREATE INDEX IF NOT EXISTS idx_applications_job ON job_applications(job_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON job_applications(status);
CREATE INDEX IF NOT EXISTS idx_applications_created ON job_applications(created_at);
CREATE INDEX IF NOT EXISTS idx_applications_email ON job_applications(email);
CREATE INDEX IF NOT EXISTS idx_jobs_active ON jobs(is_active);
CREATE INDEX IF NOT EXISTS idx_jobs_closing_date ON jobs(closing_date);
CREATE INDEX IF NOT EXISTS idx_projects_active ON projects(is_active);
CREATE INDEX IF NOT EXISTS idx_projects_featured ON projects(is_featured);
CREATE INDEX IF NOT EXISTS idx_projects_display_order ON projects(display_order);
CREATE INDEX IF NOT EXISTS idx_services_active_order ON services(is_active, display_order);

-- Existing records from the supplied MySQL dump.
INSERT OR IGNORE INTO admins
    (id, username, email, password_hash, is_active, created_at)
VALUES
    (1, 'Rishivarun', 'rishivarun@gmail.com',
     'scrypt:32768:8:1$JF6hxjEGqdEFRq4d$f12bf6668bc3ae1d45b0f3bcd6645a2cefec8e3aac5d1b1c5087b148a58a121273744355d9e771accc828354d452f95ca3ff6a8020a454ddd49771f88820f232',
     1, '2026-10-29 14:10:19');

INSERT OR IGNORE INTO contact_enquiries
    (id, name, email, phone, company, subject, message, status, admin_notes, created_at, updated_at)
VALUES
    (1, 'raju', 'tata123@gmail.com', NULL, NULL, 'Artificial intelligence',
     'ai project', 'replied', '', '2026-10-29 14:12:49', '2026-10-29 14:13:06');

INSERT OR IGNORE INTO site_settings (key, value, updated_at)
VALUES ('funding_secured', '00', '2026-10-29 14:13:14');

-- Verify after import with:
-- SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name;
-- SELECT 'admins' AS table_name, COUNT(*) AS records FROM admins
-- UNION ALL SELECT 'contact_enquiries', COUNT(*) FROM contact_enquiries
-- UNION ALL SELECT 'job_applications', COUNT(*) FROM job_applications
-- UNION ALL SELECT 'jobs', COUNT(*) FROM jobs
-- UNION ALL SELECT 'projects', COUNT(*) FROM projects
-- UNION ALL SELECT 'services', COUNT(*) FROM services
-- UNION ALL SELECT 'site_settings', COUNT(*) FROM site_settings;
