"""Unit tests for libs.quality.persistence — replay key and config."""

from __future__ import annotations

from libs.quality.persistence import QualityPersistenceConfig, make_replay_key


class TestMakeReplayKey:
    def test_basic_key(self) -> None:
        key = make_replay_key("required_fields")
        assert key == "required_fields:_:_:_"

    def test_with_pipeline_run_id(self) -> None:
        key = make_replay_key("price_validity", pipeline_run_id=42)
        assert key == "price_validity:42:_:_"

    def test_with_observation_id(self) -> None:
        key = make_replay_key("duplicate_check", observation_id=100)
        assert key == "duplicate_check:_:100:_"

    def test_with_source(self) -> None:
        key = make_replay_key("freshness", source="bestbuy")
        assert key == "freshness:_:_:bestbuy"

    def test_full_key(self) -> None:
        key = make_replay_key(
            "required_fields",
            pipeline_run_id=1,
            observation_id=2,
            source="ebay",
        )
        assert key == "required_fields:1:2:ebay"

    def test_deterministic(self) -> None:
        k1 = make_replay_key("check_a", pipeline_run_id=5, source="x")
        k2 = make_replay_key("check_a", pipeline_run_id=5, source="x")
        assert k1 == k2

    def test_different_inputs_different_keys(self) -> None:
        k1 = make_replay_key("check_a", pipeline_run_id=1)
        k2 = make_replay_key("check_a", pipeline_run_id=2)
        assert k1 != k2

    def test_none_source_treated_as_underscore(self) -> None:
        key = make_replay_key("check", source=None)
        assert key == "check:_:_:_"


class TestQualityPersistenceConfig:
    def test_from_url(self) -> None:
        config = QualityPersistenceConfig(db_url="postgresql://u:p@localhost/db")
        assert config.db_url == "postgresql://u:p@localhost/db"

    def test_from_env(self) -> None:
        config = QualityPersistenceConfig.from_env()
        assert "postgresql://" in config.db_url
