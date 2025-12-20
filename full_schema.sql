BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> bfc36cb480ac

INSERT INTO alembic_version (version_num) VALUES ('bfc36cb480ac') RETURNING alembic_version.version_num;

COMMIT;

