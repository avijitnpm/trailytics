"""Tests for Trailytics Client delegation layer."""

from unittest import mock
import pytest

import opik
from trailytics import Client


def test_client_init_defaults():
    with mock.patch("opik.Opik") as mock_opik:
        client = Client()
        mock_opik.assert_called_once_with(
            project_name="Default Project",
            workspace="default",
            host="http://localhost:5173/api/",
            api_key=None,
            batching=True,
        )
        assert client.opik_client == mock_opik.return_value


def test_client_init_custom_params():
    with mock.patch("opik.Opik") as mock_opik:
        client = Client(
            project_name="CustomProject",
            workspace="custom_ws",
            url="http://remote-server:5173/api/",
            api_key="secret-api-key",
            batching=False,
        )
        mock_opik.assert_called_once_with(
            project_name="CustomProject",
            workspace="custom_ws",
            host="http://remote-server:5173/api/",
            api_key="secret-api-key",
            batching=False,
        )


def test_client_delegation_methods():
    mock_opik_instance = mock.MagicMock()
    mock_opik_instance.project_name = "MockProject"
    mock_opik_instance.flush.return_value = True
    mock_opik_instance.get_trace_content.return_value = {"id": "trace-123"}

    with mock.patch("opik.Opik", return_value=mock_opik_instance):
        client = Client()

        assert client.project_name == "MockProject"

        # trace()
        client.trace(name="test_trace", input={"a": 1})
        mock_opik_instance.trace.assert_called_once_with(name="test_trace", input={"a": 1})

        # flush()
        res = client.flush(timeout=10)
        assert res is True
        mock_opik_instance.flush.assert_called_once_with(timeout=10)

        # get_trace_content()
        trace_data = client.get_trace_content("trace-123")
        assert trace_data == {"id": "trace-123"}
        mock_opik_instance.get_trace_content.assert_called_once_with(id="trace-123")

        # end()
        client.end(timeout=5, flush=True)
        mock_opik_instance.end.assert_called_once_with(timeout=5, flush=True)


def test_client_dynamic_attribute_forwarding():
    mock_opik_instance = mock.MagicMock()
    mock_opik_instance.custom_backend_method.return_value = "custom_result"

    with mock.patch("opik.Opik", return_value=mock_opik_instance):
        client = Client()
        result = client.custom_backend_method("arg1", kwarg="arg2")
        assert result == "custom_result"
        mock_opik_instance.custom_backend_method.assert_called_once_with("arg1", kwarg="arg2")
