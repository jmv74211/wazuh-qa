'''
copyright: Copyright (C) 2015-2021, Wazuh Inc.

           Created by Wazuh, Inc. <info@wazuh.com>.

           This program is free software; you can redistribute it and/or modify it under the terms of GPLv2

type: integration

brief: File Integrity Monitoring (FIM) system watches selected files and triggering alerts when these
       files are modified. Specifically, these tests will check if the modifications made on files during
       the initial scan ('baseline') generate events when the scan is finished.
       The FIM capability is managed by the 'wazuh-syscheckd' daemon, which checks configured files
       for changes to the checksums, permissions, and ownership.

tier: 0

modules:
    - fim

components:
    - agent
    - manager

daemons:
    - wazuh-syscheckd

os_platform:
    - linux
    - windows

os_version:
    - Arch Linux
    - Amazon Linux 2
    - Amazon Linux 1
    - CentOS 8
    - CentOS 7
    - CentOS 6
    - Ubuntu Focal
    - Ubuntu Bionic
    - Ubuntu Xenial
    - Ubuntu Trusty
    - Debian Buster
    - Debian Stretch
    - Debian Jessie
    - Debian Wheezy
    - Red Hat 8
    - Red Hat 7
    - Red Hat 6
    - Windows 10
    - Windows 8
    - Windows 7
    - Windows Server 2019
    - Windows Server 2016
    - Windows Server 2012
    - Windows Server 2003
    - Windows XP

references:
    - https://documentation.wazuh.com/current/user-manual/capabilities/file-integrity/index.html
    - https://documentation.wazuh.com/current/user-manual/reference/ossec-conf/syscheck.html

pytest_args:
    - fim_mode:
        realtime: Enable real-time monitoring on Linux (using the 'inotify' system calls) and Windows systems.
        whodata: Implies real-time monitoring but adding the 'who-data' information.
    - tier:
        0: Only level 0 tests are performed, they check basic functionalities and are quick to perform.
        1: Only level 1 tests are performed, they check functionalities of medium complexity.
        2: Only level 2 tests are performed, they check advanced functionalities and are slow to perform.

tags:
    - fim_basic_usage
'''
import os
from time import time
import sys

import pytest
from wazuh_testing.fim import (LOG_FILE_PATH, REGULAR, callback_detect_event, callback_detect_end_scan, create_file,
                               generate_params)
from wazuh_testing.tools import PREFIX
from wazuh_testing.tools.configuration import load_wazuh_configurations, check_apply_test
from wazuh_testing.tools.monitoring import FileMonitor

# Marks

pytestmark = pytest.mark.tier(level=0)

# variables

test_directories = [os.path.join(PREFIX, 'testdir1'), os.path.join(PREFIX, 'testdir2')]

directory_str = ','.join(test_directories + [os.path.join(PREFIX, 'noexists')])

wazuh_log_monitor = FileMonitor(LOG_FILE_PATH)
test_data_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data')
configurations_path = os.path.join(test_data_path, 'wazuh_conf.yaml')
testdir1, testdir2 = test_directories

# configurations

conf_params = {'TEST_DIRECTORIES': directory_str, 'MODULE_NAME': __name__}
p, m = generate_params(extra_params=conf_params, modes=['scheduled', 'realtime'])

configurations = load_wazuh_configurations(configurations_path, __name__, params=p, metadata=m)


# fixtures

@pytest.fixture(scope='module', params=configurations)
def get_configuration(request):
    """Get configurations from the module."""
    return request.param


# tests

def callback_detect_event_before_end_scan(line):
    ended_scan = callback_detect_end_scan(line)
    if ended_scan is None:
        event = callback_detect_event(line)
        assert event is None, 'Event detected before end scan'
        return None
    else:
        return True


def extra_configuration_before_yield():
    for _ in range(1000):
        create_file(REGULAR, testdir1, f'test_{int(round(time() * 10 ** 6))}', content='')
        create_file(REGULAR, testdir2, f'test_{int(round(time() * 10 ** 6))}', content='')

pytest.mark.skipif(sys.platform == 'win32', reason="Blocked by wazuh/wazuh-qa#2174 - Refactor required")
def test_wait_until_baseline(get_configuration, configure_environment, restart_syscheckd):
    '''
    description: Check if FIM events are appearing after the 'baseline'. The log message
                 'File integrity monitoring scan ended' informs about the end of the first scan,
                 which generates the 'baseline'. For this purpose, the test creates a test file
                 while the initial scan is being performed. When the baseline has been generated
                 it checks if the FIM addition event has been triggered.

    wazuh_min_version: 4.2.0

    parameters:
        - get_configuration:
            type: fixture
            brief: Get configurations from the module.
        - configure_environment:
            type: fixture
            brief: Configure a custom environment for testing.
        - restart_syscheckd:
            type: fixture
            brief: Clear the 'ossec.log' file and start a new monitor.

    assertions:
        - Verify that a FIM addition event was generated during the initial scan.

    input_description: A test case (ossec_conf) is contained in external YAML file (wazuh_conf.yaml)
                       which includes configuration settings for the 'wazuh-syscheckd' daemon and, it
                       is combined with the testing directories to be monitored defined in this module.

    expected_output:
        - r'.*Sending FIM event: (.+)$'

    tags:
        - realtime
    '''
    check_apply_test({'ossec_conf'}, get_configuration['tags'])

    # Create a file during initial scan to check if the event is logged after the 'scan ended' message
    create_file(REGULAR, testdir1, f'test_{int(round(time() * 10 ** 6))}', content='')

    wazuh_log_monitor.start(timeout=120, callback=callback_detect_event_before_end_scan,
                            error_message='Did not receive expected event before end the scan')
