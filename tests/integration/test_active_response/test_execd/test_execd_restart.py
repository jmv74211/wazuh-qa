# Copyright (C) 2015-2020, Wazuh Inc.
# Created by Wazuh, Inc. <info@wazuh.com>.
# This program is free software; you can redistribute it and/or modify it under the terms of GPLv2

import hashlib
import os
import platform
import pytest
import time
import requests
import subprocess
import yaml
import json
import socket

from configobj import ConfigObj
from datetime import datetime
from wazuh_testing.tools import WAZUH_PATH, WAZUH_SOCKETS, LOG_FILE_PATH
from wazuh_testing.tools.authd_sim import AuthdSimulator
from wazuh_testing.tools.configuration import load_wazuh_configurations
from wazuh_testing.tools.file import truncate_file
from wazuh_testing.tools.remoted_sim import RemotedSimulator
from wazuh_testing.tools.services import control_service
from wazuh_testing.tools.monitoring import FileMonitor

pytestmark = [pytest.mark.linux, pytest.mark.win32, pytest.mark.tier(level=0), pytest.mark.agent]

AR_LOG_FILE_PATH = os.path.join(WAZUH_PATH, 'logs/active-responses.log')
EXECD_SOCKET = os.path.join(WAZUH_PATH, 'queue', 'alerts', 'execq')
CRYPTO = "aes"
SERVER_ADDRESS = 'localhost'
PROTOCOL = "udp"

def get_current_version():
    if platform.system() == 'Linux':
        config_file_path = os.path.join(WAZUH_PATH, 'etc', 'ossec-init.conf')
        _config = ConfigObj(config_file_path)
        return _config['VERSION']

    else:
        version = None
        with open(os.path.join(WAZUH_PATH, 'VERSION'), 'r') as f:
            version = f.read()
            version = version[:version.rfind('\n')]
        return version


_agent_version = get_current_version()

test_metadata = [
    {
        'command': 'restart-wazuh0',
        'rule_id': '554',
        'results': {
            'success': True,
        }
    },
    {
        'command': 'restart-wazuh0',
        'rule_id': '554',
        'results': {
            'success': False,
        }
    },
]

params = [
    {
        'CRYPTO': CRYPTO,
        'SERVER_ADDRESS': SERVER_ADDRESS,
        'REMOTED_PORT': 1514,
        'PROTOCOL': PROTOCOL
    } for _ in range(0, len(test_metadata))
]

def load_tests(path):
    """ Loads a yaml file from a path
    Return
    ----------
    yaml structure
    """
    with open(path) as f:
        return yaml.safe_load(f)

test_data_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),'data')
configurations_path = os.path.join(test_data_path, 'wazuh_conf.yaml')
configurations = load_wazuh_configurations(configurations_path, __name__, params=params, metadata=test_metadata)

@pytest.fixture(scope="session")
def set_ar_conf_mode():
    local_int_conf_path = os.path.join(WAZUH_PATH, 'etc/shared', 'ar.conf')
    debug_line = 'restart-wazuh0 - restart-wazuh - 0\nrestart-wazuh0 - restart-wazuh.exe - 0\n'
    with open(local_int_conf_path, 'w') as local_file_write:
        local_file_write.write('\n'+debug_line)
    with open(local_int_conf_path, 'r') as local_file_read:
        lines = local_file_read.readlines()
        for line in lines:
            if line == debug_line:
                return

@pytest.fixture(scope="session")
def set_debug_mode():
    local_int_conf_path = os.path.join(WAZUH_PATH, 'etc', 'local_internal_options.conf')
    debug_line = 'execd.debug=2\n'
    with open(local_int_conf_path, 'r') as local_file_read:
        lines = local_file_read.readlines()
        for line in lines:
            if line == debug_line:
                return
    with open(local_int_conf_path, 'a') as local_file_write:
        local_file_write.write('\n'+debug_line)

@pytest.fixture(scope="module", params=configurations)
def get_configuration(request):
    """Get configurations from the module"""
    yield request.param

@pytest.fixture(scope="session")
def set_debug_mode():
    local_int_conf_path = os.path.join(WAZUH_PATH, 'etc', 'local_internal_options.conf')
    debug_line = 'execd.debug=2\n'
    with open(local_int_conf_path, 'r') as local_file_read:
        lines = local_file_read.readlines()
        for line in lines:
            if line == debug_line:
                return
    with open(local_int_conf_path, 'a') as local_file_write:
        local_file_write.write('\n'+debug_line)

def send_message(data_object, socket_path):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.connect(socket_path)
    sock.send(data_object.encode())
    sock.close()

def wait_received_message_line(line):
    if ("DEBUG: Received message: " in line):
        return True
    return None

def wait_start_message_line(line):
    if ("Starting" in line):
        return True
    return None

def wait_message_line(line):
    if ("ossec/active-response/bin/restart-wazuh: {\"version\"" in line):
        return True
    return None

