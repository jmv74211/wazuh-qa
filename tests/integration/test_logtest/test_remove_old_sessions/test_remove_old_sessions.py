# Copyright (C) 2015-2021, Wazuh Inc.
# Created by Wazuh, Inc. <info@wazuh.com>.
# This program is free software; you can redistribute it and/or modify it under the terms of GPLv2

import os

import pytest
from wazuh_testing import global_parameters
from wazuh_testing.logtest import (callback_logtest_started,
                                   callback_remove_session,
                                   callback_session_initialized)
from wazuh_testing.tools import LOG_FILE_PATH, LOGTEST_SOCKET_PATH
from wazuh_testing.tools.configuration import load_wazuh_configurations
from wazuh_testing.tools.monitoring import FileMonitor, SocketController
from wazuh_testing.tools.services import control_service
from wazuh_testing.tools.file import truncate_file

# Marks
pytestmark = [pytest.mark.linux, pytest.mark.tier(level=0), pytest.mark.server]

# Configurations
test_data_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data')
configurations_path = os.path.join(test_data_path, 'wazuh_conf.yaml')
configurations = load_wazuh_configurations(configurations_path, __name__)

# Variables
logtest_startup_timeout = 30
wazuh_log_monitor = FileMonitor(LOG_FILE_PATH)
local_internal_options = {'analysisd.debug': str(1)}
msg_create_session = """{"version":1, "command":"log_processing", "parameters":{
"event": "Oct 15 21:07:56 linux-agent sshd[29205]: Invalid user blimey from 18.18.18.18 port 48928",
"log_format": "syslog", "location": "master->/var/log/syslog"}}"""


@pytest.fixture(scope='module')
def get_local_internal_options():
    """Get configurations from the module."""
    return local_internal_options


# Function to manage the comunication with Wazuh-logtest
def create_connection():
    return SocketController(address=LOGTEST_SOCKET_PATH, family='AF_UNIX', connection_protocol='TCP')


def remove_connection(connection):
    connection.close()
    del connection


# Fixture
@pytest.fixture(scope='module', params=configurations)
def get_configuration(request):
    """Get configurations from the module."""
    return request.param


@pytest.fixture(scope='module')
def wait_for_logtest_startup(request):
    """Wait until logtest has begun."""
    log_monitor = FileMonitor(LOG_FILE_PATH)
    log_monitor.start(timeout=logtest_startup_timeout, callback=callback_logtest_started)


@pytest.fixture(scope='module')
def restart_required_logtest_daemons():
    """Wazuh logtests daemons handler."""
    required_logtest_daemons = ['wazuh-analysisd', 'wazuh-db']

    truncate_file(LOG_FILE_PATH)

    for daemon in required_logtest_daemons:
        control_service('restart', daemon=daemon)

    yield

    for daemon in required_logtest_daemons:
        control_service('stop', daemon=daemon)


# Test
def test_remove_old_session(get_local_internal_options,
                            configure_local_internal_options,
                            get_configuration, configure_environment,
                            restart_required_logtest_daemons,
                            wait_for_logtest_startup):
    """Create more sessions than allowed and wait for the message which
    informs that Wazuh-logtest has removed the oldest session.
    """

    max_sessions = int(get_configuration['sections'][0]['elements'][2]['max_sessions']['value'])

    first_session_token = None

    for i in range(0, max_sessions):

        receiver_socket = create_connection()
        receiver_socket.send(msg_create_session, True)
        msg_recived = receiver_socket.receive()[4:]
        msg_recived = msg_recived.decode()
        remove_connection(receiver_socket)

        if i == 0:
            first_session_token = wazuh_log_monitor.start(timeout=global_parameters.default_timeout,
                                                          callback=callback_session_initialized,
                                                          error_message='Event not found')
        else:
            wazuh_log_monitor.start(timeout=global_parameters.default_timeout,
                                    callback=callback_session_initialized,
                                    error_message='Event not found')

    # This session should do Wazuh-logtest to remove the oldest session
    receiver_socket = create_connection()
    receiver_socket.send(msg_create_session, True)
    msg_recived = receiver_socket.receive()[4:]
    msg_recived = msg_recived.decode()
    remove_connection(receiver_socket)

    remove_session_token = wazuh_log_monitor.start(timeout=global_parameters.default_timeout,
                                                   callback=callback_remove_session,
                                                   error_message='Event not found')

    assert first_session_token == remove_session_token, "Incorrect session removed"

    wazuh_log_monitor.start(timeout=global_parameters.default_timeout,
                            callback=callback_session_initialized,
                            error_message='Event not found')
