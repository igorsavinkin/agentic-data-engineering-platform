# Custom Airflow image for the AI Data Platform (TASK-134).
#
# Extends the stock Apache Airflow image with project DAG dependencies,
# DAG files, and project libs baked in at build time. This eliminates
# the need for runtime pip install or volume mounts.
#
# Build context: repository root.
#
# Usage:
#   docker build -f airflow/Dockerfile -t ai-data-platform/airflow:dev .
#
# The image includes:
#   - All Python packages required by project DAGs (polars, pydantic-settings,
#     boto3, psycopg2, prometheus-client, opentelemetry-*)
#   - Project libs/ at /opt/airflow/libs/ (imported by DAGs)
#   - Project DAGs at /opt/airflow/dags/

ARG AIRFLOW_VERSION=2.10.4
FROM apache/airflow:${AIRFLOW_VERSION}-python3.12

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/opt/airflow \
    AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/dags

USER airflow

COPY airflow/requirements.txt /tmp/airflow-requirements.txt
RUN pip install -r /tmp/airflow-requirements.txt

USER root

COPY --chown=airflow:root libs/ /opt/airflow/libs/
COPY --chown=airflow:root airflow/dags/ /opt/airflow/dags/

USER airflow
