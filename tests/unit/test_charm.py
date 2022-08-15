# Copyright 2020 Canonical Ltd.
# Licensed under the GPLv3, see LICENCE file for details.

from unittest import mock
import logging
import os

import pytest
from ops import model
from ops import testing

from charm import JenkinsAgentCharm
from . import types

SERVICE_NAME = "jenkins-agent"

CONFIG_DEFAULT = {
    "image": "jenkins-agent-operator",
    "jenkins_url": "",
    "jenkins_agent_name": "",
    "jenkins_agent_token": "",
    "jenkins_agent_label": "",
}

CONFIG_ONE_AGENT = {
    "jenkins_url": "http://test",
    "jenkins_agent_name": "agent-one",
    "jenkins_agent_token": "token-one",
}

CONFIG_ONE_AGENT_CUSTOM_IMAGE = {
    "image": "image-name",
    "jenkins_url": "http://test",
    "jenkins_agent_name": "agent-one",
    "jenkins_agent_token": "token-one",
}

ENV_INITIAL = {'JENKINS_AGENTS': '', 'JENKINS_TOKENS': '', 'JENKINS_URL': ''}

ENV_ONE_AGENT = {
    'JENKINS_AGENTS': 'agent-one',
    'JENKINS_TOKENS': 'token-one',
    'JENKINS_URL': 'http://test',
}

SPEC_EXPECTED = {
    'containers': [
        {
            'config': {
                'JENKINS_AGENTS': 'agent-one',
                'JENKINS_TOKENS': 'token-one',
                'JENKINS_URL': 'http://test',
            },
            'imageDetails': {'imagePath': 'image-name'},
            'name': 'jenkins-agent',
            'readinessProbe': {'exec': {'command': ['/bin/cat', '/var/lib/jenkins/agents/.ready']}},
        }
    ]
}


def test__get_env_config_initial(harness: testing.Harness[JenkinsAgentCharm]):
    """arrange: given charm in its initial state
    act: when the environment variables for the charm are generated
    assert: then the environment is empty.
    """
    env_config = harness.charm._get_env_config()

    assert env_config == {
        'JENKINS_AGENTS': '',
        'JENKINS_TOKENS': '',
        'JENKINS_URL': '',
    }


def test__get_env_config_config(harness: testing.Harness[JenkinsAgentCharm]):
    """arrange: given charm in its initial state except that the configuration has been set
    act: when the environment variables for the charm are generated
    assert: then the environment contains the data from the configuration.
    """
    jenkins_url = "http://test"
    jenkins_agent_name = "agent"
    jenkins_agent_token = "token"
    harness.update_config(
        {
            "jenkins_url": jenkins_url,
            "jenkins_agent_name": jenkins_agent_name,
            "jenkins_agent_token": jenkins_agent_token,
        }
    )

    env_config = harness.charm._get_env_config()

    assert env_config == {
        'JENKINS_AGENTS': jenkins_agent_name,
        'JENKINS_TOKENS': jenkins_agent_token,
        'JENKINS_URL': jenkins_url,
    }


@pytest.mark.parametrize(
    "agents, expected_jenkins_agent_name, tokens, expected_jenkins_agent_token",
    [
        pytest.param([], "", [], "", id="empty"),
        pytest.param(["agent"], "agent", ["token"], "token", id="single"),
        pytest.param(
            ["agent 1", "agent 2"],
            "agent 1:agent 2",
            ["token 1", "token 2"],
            "token 1:token 2",
            id="multiple",
        ),
    ],
)
def test__get_env_config_relation(
    harness: testing.Harness[JenkinsAgentCharm],
    agents: list[str],
    expected_jenkins_agent_name: str,
    tokens: list[str],
    expected_jenkins_agent_token: str,
):
    """arrange: given charm in its initial state except that relation data has been set
    act: when the environment variables for the charm are generated
    assert: then the environment contains the data from the relation.
    """
    jenkins_url = "http://test"
    harness.charm._stored.jenkins_url = jenkins_url
    harness.charm._stored.agents = agents
    harness.charm._stored.agent_tokens = tokens

    env_config = harness.charm._get_env_config()

    assert env_config == {
        'JENKINS_AGENTS': expected_jenkins_agent_name,
        'JENKINS_TOKENS': expected_jenkins_agent_token,
        'JENKINS_URL': jenkins_url,
    }


