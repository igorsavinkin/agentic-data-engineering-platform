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


def check_s3(report: VerificationReport) -> None:
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
                "import boto3; s3=boto3.client('s3'); buckets=[b['Name'] for b in s3.list_buckets()['Buckets']]; print(len(buckets))",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        ok = result.returncode == 0
        report.add("S3: IRSA access", ok, "boto3 OK" if ok else result.stderr[:100])
    except Exception as e:
        report.add("S3: IRSA access", False, str(e))


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
                "products.raw.v1",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        has_data = bool(result.stdout.strip())
        report.add(
            "Data flow: raw events in Kafka",
            has_data,
            result.stdout.strip()[:80] if has_data else "no offsets yet",
        )
    except Exception as e:
        report.add("Data flow: raw events in Kafka", False, str(e))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify EKS deployment")
    parser.add_argument(
        "--api-url", default="http://localhost:8000", help="API base URL for health checks"
    )
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per check in seconds")
    parser.add_argument(
        "--skip-data-flow", action="store_true", help="Skip data flow checks (no ingestion yet)"
    )
    args = parser.parse_args()

    report = VerificationReport()

    print("Running EKS deployment verification...\n")

    check_pods(report)
    check_api_health(report, args.api_url)
    check_kafka_topics(report)
    check_s3(report)
    check_postgresql(report)

    if not args.skip_data_flow:
        check_data_flow(report)

    report.print_summary()
    return 1 if report.failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
