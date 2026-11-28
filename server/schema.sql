-- Reference DDL for MySQL 8.4. Use Alembic for actual deployment.

CREATE TABLE universities (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	code VARCHAR(32) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (code)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE TABLE users (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	max_user_id BIGINT NOT NULL, 
	active BOOL NOT NULL, 
	owner BOOL NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (max_user_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE TABLE study_groups (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	university_id INTEGER NOT NULL, 
	slug VARCHAR(100) NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	term VARCHAR(32) NOT NULL, 
	public BOOL NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_group_term UNIQUE (university_id, code, term), 
	FOREIGN KEY(university_id) REFERENCES universities (id), 
	UNIQUE (slug)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE TABLE announcements (
	group_id INTEGER NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	payload JSON NOT NULL, 
	sort_order INTEGER NOT NULL, 
	PRIMARY KEY (group_id, code), 
	FOREIGN KEY(group_id) REFERENCES study_groups (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE TABLE group_snapshots (
	group_id INTEGER NOT NULL, 
	schedule_meta JSON NOT NULL, 
	content_meta JSON NOT NULL, 
	PRIMARY KEY (group_id), 
	FOREIGN KEY(group_id) REFERENCES study_groups (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE TABLE memberships (
	group_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	`role` VARCHAR(16) NOT NULL, 
	digit INTEGER, 
	PRIMARY KEY (group_id, user_id), 
	CONSTRAINT ck_member_role CHECK (role IN ('student','admin')), 
	CONSTRAINT ck_member_digit CHECK (digit IS NULL OR digit BETWEEN 0 AND 9), 
	FOREIGN KEY(group_id) REFERENCES study_groups (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE TABLE schedule_entries (
	group_id INTEGER NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	day DATE NOT NULL, 
	start VARCHAR(5) NOT NULL, 
	payload JSON NOT NULL, 
	sort_order INTEGER NOT NULL, 
	PRIMARY KEY (group_id, code), 
	FOREIGN KEY(group_id) REFERENCES study_groups (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;
CREATE INDEX ix_schedule_group_day ON schedule_entries (group_id, day, start);
CREATE TABLE subjects (
	group_id INTEGER NOT NULL, 
	code VARCHAR(32) NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	PRIMARY KEY (group_id, code), 
	FOREIGN KEY(group_id) REFERENCES study_groups (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE TABLE variants (
	group_id INTEGER NOT NULL, 
	task_number INTEGER NOT NULL, 
	variant_number INTEGER NOT NULL, 
	topic TEXT NOT NULL, 
	PRIMARY KEY (group_id, task_number, variant_number), 
	CONSTRAINT ck_variant_number CHECK (variant_number BETWEEN 1 AND 10), 
	CONSTRAINT ck_variant_task CHECK (task_number BETWEEN 1 AND 4), 
	FOREIGN KEY(group_id) REFERENCES study_groups (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE TABLE tasks (
	group_id INTEGER NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	subject_code VARCHAR(32) NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	description TEXT NOT NULL, 
	deadline DATE, 
	deadline_note TEXT NOT NULL, 
	source TEXT NOT NULL, 
	active BOOL NOT NULL, 
	sort_order INTEGER NOT NULL, 
	PRIMARY KEY (group_id, code), 
	CONSTRAINT fk_task_subject FOREIGN KEY(group_id, subject_code) REFERENCES subjects (group_id, code), 
	FOREIGN KEY(group_id) REFERENCES study_groups (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE TABLE progress (
	group_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	task_code VARCHAR(64) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	PRIMARY KEY (group_id, user_id, task_code), 
	CONSTRAINT fk_progress_member FOREIGN KEY(group_id, user_id) REFERENCES memberships (group_id, user_id), 
	CONSTRAINT fk_progress_task FOREIGN KEY(group_id, task_code) REFERENCES tasks (group_id, code), 
	CONSTRAINT ck_progress_status CHECK (status IN ('not_started','in_progress','prepared','checked','submitted','accepted','revise','not_required','clarify'))
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

-- 1.3.1 migration 0002_auth


CREATE TABLE auth_sessions (
    token_hash VARCHAR(64) NOT NULL, 
    user_id INTEGER NOT NULL, 
    expires_at BIGINT NOT NULL, 
    PRIMARY KEY (token_hash), 
    FOREIGN KEY(user_id) REFERENCES users (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE INDEX ix_auth_sessions_user_id ON auth_sessions (user_id);

CREATE INDEX ix_auth_sessions_expires_at ON auth_sessions (expires_at);

CREATE TABLE used_launches (
    signature VARCHAR(64) NOT NULL, 
    expires_at BIGINT NOT NULL, 
    PRIMARY KEY (signature)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE INDEX ix_used_launches_expires_at ON used_launches (expires_at);

CREATE TABLE audit_events (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    actor_id INTEGER NOT NULL, 
    group_id INTEGER NOT NULL, 
    action VARCHAR(32) NOT NULL, 
    object_code VARCHAR(64) NOT NULL, 
    occurred_at BIGINT NOT NULL, 
    details JSON NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(actor_id) REFERENCES users (id), 
    FOREIGN KEY(group_id) REFERENCES study_groups (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE INDEX ix_audit_group_id ON audit_events (group_id, id);