def test__get_env_config_config_relation(harness: testing.Harness[JenkinsAgentCharm]):
    """arrange: given charm in its initial state except that the configuration and relation data
        has been set
    act: when the environment variables for the charm are generated
    assert: then the environment contains the data from the relation.
    """
    # Set the configuraton
    config_jenkins_url = "http://test_config"
    config_jenkins_agent_name = "agent config"
    config_jenkins_agent_token = "token config"
    harness.update_config(
        {
            "jenkins_url": config_jenkins_url,
            "jenkins_agent_name": config_jenkins_agent_name,
            "jenkins_agent_token": config_jenkins_agent_token,
        }
    )
    # Set the relation
    relation_jenkins_url = "http://test_relation"
    relation_jenkins_agent_name = "agent relation"
    relation_jenkins_agent_token = "token relation"
    harness.charm._stored.jenkins_url = relation_jenkins_url
    harness.charm._stored.agents = [relation_jenkins_agent_name]
    harness.charm._stored.agent_tokens = [relation_jenkins_agent_token]

    env_config = harness.charm._get_env_config()

    assert env_config == {
        'JENKINS_AGENTS': relation_jenkins_agent_name,
        'JENKINS_TOKENS': relation_jenkins_agent_token,
        'JENKINS_URL': relation_jenkins_url,
    }


def test_config_changed_invalid(harness_pebble_ready: testing.Harness[JenkinsAgentCharm]):
    """arrange: given charm in its initial state
    act: when the config_changed event occurs
    assert: the charm enters the blocked status with message that required configuration is missing
    """
    harness_pebble_ready.charm.on.config_changed.emit()

    assert isinstance(harness_pebble_ready.model.unit.status, model.BlockedStatus)
    assert "jenkins_agent_name" in harness_pebble_ready.model.unit.status.message
    assert "jenkins_agent_token" in harness_pebble_ready.model.unit.status.message


def test_config_changed(
    harness_pebble_ready: testing.Harness[JenkinsAgentCharm],
    valid_config,
    caplog: pytest.LogCaptureFixture,
):
    """arrange: given charm in its initial state with valid configuration
    act: when the config_changed event occurs
    assert: the charm is in the active status, the container has the jenkins-agent service and has
        been restarted and a log message indicating a layer has been added is written.
    """
    harness_pebble_ready.update_config(valid_config)
    # Mock the restart function on the container
    container: model.Container = harness_pebble_ready.model.unit.get_container(
        harness_pebble_ready.charm.service_name
    )
    container.restart = mock.MagicMock()

    caplog.set_level(logging.DEBUG)
    harness_pebble_ready.charm.on.config_changed.emit()

    assert isinstance(harness_pebble_ready.model.unit.status, model.ActiveStatus)
    assert harness_pebble_ready.charm.service_name in container.get_plan().services
    container.restart.assert_called_once_with(harness_pebble_ready.charm.service_name)
    assert "add_layer" in caplog.text


def test_config_changed_pebble_not_ready(harness: testing.Harness[JenkinsAgentCharm], valid_config):
    """arrange: given charm where the pebble is not ready state with valid configuration
    act: when the config_changed event occurs
    assert: the event is deferred.
    """
    harness.update_config(valid_config)
    # Mock the restart function on the container
    container: model.Container = harness.model.unit.get_container(harness.charm.service_name)
    container.restart = mock.MagicMock()

    harness.charm.on.config_changed.emit()

    assert isinstance(harness.model.unit.status, model.MaintenanceStatus)
    container.restart.assert_not_called()


def test_config_changed_no_change(
    harness_pebble_ready: testing.Harness[JenkinsAgentCharm],
    valid_config,
    caplog: pytest.LogCaptureFixture,
):
    """arrange: given charm in active state with valid configuration
    act: when the config_changed event occurs
    assert: the charm stays in the active status, the container is not restarted and a log message
        indicating unchaged configuration is written.
    """
    # Get container into active state
    harness_pebble_ready.update_config(valid_config)
    harness_pebble_ready.charm.on.config_changed.emit()
    # Mock the restart function on the container
    container: model.Container = harness_pebble_ready.model.unit.get_container(
        harness_pebble_ready.charm.service_name
    )
    container.restart = mock.MagicMock()

    caplog.set_level(logging.DEBUG)
    harness_pebble_ready.charm.on.config_changed.emit()

    assert isinstance(harness_pebble_ready.model.unit.status, model.ActiveStatus)
    container.restart.assert_not_called()
    assert "unchanged" in caplog.text


