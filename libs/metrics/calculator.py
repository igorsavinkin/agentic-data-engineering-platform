"""Daily metrics calculator (TASK-062).

Computes analytical metrics from product_observations for a given date
range. The calculator is stateless — it takes a Polars DataFrame of
observations and returns a list of metric values.

Metrics computed:
- observation_count: total observations per day
- unique_products: distinct canonical products observed
- avg_price: average observed price (non-null only)
- availability_in_stock: observations with availability='in_stock'
- availability_out_of_stock: observations with availability='out_of_stock'
- source_observation_count: per-source observation counts
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import polars as pl

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DailyMetric:
    """A single computed metric value."""

    metric_date: date
    metric_name: str
    dimension: str
    value: float

    @property
    def replay_key(self) -> str:
        dim = self.dimension or "_"
        return f"{self.metric_name}:{self.metric_date.isoformat()}:{dim}"


@dataclass
class DailyMetricsResult:
    """Outcome of computing daily metrics for a date range."""

    metrics: list[DailyMetric] = field(default_factory=list)
    observation_count: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors


class DailyMetricsCalculator:
    """Compute daily analytical metrics from product observations.

    The calculator expects a Polars DataFrame with at least these columns:
    - source_name: text
    - product_id: text (canonical product identifier)
    - price: float64 (nullable)
    - availability: text
    - collected_at: datetime

    Parameters
    ----------
    target_date:
        The date to compute metrics for.
    """

    def __init__(self, target_date: date) -> None:
        self._target_date = target_date

    def compute(self, observations: pl.DataFrame) -> DailyMetricsResult:
        """Compute all metrics from the observation DataFrame.

        Returns a result containing all computed metrics. If the input
        is empty, returns an empty result (no errors).
        """
        result = DailyMetricsResult()
        result.observation_count = observations.height

        if observations.is_empty():
            return result

        try:
            result.metrics.extend(self._observation_count(observations))
            result.metrics.extend(self._unique_products(observations))
            result.metrics.extend(self._avg_price(observations))
            result.metrics.extend(self._availability_distribution(observations))
            result.metrics.extend(self._source_observation_count(observations))
        except Exception as exc:
            result.errors.append(str(exc))
            logger.error("metrics_computation_failed", extra={"error": str(exc)})

        return result

    def _observation_count(self, df: pl.DataFrame) -> list[DailyMetric]:
        count = df.height
        return [
            DailyMetric(
                metric_date=self._target_date,
                metric_name="observation_count",
                dimension="",
                value=float(count),
            )
        ]

    def _unique_products(self, df: pl.DataFrame) -> list[DailyMetric]:
        if "product_id" not in df.columns:
            return []
        unique = df.select(pl.col("product_id").n_unique()).item()
        return [
            DailyMetric(
                metric_date=self._target_date,
                metric_name="unique_products",
                dimension="",
                value=float(unique),
            )
        ]

    def _avg_price(self, df: pl.DataFrame) -> list[DailyMetric]:
        if "price" not in df.columns:
            return []
        prices = df.filter(pl.col("price").is_not_null())
        if prices.is_empty():
            return [
                DailyMetric(
                    metric_date=self._target_date,
                    metric_name="avg_price",
                    dimension="",
                    value=0.0,
                )
            ]
        avg = prices.select(pl.col("price").mean()).item()
        return [
            DailyMetric(
                metric_date=self._target_date,
                metric_name="avg_price",
                dimension="",
                value=float(avg) if avg is not None else 0.0,
            )
        ]

    def _availability_distribution(self, df: pl.DataFrame) -> list[DailyMetric]:
        if "availability" not in df.columns:
            return []
        metrics: list[DailyMetric] = []
        for state in ["in_stock", "out_of_stock"]:
            count = df.filter(pl.col("availability") == state).height
            metrics.append(
                DailyMetric(
                    metric_date=self._target_date,
                    metric_name=f"availability_{state}",
                    dimension="",
                    value=float(count),
                )
            )
        return metrics

    def _source_observation_count(self, df: pl.DataFrame) -> list[DailyMetric]:
        if "source_name" not in df.columns:
            return []
        metrics: list[DailyMetric] = []
        counts = df.group_by("source_name").len()
        for row in counts.iter_rows():
            source_name, count = row
            metrics.append(
                DailyMetric(
                    metric_date=self._target_date,
                    metric_name="source_observation_count",
                    dimension=str(source_name),
                    value=float(count),
                )
            )
        return metrics
