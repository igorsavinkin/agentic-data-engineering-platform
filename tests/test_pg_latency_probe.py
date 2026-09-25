"""Unit tests for PostgreSQL latency probe (TASK-113)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.load_test.pg_latency_probe import create_pg_probe_fn


class TestCreatePgProbeFn:
    def test_empty_event_ids(self) -> None:
        probe = create_pg_probe_fn("postgresql://localhost/test")
        result = probe([])
        assert result == []

    @patch("libs.load_test.pg_latency_probe.psycopg2")
    def test_returns_found_event_ids(self, mock_psycopg2: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("e1",), ("e3",)]
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        probe = create_pg_probe_fn("postgresql://localhost/test", source="load-test")
        result = probe(["e1", "e2", "e3"])

        assert sorted(result) == ["e1", "e3"]
        mock_psycopg2.connect.assert_called_once_with("postgresql://localhost/test")
        mock_cursor.execute.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch("libs.load_test.pg_latency_probe.psycopg2")
    def test_strips_psycopg2_scheme(self, mock_psycopg2: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        probe = create_pg_probe_fn("postgresql+psycopg2://localhost/test")
        probe(["e1"])

        mock_psycopg2.connect.assert_called_once_with("postgresql://localhost/test")

    @patch("libs.load_test.pg_latency_probe.psycopg2")
    def test_connection_closed_on_success(self, mock_psycopg2: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        probe = create_pg_probe_fn("postgresql://localhost/test")
        probe(["e1"])

        mock_conn.close.assert_called_once()

    @patch("libs.load_test.pg_latency_probe.psycopg2")
    def test_connection_closed_on_error(self, mock_psycopg2: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = RuntimeError("DB error")
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        probe = create_pg_probe_fn("postgresql://localhost/test")

        try:
            probe(["e1"])
        except RuntimeError:
            pass

        mock_conn.close.assert_called_once()

    @patch("libs.load_test.pg_latency_probe.psycopg2")
    def test_query_includes_source_filter(self, mock_psycopg2: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        probe = create_pg_probe_fn("postgresql://localhost/test", source="my-source")
        probe(["e1"])

        call_args = mock_cursor.execute.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert "my-source" in params
        assert params[0] == "my-source"
        assert "s.name = %s" in query