@pytest.mark.parametrize(
    "agent_tokens, config, expected_validity, expected_message_contents, "
    "expected_not_in_message_contents",
    [
        pytest.param(
            [],
            {"jenkins_url": "", "jenkins_agent_name": "", "jenkins_agent_token": ""},
            False,
            ("jenkins_url", "jenkins_agent_name", "jenkins_agent_token"),
            (),
            id="agent_tokens not set and configuration empty",
        ),
        pytest.param(
            ["token"],
            {"jenkins_url": "", "jenkins_agent_name": "", "jenkins_agent_token": ""},
            True,
            (),
            (),
            id="agent_tokens set and configuration empty",
        ),
        pytest.param(
            [],
            {"jenkins_url": "http://test", "jenkins_agent_name": "", "jenkins_agent_token": ""},
            False,
            ("jenkins_agent_name", "jenkins_agent_token"),
            ("jenkins_url",),
            id="agent_tokens not set and configuration empty except jenkins_url set",
        ),
        pytest.param(
            [],
            {"jenkins_url": "", "jenkins_agent_name": "agent 1", "jenkins_agent_token": "token 1"},
            False,
            ("jenkins_url",),
            ("jenkins_agent_name", "jenkins_agent_token"),
            id="agent_tokens not set and configuration empty except jenkins_agent_name and "
            "jenkins_agent_token set",
        ),
        pytest.param(
            [],
            {
                "jenkins_url": "http://test",
                "jenkins_agent_name": "agent 1",
                "jenkins_agent_token": "token 1",
            },
            True,
            (),
            (),
            id="agent_tokens not set and configuration valid",
        ),
    ],
)
def test__is_valid_config(
    harness: testing.Harness[JenkinsAgentCharm],
    agent_tokens: list[str],
    config,
    expected_validity: bool,
    expected_message_contents: tuple[str, ...],
    expected_not_in_message_contents: tuple[str, ...],
):
    """arrange: given charm with the given agent_tokens and configuration set
    act: when _is_valid_config is called
    assert: then the expected configuration validity and message is returned.
    """
    harness.charm._stored.agent_tokens = agent_tokens
    harness.update_config(config)

    validity, message = harness.charm._is_valid_config()

    assert validity == expected_validity
    if validity:
        assert message is None
        return
    for expected_message_content in expected_message_contents:
        assert expected_message_content in message
    for expected_not_in_message_content in expected_not_in_message_contents:
        assert expected_not_in_message_content not in message


