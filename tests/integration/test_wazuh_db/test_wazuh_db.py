# Copyright (C) 2015-2021, Wazuh Inc.
# Created by Wazuh, Inc. <info@wazuh.com>.
# This program is free software; you can redistribute it and/or modify it under the terms of GPLv2

import os
import re
import time

import pytest
import yaml
import random
from wazuh_testing.tools import WAZUH_PATH
from wazuh_testing.tools.services import control_service
from wazuh_testing.tools.wazuh_manager import remove_all_agents

# Marks

pytestmark = [pytest.mark.linux, pytest.mark.tier(level=0), pytest.mark.server]

# Configurations

test_data_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data')
messages_files = os.listdir(test_data_path)
module_tests = list()
for file in messages_files:
    with open(os.path.join(test_data_path, file)) as f:
        module_tests.append((yaml.safe_load(f), file.split('_')[0]))

# Variables

log_monitor_paths = []

wdb_path = os.path.join(os.path.join(WAZUH_PATH, 'queue', 'db', 'wdb'))

receiver_sockets_params = [(wdb_path, 'AF_UNIX', 'TCP')]

# mitm_analysisd = ManInTheMiddle(address=analysis_path, family='AF_UNIX', connection_protocol='UDP')
# monitored_sockets_params is a List of daemons to start with optional ManInTheMiddle to monitor
# List items -> (wazuh_daemon: str,(
#                mitm: ManInTheMiddle
#                daemon_first: bool))
# Example1 -> ('wazuh-clusterd', None)              Only start wazuh-clusterd with no MITM
# Example2 -> ('wazuh-clusterd', (my_mitm, True))   Start MITM and then wazuh-clusterd
monitored_sockets_params = [('wazuh-db', None, True)]

receiver_sockets, monitored_sockets, log_monitors = None, None, None  # Set in the fixtures


def regex_match(regex, string):
    regex = regex.replace('*', '.*')
    regex = regex.replace('[', '')
    regex = regex.replace(']', '')
    regex = regex.replace('(', '')
    regex = regex.replace(')', '')
    string = string.replace('[', '')
    string = string.replace(']', '')
    string = string.replace('(', '')
    string = string.replace(')', '')
    return re.match(regex, string)


@pytest.fixture(scope='module')
def clean_registered_agents():
    remove_all_agents('wazuhdb')
    time.sleep(5)


@pytest.fixture(scope='module')
def restart_wazuh():
    control_service('restart')


@pytest.fixture(scope='function')
def pre_insert_agents():
    AGENTS_CANT = 14000
    AGENTS_OFFSET = 20
    for id in range(AGENTS_OFFSET, AGENTS_OFFSET + AGENTS_CANT):
        command = f'global insert-agent {{"id":{id},"name":"TestName{id}","date_add":1599223378}}'
        receiver_sockets[0].send(command, size=True)
        response = receiver_sockets[0].receive(size=True).decode()
        data = response.split()
        assert data[0] == 'ok', f"Unable to add agent {id}"

        command = f'global update-keepalive {{"id":{id},"sync_status":"syncreq","connection_status":"active"}}'
        receiver_sockets[0].send(command, size=True)
        response = receiver_sockets[0].receive(size=True).decode()
        data = response.split()
        assert data[0] == 'ok', f"Unable to update agent {id}"


@pytest.fixture(scope='function')
def pre_set_sync_info():
    """Asign the last_attempt value to last_completion in sync_info table to force the synced status"""

    command = "agent 000 sql UPDATE sync_info SET last_completion = 10, last_attempt = 10 " \
              "where component = 'syscollector-packages'"
    receiver_sockets[0].send(command, size=True)
    response = receiver_sockets[0].receive(size=True).decode()
    data = response.split()
    assert data[0] == 'ok', 'Unable to set sync_info table'