def wait_invalid_input_message_line(line):
    if ("Invalid input format" in line):
        return line
    return None

def wait_ended_message_line(line):
    if ("Ended" in line):
        return True
    return None

def wait_shutdown_message_line(line):
    if ("Shutdown received. Deleting responses." in line):
        return True
    return None

def validate_new_ar_message(message, expected):
    json_alert = json.loads(message) # Alert in JSON
    assert json_alert['version'], 'Missing version in JSON message'
    assert json_alert['version'] == 1, 'Invalid version in JSON message'
    assert json_alert['origin'], 'Missing origin in JSON message'
    assert json_alert['origin']['module'], 'Missing module in JSON message'
    assert json_alert['origin']['module'] == expected['module'], 'Invalid module in JSON message'
    assert json_alert['command'], 'Missing command in JSON message'
    assert json_alert['command'] == expected['command'], 'Invalid command in JSON message'
    assert json_alert['parameters'], 'Missing parameters in JSON message'
    assert json_alert['parameters']['alert'], 'Missing alert in JSON message'
    assert json_alert['parameters']['alert']['rule'], 'Missing rule in JSON message'
    assert json_alert['parameters']['alert']['rule']['id'], 'Missing rule ID in JSON message'
    assert json_alert['parameters']['alert']['rule']['id'] == expected['rule_id'], 'Invalid rule ID in JSON message'

    if expected['ar_name'] != 'restart-wazuh':
        assert json_alert['parameters']['alert']['data'], 'Missing data in JSON message'
        assert json_alert['parameters']['alert']['data']['srcip'], 'Missing source IP in JSON message'
        assert json_alert['parameters']['alert']['data']['srcip'] == SRC_IP, 'Invalid source IP in JSON message'
        assert json_alert['parameters']['alert']['data']['dstuser'], 'Missing destination user in JSON message'
        assert json_alert['parameters']['alert']['data']['dstuser'] == DST_USR, 'Invalid destination user in JSON message'

def build_message(metadata, expected):
    origin = "\"name\":\"\",\"module\":\"wazuh-analysisd\""
    command = "\"" + metadata['command'] + "\""
    rules = "\"level\":5,\"description\":\"Test.\",\"id\":" + metadata['rule_id']

    if expected['success'] == False:
        return "{\"origin\":{" + origin + "},\"command\":" + command + ",\"parameters\":{\"extra_args\":[],\"alert\":{\"rule\":{" + rules + "}}}}"

    return "{\"version\":1,\"origin\":{" + origin + "},\"command\":" + command + ",\"parameters\":{\"extra_args\":[],\"alert\":{\"rule\":{" + rules + "}}}}"

def clean_logs():
    truncate_file(LOG_FILE_PATH)
    truncate_file(AR_LOG_FILE_PATH)

@pytest.fixture(scope="session")
def test_version():
    if _agent_version < "v4.2.0":
        raise AssertionError("The version of the agent is < 4.2.0")

@pytest.fixture(scope="function")
def restart_service():
    clean_logs()
    control_service('restart')
    yield

def test_execd_restart(set_debug_mode, set_ar_conf_mode, get_configuration, test_version, configure_environment, restart_service):
    metadata = get_configuration['metadata']
    expected = metadata['results']
    ossec_log_monitor = FileMonitor(LOG_FILE_PATH)
    ar_log_monitor = FileMonitor(AR_LOG_FILE_PATH)

    message = build_message(metadata, expected)
    send_message(message, EXECD_SOCKET)

    ##### Checking AR in ossec logs ####
    try:
        ossec_log_monitor.start(timeout=10, callback=wait_received_message_line)
    except TimeoutError as err:
        raise AssertionError("Received message tooks too much!")

    ##### Checking AR in active-response logs ####
    try:
        ar_log_monitor.start(timeout=10, callback=wait_start_message_line)
    except TimeoutError as err:
        raise AssertionError("Start message tooks too much!")

    if expected['success'] == True:
        try:
            ar_log_monitor.start(timeout=10, callback=wait_message_line)
        except TimeoutError as err:
            raise AssertionError("AR message tooks too much!")

        # Checking shutdown message in ossec logs
        try:
            ossec_log_monitor.start(timeout=20, callback=wait_shutdown_message_line)
        except TimeoutError as err:
            raise AssertionError("Shutdown message tooks too much!")

        mystring = os.popen('ps -aux | grep restart-wazuh')
        flag = False
        for process in mystring:
            if '/var/ossec/active-response/bin/restart-wazuh' in process:
                flag = True

        if flag == False:
            raise AssertionError("The script is not running")

        try:
            ar_log_monitor.start(timeout=10, callback=wait_ended_message_line)
        except TimeoutError as err:
            raise AssertionError("Ended message tooks too much!")

    else:
        try:
            ar_log_monitor.start(timeout=10, callback=wait_invalid_input_message_line)
        except TimeoutError as err:
            raise AssertionError("Invalid input message tooks too much!")