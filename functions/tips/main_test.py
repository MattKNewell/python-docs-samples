# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
from unittest.mock import MagicMock, Mock, patch

import flask
import pytest
import requests
import responses

import main


# Create a fake "app" for generating test request contexts.
@pytest.fixture(scope="module")
def app():
    return flask.Flask(__name__)


def test_lazy_globals(app):
    with app.test_request_context():
        main.lazy_globals(flask.request)


@responses.activate
def test_connection_pooling_200(app):
    responses.add(responses.GET, 'http://example.com',
                  json={'status': 'OK'}, status=200)
    with app.test_request_context():
        main.connection_pooling(flask.request)


@responses.activate
def test_connection_pooling_404(app):
    responses.add(responses.GET, 'http://example.com',
                  json={'error': 'not found'}, status=404)
    with app.test_request_context():
        with pytest.raises(requests.exceptions.HTTPError):
            main.connection_pooling(flask.request)


def test_avoid_infinite_retries(capsys):
    now = datetime.datetime.now()

    with patch('main.datetime', wraps=datetime.datetime) as datetime_mock:
        datetime_mock.now = Mock(return_value=now)
        old_event = Mock(
            timestamp=(now - datetime.timedelta(seconds=15)).isoformat())
        young_event = Mock(
            timestamp=(now - datetime.timedelta(seconds=5)).isoformat())
        context = Mock(event_id='fake_event_id')

        main.avoid_infinite_retries(old_event, context)
        out, _ = capsys.readouterr()
        assert 'Dropped {} (age 15000.0ms)'.format(context.event_id) in out

        main.avoid_infinite_retries(young_event, context)
        out, _ = capsys.readouterr()
        assert 'Processed {} (age 5000.0ms)'.format(context.event_id) in out


def test_retry_or_not():
    with patch('google.cloud') as cloud_mock:

        error_client = MagicMock()

        cloud_mock.error_reporting = MagicMock(
            Client=MagicMock(return_value=error_client))

        event = Mock(data={})
        main.retry_or_not(event, None)
        assert error_client.report_exception.call_count == 1

        event.data = {'retry': True}
        with pytest.raises(RuntimeError):
            main.retry_or_not(event, None)

        assert error_client.report_exception.call_count == 2
