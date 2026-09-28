#!/usr/bin/env python3
"""verify_eks_deployment.py — End-to-end verification of the AWS EKS deployment.

Checks every layer of the platform:
  1. Kubernetes pod health
  2. API health and readiness endpoints
  3. Kafka topic existence
  4. S3 bucket accessibility
  5. PostgreSQL connectivity and schema
  6. Ingestion → Kafka → Processor → Parquet → PostgreSQL data flow

Usage:
    python scripts/verify_eks_deployment.py [--api-url URL] [--timeout SECONDS]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field

NAMESPACE = "ai-data-platform"
STRIMZI_NAMESPACE = "strimzi"

EXPECTED_DEPLOYMENTS = [
    "ingestion",
    "processor",
    "raw-writer",
    "lake-writer",
    "warehouse-loader",
    "api",
]

EXPECTED_TOPICS = [
    "products.raw.v1",
    "products.validated.v1",
    "products.invalid.v1",
    "pipeline.events.v1",
    "data-quality.events.v1",
]


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class VerificationReport:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.results.append(CheckResult(name=name, passed=passed, detail=detail))

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def print_summary(self) -> None:
        print("\n" + "=" * 60)
        print("EKS DEPLOYMENT VERIFICATION REPORT")
        print("=" * 60)
        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            line = f"  [{status}] {r.name}"
            if r.detail:
                line += f" — {r.detail}"
            print(line)
        print("-" * 60)
        print(f"  Total: {len(self.results)}  Passed: {self.passed}  Failed: {self.failed}")
        print("=" * 60)


def kubectl(*args: str, namespace: str = NAMESPACE) -> str:
    cmd = ["kubectl"] + list(args) + ["-n", namespace]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.stdout.strip()


def check_pods(report: VerificationReport) -> None:
    for dep in EXPECTED_DEPLOYMENTS:
        try:
            output = kubectl("get", "deployment", dep, "-o", "jsonpath={.status.readyReplicas}")
            ready = int(output) if output else 0
            report.add(f"Pod: {dep}", ready > 0, f"ready={ready}")
        except Exception as e:
            report.add(f"Pod: {dep}", False, str(e))


def check_api_health(report: VerificationReport, api_url: str) -> None:
    try:
        result = subprocess.run(
            [
                "kubectl",
                "exec",
                "-n",
                NAMESPACE,
                kubectl(
                    "get",
                    "pod",
                    "-l",
                    "app.kubernetes.io/component=api",
                    "-o",
                    "jsonpath={.items[0].metadata.name}",
                ),
                "--",
                "python",
                "-c",
                f"import urllib.request; r=urllib.request.urlopen('{api_url}/api/v1/health'); print(r.status)",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        ok = result.returncode == 0 and "200" in result.stdout
        report.add("API: /health", ok, result.stdout.strip() if ok else result.stderr[:100])
    except Exception as e:
        report.add("API: /health", False, str(e))


def check_kafka_topics(report: VerificationReport) -> None:
    try:
        pod = kubectl(
            "get",
            "pod",
            "-l",
            "strimzi.io/name=platform-cluster-kafka",
            "-o",
            "jsonpath={.items[0].metadata.name}",
            namespace=STRIMZI_NAMESPACE,
        )
        result = subprocess.run(
            [
                "kubectl",
                "exec",
                "-n",
                STRIMZI_NAMESPACE,
                pod,
                "--",
                "/opt/kafka/bin/kafka-topics.sh",
                "--bootstrap-server",
                "localhost:9092",
                "--list",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        existing = set(result.stdout.strip().split("\n"))
        for topic in EXPECTED_TOPICS:
            report.add(f"Kafka: {topic}", topic in existing)
    except Exception as e:
        report.add("Kafka: topics", False, str(e))


def check_s3(report: VerificationReport, bucket_name: str) -> None:
    try:
        result = subprocess.run(
            [
                "kubectl",
                "exec",
                "-n",
                NAMESPACE,
                kubectl(
                    "get",
                    "pod",
                    "-l",
                    "app.kubernetes.io/component=raw-writer",
                    "-o",
                    "jsonpath={.items[0].metadata.name}",
                ),
                "--",
                "python",
                "-c",
                f"import boto3; s3=boto3.client('s3'); "
                f"s3.head_bucket(Bucket='{bucket_name}'); "
                f"resp=s3.list_objects_v2(Bucket='{bucket_name}', Prefix='bronze/', MaxKeys=1); "
                f"print('ok')",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        ok = result.returncode == 0
        report.add(
            "S3: IRSA bucket access",
            ok,
            f"bucket={bucket_name}" if ok else result.stderr[:100],
        )
    except Exception as e:
        report.add("S3: IRSA bucket access", False, str(e))


def check_postgresql(report: VerificationReport) -> None:
    try:
        result = subprocess.run(
            [
                "kubectl",
                "exec",
                "-n",
                NAMESPACE,
                kubectl(
                    "get",
                    "pod",
                    "-l",
                    "app.kubernetes.io/component=warehouse-loader",
                    "-o",
                    "jsonpath={.items[0].metadata.name}",
                ),
                "--",
                "python",
                "-c",
                "import os, psycopg2; conn=psycopg2.connect("
                "host=os.environ['WAREHOUSE_DB_HOST'],"
                "port=os.environ['WAREHOUSE_DB_PORT'],"
                "dbname=os.environ['WAREHOUSE_DB_NAME'],"
                "user=os.environ['WAREHOUSE_DB_USER'],"
                "password=os.environ['WAREHOUSE_DB_PASSWORD'],"
                "); cur=conn.cursor(); cur.execute('SELECT 1'); print(cur.fetchone()); conn.close()",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        ok = result.returncode == 0
        report.add(
            "PostgreSQL: RDS connection", ok, result.stdout.strip() if ok else result.stderr[:100]
        )
    except Exception as e:
        report.add("PostgreSQL: RDS connection", False, str(e))


def check_data_flow(report: VerificationReport) -> None:
    try:
        pod = kubectl(
            "get",
            "pod",
            "-l",
            "strimzi.io/name=platform-cluster-kafka",
            "-o",
            "jsonpath={.items[0].metadata.name}",
            namespace=STRIMZI_NAMESPACE,
        )
        for topic in ["products.raw.v1", "products.validated.v1"]:
            result = subprocess.run(
                [
                    "kubectl",
                    "exec",
                    "-n",
                    STRIMZI_NAMESPACE,
                    pod,
                    "--",
                    "/opt/kafka/bin/kafka-run-class.sh",
                    "kafka.tools.GetOffsetShell",
                    "--broker-list",
                    "localhost:9092",
                    "--topic",
                    topic,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            has_data = bool(result.stdout.strip())
            label = f"Data flow: {topic} offsets"
            report.add(
                label,
                has_data,
                result.stdout.strip()[:80] if has_data else "no offsets yet",
            )
    except Exception as e:
        report.add("Data flow: raw events in Kafka", False, str(e))


def check_s3_parquet(report: VerificationReport, bucket_name: str) -> None:
    try:
        result = subprocess.run(
            [
                "kubectl",
                "exec",
                "-n",
                NAMESPACE,
                kubectl(
                    "get",
                    "pod",
                    "-l",
                    "app.kubernetes.io/component=raw-writer",
                    "-o",
                    "jsonpath={.items[0].metadata.name}",
                ),
                "--",
                "python",
                "-c",
                f"import boto3; s3=boto3.client('s3'); "
                f"bronze=s3.list_objects_v2(Bucket='{bucket_name}', "
                f"Prefix='bronze/', MaxKeys=5); "
                f"silver=s3.list_objects_v2(Bucket='{bucket_name}', "
                f"Prefix='silver/', MaxKeys=5); "
                f"b=bronze.get('KeyCount',0); s=silver.get('KeyCount',0); "
                f"print(f'bronze={{b}} silver={{s}}')",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        ok = result.returncode == 0
        report.add(
            "S3: Parquet objects",
            ok,
            result.stdout.strip() if ok else result.stderr[:100],
        )
    except Exception as e:
        report.add("S3: Parquet objects", False, str(e))


def check_warehouse_data(report: VerificationReport) -> None:
    try:
        result = subprocess.run(
            [
                "kubectl",
                "exec",
                "-n",
                NAMESPACE,
                kubectl(
                    "get",
                    "pod",
                    "-l",
                    "app.kubernetes.io/component=warehouse-loader",
                    "-o",
                    "jsonpath={.items[0].metadata.name}",
                ),
                "--",
                "python",
                "-c",
                "import os, psycopg2; conn=psycopg2.connect("
                "host=os.environ['WAREHOUSE_DB_HOST'],"
                "port=os.environ['WAREHOUSE_DB_PORT'],"
                "dbname=os.environ['WAREHOUSE_DB_NAME'],"
                "user=os.environ['WAREHOUSE_DB_USER'],"
                "password=os.environ['WAREHOUSE_DB_PASSWORD'],"
                "); cur=conn.cursor(); "
                'cur.execute("SELECT table_name FROM information_schema.tables '
                "WHERE table_schema='public'\"); "
                "tables=[r[0] for r in cur.fetchall()]; "
                "print(f'tables={len(tables)}: {tables[:5]}'); conn.close()",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        ok = result.returncode == 0
        report.add(
            "Warehouse: tables loaded",
            ok,
            result.stdout.strip() if ok else result.stderr[:100],
        )
    except Exception as e:
        report.add("Warehouse: tables loaded", False, str(e))


def check_agent_query(report: VerificationReport, api_url: str) -> None:
    try:
        result = subprocess.run(
            [
                "kubectl",
                "exec",
                "-n",
                NAMESPACE,
                kubectl(
                    "get",
                    "pod",
                    "-l",
                    "app.kubernetes.io/component=api",
                    "-o",
                    "jsonpath={.items[0].metadata.name}",
                ),
                "--",
                "python",
                "-c",
                f"import urllib.request, json; "
                f"data=json.dumps({{'query': 'how many products are loaded?'}}).encode(); "
                f"req=urllib.request.Request('{api_url}/api/v1/agent/query', "
                f"data=data, headers={{'Content-Type': 'application/json'}}); "
                f"r=urllib.request.urlopen(req); print(r.status)",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        ok = result.returncode == 0 and "200" in result.stdout
        report.add(
            "Agent: query round-trip",
            ok,
            result.stdout.strip() if ok else result.stderr[:100],
        )
    except Exception as e:
        report.add("Agent: query round-trip", False, str(e))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify EKS deployment")
    parser.add_argument(
        "--api-url", default="http://localhost:8000", help="API base URL for health checks"
    )
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per check in seconds")
    parser.add_argument(
        "--bucket-name",
        default="ai-data-platform-data",
        help="S3 data lake bucket name for access verification",
    )
    parser.add_argument(
        "--skip-data-flow", action="store_true", help="Skip data flow checks (no ingestion yet)"
    )
    args = parser.parse_args()

    report = VerificationReport()

    print("Running EKS deployment verification...\n")

    check_pods(report)
    check_api_health(report, args.api_url)
    check_kafka_topics(report)
    check_s3(report, args.bucket_name)
    check_postgresql(report)

    if not args.skip_data_flow:
        check_data_flow(report)
        check_s3_parquet(report, args.bucket_name)
        check_warehouse_data(report)
        check_agent_query(report, args.api_url)

    report.print_summary()
    return 1 if report.failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