def test_on_agent_relation_joined(
    harness: testing.Harness[JenkinsAgentCharm],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    """arrange: given charm in its initial state
    act: when the slave_relation_joined occurs
    assert: then the agent sets the executors, labels and slave hosts relation data and writes a
        note to the logs.
    """
    # Mock uname and CPU count
    mock_os_cpu_count = mock.MagicMock()
    cpu_count = 8
    mock_os_cpu_count.return_value = cpu_count
    monkeypatch.setattr(os, "cpu_count", mock_os_cpu_count)
    mock_os_uname = mock.MagicMock()
    machine_architecture = "x86_64"
    mock_os_uname.return_value.machine = machine_architecture
    monkeypatch.setattr(os, "uname", mock_os_uname)

    caplog.set_level(logging.INFO)
    harness.enable_hooks()
    relation_id = harness.add_relation("slave", "jenkins")
    unit_name = "jenkins-agent-k8s/0"
    harness.add_relation_unit(relation_id, unit_name)

    assert harness.get_relation_data(relation_id, unit_name) == {
        'executors': str(cpu_count),
        'labels': machine_architecture,
        'slavehost': unit_name.replace("/", "-"),
    }
    assert "relation" in caplog.text.lower()
    assert "joined" in caplog.text.lower()


def test_on_agent_relation_joined_labels(
    harness: testing.Harness[JenkinsAgentCharm], monkeypatch: pytest.MonkeyPatch
):
    """arrange: given charm in its initial state with labels configured
    act: when the slave_relation_joined occurs
    assert: then the agent sets the labels based on the configuration.
    """
    labels = "label 1,label 2"
    harness.update_config({"jenkins_agent_labels": labels})

    # Mock CPU count and uname
    monkeypatch.setattr(os, "uname", mock.MagicMock())
    monkeypatch.setattr(os, "cpu_count", mock.MagicMock())

    harness.enable_hooks()
    relation_id = harness.add_relation("slave", "jenkins")
    unit_name = "jenkins-agent-k8s/0"
    harness.add_relation_unit(relation_id, unit_name)

    assert harness.get_relation_data(relation_id, unit_name)["labels"] == labels


def test_on_agent_relation_changed_jenkins_url_missing(
    harness: testing.Harness[JenkinsAgentCharm],
    caplog: pytest.LogCaptureFixture,
    charm_with_jenkins_relation: types.CharmWithJenkinsRelation,
):
    """arrange: given charm with relation to jenkins
    act: when the relation data is updated without the jenkins url
    assert: the unit stays in active status and a warning is written to the logs.
    """
    # Update relation data
    caplog.set_level(logging.INFO)
    harness.update_relation_data(
        relation_id=charm_with_jenkins_relation.relation_id,
        app_or_unit=charm_with_jenkins_relation.remote_unit_name,
        key_values={"secret": "relation token"},
    )

    assert harness.charm._stored.jenkins_url is None
    assert harness.charm._stored.agent_tokens == []
    assert harness.charm._stored.agents[-1] == "jenkins-agent-k8s-0"
    assert isinstance(harness.model.unit.status, model.ActiveStatus)
    assert "expected 'url'" in caplog.text.lower()
    assert "skipping setup" in caplog.text.lower()


def test_on_agent_relation_changed_secret_missing(
    harness: testing.Harness[JenkinsAgentCharm],
    caplog: pytest.LogCaptureFixture,
    charm_with_jenkins_relation: types.CharmWithJenkinsRelation,
):
    """arrange: given charm with relation to jenkins
    act: when the relation data is updated without the secret
    assert: the unit stays in active status and a warning is written to the logs.
    """
    # Update relation data
    caplog.set_level(logging.INFO)
    relation_jenkins_url = "http://relation"
    harness.update_relation_data(
        relation_id=charm_with_jenkins_relation.relation_id,
        app_or_unit=charm_with_jenkins_relation.remote_unit_name,
        key_values={"url": relation_jenkins_url},
    )

    assert harness.charm._stored.jenkins_url == relation_jenkins_url
    assert harness.charm._stored.agent_tokens == []
    assert harness.charm._stored.agents[-1] == "jenkins-agent-k8s-0"
    assert isinstance(harness.model.unit.status, model.ActiveStatus)
    assert "expected 'secret'" in caplog.text.lower()
    assert "skipping setup" in caplog.text.lower()


def test_on_agent_relation_changed(
    harness: testing.Harness[JenkinsAgentCharm],
    caplog: pytest.LogCaptureFixture,
    charm_with_jenkins_relation: types.CharmWithJenkinsRelation,
    monkeypatch: pytest.MonkeyPatch,
):
    """arrange: given charm with relation to jenkins
    act: when the relation data is updated
    assert: then the relation data is stored on the charm, the unit enters maintenance status,
        emits the config_changed event and writes a note to the logs.
    """
    # Mock config_changed hook
    mock_config_changed = mock.MagicMock()
    monkeypatch.setattr(harness.charm.on, "config_changed", mock_config_changed)

    # Update relation data
    caplog.set_level(logging.INFO)
    relation_jenkins_url = "http://relation"
    relation_secret = "relation token"
    harness.update_relation_data(
        relation_id=charm_with_jenkins_relation.relation_id,
        app_or_unit=charm_with_jenkins_relation.remote_unit_name,
        key_values={"url": relation_jenkins_url, "secret": relation_secret},
    )

    assert harness.charm._stored.jenkins_url == relation_jenkins_url
    assert harness.charm._stored.agent_tokens[-1] == relation_secret
    assert harness.charm._stored.agents[-1] == "jenkins-agent-k8s-0"
    mock_config_changed.emit.assert_called_once_with()
    assert isinstance(harness.model.unit.status, model.MaintenanceStatus)
    assert "relation" in caplog.text.lower()
    assert "changed" in caplog.text.lower()


def test_on_agent_relation_changed_new_agent_name(
    harness: testing.Harness[JenkinsAgentCharm],
    charm_with_jenkins_relation: types.CharmWithJenkinsRelation,
    monkeypatch: pytest.MonkeyPatch,
):
    """arrange: given charm with relation to jenkins and an existing agent
    act: when the relation data is updated
    assert: then a new agent is stored.
    """
    harness.charm._stored.agents = ["jenkins-agent-k8s-0"]
    # Mock config_changed hook
    monkeypatch.setattr(harness.charm.on, "config_changed", mock.MagicMock())

    # Update relation data
    harness.update_relation_data(
        relation_id=charm_with_jenkins_relation.relation_id,
        app_or_unit=charm_with_jenkins_relation.remote_unit_name,
        key_values={"url": "http://relation", "secret": "relation token"},
    )

    assert harness.charm._stored.agents[-1] == "jenkins-agent-k8s-1"


def test_on_agent_relation_changed_jenkins_url_configured(
    harness: testing.Harness[JenkinsAgentCharm],
    valid_config,
    caplog: pytest.LogCaptureFixture,
    charm_with_jenkins_relation: types.CharmWithJenkinsRelation,
    monkeypatch: pytest.MonkeyPatch,
):
    """arrange: given charm with relation to jenkins and the jenkins_url configuration set
    act: when the relation data is updated
    assert: then the relation data is stored on the charm, the unit stays in active status, does
        not emit the config_changed event and writes a note to the logs.
    """
    harness.update_config(valid_config)
    # Mock config_changed hook
    mock_config_changed = mock.MagicMock()
    monkeypatch.setattr(harness.charm.on, "config_changed", mock_config_changed)

    # Update relation data
    caplog.set_level(logging.INFO)
    relation_jenkins_url = "http://relation"
    relation_secret = "relation token"
    harness.update_relation_data(
        relation_id=charm_with_jenkins_relation.relation_id,
        app_or_unit=charm_with_jenkins_relation.remote_unit_name,
        key_values={"url": relation_jenkins_url, "secret": relation_secret},
    )

    assert harness.charm._stored.jenkins_url == relation_jenkins_url
    assert harness.charm._stored.agent_tokens[-1] == relation_secret
    assert harness.charm._stored.agents[-1] == "jenkins-agent-k8s-0"
    mock_config_changed.emit.assert_not_called()
    assert isinstance(harness.model.unit.status, model.ActiveStatus)
    assert "relation" in caplog.text.lower()
    assert "changed" in caplog.text.lower()
    assert "'jenkins_url'" in caplog.text.lower()


# class TestJenkinsAgentCharm(unittest.TestCase):
#     def setUp(self):
#         self.harness = Harness(JenkinsAgentCharm)
#         self.addCleanup(self.harness.cleanup)
#         self.harness.begin()
#         self.harness.disable_hooks()
#         self.harness.update_config(CONFIG_DEFAULT)

#     @patch("charm.JenkinsAgentCharm._on_config_changed")
#     @patch("os.uname")
#     @patch("os.cpu_count")
#     def test__on_agent_relation_changed__multiple__agents(
#         self, mock_os_cpu_count, mock_os_uname, mock_on_config_changed
#     ):
#         """Test relation_data is set when a new relation joins."""
#         mock_os_cpu_count.return_value = 8
#         mock_os_uname.return_value.machine = "x86_64"
#         remote_unit = "jenkins/0"
#         agent_name = "alejdg-jenkins-agent-k8s-0"
#         expected_new_agent = "alejdg-jenkins-agent-k8s-1"
#         url = "http://test"
#         secret = "token"

#         self.harness.charm._stored.agents = [agent_name]
#         self.harness.enable_hooks()
#         rel_id = self.harness.add_relation("slave", "jenkins")
#         self.harness.add_relation_unit(rel_id, remote_unit)
#         self.harness.update_relation_data(rel_id, remote_unit, {"url": url, "secret": secret})
#         self.assertEqual(self.harness.charm._stored.jenkins_url, url)
#         self.assertEqual(self.harness.charm._stored.agent_tokens[-1], secret)
#         self.assertEqual(self.harness.charm._stored.agents[-1], expected_new_agent)
#         mock_on_config_changed.assert_called()