@pytest.fixture(scope='function')
def pre_insert_packages():
    """Insert a set of dummy packages into sys_programs table"""

    PACKAGES_NUMBER = 20000
    for pkg_n in range(PACKAGES_NUMBER):
        command = f'agent 000 sql INSERT OR REPLACE INTO sys_programs \
        (scan_id,scan_time,format,name,priority,section,size,vendor,install_time,version,\
        architecture,multiarch,source,description,location,triaged,cpe,msu_name,checksum,item_id)\
        VALUES(0,"2021/04/07 22:00:00","deb","test_package_{pkg_n}","optional","utils",{random.randint(200,1000)},\
        "Wazuh wazuh@wazuh.com",NULL,"{random.randint(1,10)}.0.0","all",NULL,NULL,"Test package {pkg_n}",\
        NULL,0,NULL,NULL,"{random.getrandbits(128)}","{random.getrandbits(128)}")'
        receiver_sockets[0].send(command, size=True)
        response = receiver_sockets[0].receive(size=True).decode()
        data = response.split()
        assert data[0] == 'ok', f"Unable to insert package {pkg_n}"


@pytest.mark.parametrize('test_case',
                         [case['test_case'] for module_data in module_tests for case in module_data[0]],
                         ids=[f"{module_name}: {case['name']}"
                              for module_data, module_name in module_tests
                              for case in module_data]
                         )
def test_wazuh_db_messages(restart_wazuh, clean_registered_agents, configure_sockets_environment, connect_to_sockets_module, test_case):
    """Check that every input message in wazuh-db socket generates the adequate output to wazuh-db socket

    Parameters
    ----------
    test_case : list
        List of test_case stages (dicts with input, output and stage keys).
    """
    for index, stage in enumerate(test_case):
        if 'ignore' in stage and stage['ignore'] == 'yes':
            continue

        receiver_sockets[0].send(stage['input'], size=True)
        for output in stage['output']:
            response = receiver_sockets[0].receive(size=True).decode()
            if 'use_regex' in stage and stage['use_regex'] == 'yes':
                match = True if regex_match(output, response) else False
            else:
                match = (output == response)
            assert match, 'Failed test case stage {}: {}. Expected: {}. Response: {}' \
                .format(index + 1, stage['stage'], output, response)


def test_wazuh_db_create_agent(restart_wazuh, clean_registered_agents, configure_sockets_environment, connect_to_sockets_module):
    """Check that Wazuh DB creates the agent database when a query with a new agent ID is sent"""
    test = {'name': 'Create agent',
            'description': "Wazuh DB creates automatically the agent's database the first time a query with a new agent"
                           ' ID reaches it. Once the database is created, the query is processed as expected.',
            "test_case": [{'input': 'agent 999 syscheck integrity_check_left',
                           'output': ["err Invalid FIM query syntax, near 'integrity_check_left'"],
                           'stage': 'Syscheck - Agent does not exits yet'}]}
    test_wazuh_db_messages(clean_registered_agents, restart_wazuh, configure_sockets_environment, connect_to_sockets_module, test['test_case'])
    assert os.path.exists(os.path.join(WAZUH_PATH, 'queue', 'db', '999.db'))


def test_wazuh_db_timeout(configure_sockets_environment, connect_to_sockets_module,
                          pre_insert_packages, pre_set_sync_info):
    """Check that effectively the socket is closed after timeout is reached"""
    wazuh_db_send_sleep = 2

    command = 'agent 000 package get'
    receiver_sockets[0].send(command, size=True)
    # Waiting Wazuh-DB to process command
    time.sleep(wazuh_db_send_sleep)
    socket_closed = False
    cmd_counter = 0
    status = 'due'
    while not socket_closed and status == 'due':
        cmd_counter += 1
        response = receiver_sockets[0].receive(size=True).decode()
        if response == '':
            socket_closed = True
        else:
            status = response.split()[0]

    assert socket_closed, f"Socket never closed. Received {cmd_counter} commands. Last command: {response}"
