-- Create the Airflow metadata database (TASK-058).
-- Runs on first PostgreSQL startup via /docker-entrypoint-initdb.d/.
-- Grants the platform user CREATEDB so airflow-init can manage its own DB.

CREATE DATABASE airflow;
ALTER USER platform CREATEDB;
GRANT ALL PRIVILEGES ON DATABASE airflow TO platform;
