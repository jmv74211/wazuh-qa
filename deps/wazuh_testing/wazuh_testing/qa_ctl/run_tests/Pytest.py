from datetime import datetime
import tempfile
import os

from wazuh_testing.qa_ctl.run_tests.TestResult import TestResult
from wazuh_testing.qa_ctl.provisioning.ansible.AnsibleRunner import AnsibleRunner
from wazuh_testing.qa_ctl.provisioning.ansible.AnsibleTask import AnsibleTask
from wazuh_testing.qa_ctl.run_tests.Test import Test


class Pytest(Test):
    """The class encapsulates the execution options of a specified set of tests and allows running them on the
        remote host

    Args:
        tests_result_path(str): Path to the directory where the reports will be stored in the local machine
        tests_path (str): Path to the set of tests to be executed
        tests_run_dir (str): Path to the directory from where the tests are going to be executed
        tiers (list(int), []): List of tiers to be executed
        stop_after_first_failure (boolean, False): If set to true then the tests' execution will stop after the first
                                                  failure
        keyword_expression (str, None): Regular expression allowing to execute all the tests that match said expression
        traceback (str, 'auto): Set the traceback mode (auto/long/short/line/native/no)
        dry_run(boolean, False): If set to True the flag --collect-only is added so no test will be executed, only
                                collected
        custom_args(list(str), []): set of key pair values to be added as extra args to the test execution command
        verbose_level(boolean, False): if set to true, verbose flag is added to test execution command
        log_level(str, None): Log level to be set
        markers(list(str), []): Set of markers to be added to the test execution command
        hosts(list(), ['all']): List of hosts aliases where the tests will be runned

    Attributes:
        tests_path (str): Path to the set of tests to be executed
        tests_run_dir (str): Path to the directory from where the tests are going to be executed
        tier (srt, None): List of tiers to be executed
        stop_after_first_failure (boolean, False): If set to true then the tests' execution will stop after the first
                                                  failure
        keyword_expression (str, None): Regular expression allowing to execute all the tests that match said expression
        traceback (str, None): Set the traceback mode (auto/long/short/line/native/no)
        dry_run(boolean, False): If set to True the flag --collect-only is added so no test will be executed, only
                                collected
        custom_args(dict, None): set of key pair values to be added as extra args to the test execution command
        verbose_level(boolean, False): if set to true, verbose flag is added to test execution command
        log_level(str, None): Log level to be set
        markers(list(str), None): Set of markers to be added to the test execution command
        hosts(list(), ['all']): List of hosts aliases where the tests will be runned

    """

    RUN_PYTEST = 'python3 -m pytest '

    def __init__(self, tests_result_path, tests_path, tests_run_dir, tiers=[], stop_after_first_failure=False,
                 keyword_expression=None, traceback='auto', dry_run=False, custom_args=[], verbose_level=False,
                 log_level=None, markers=[], hosts=['all']):
        self.tiers = tiers
        self.stop_after_first_failure = stop_after_first_failure
        self.keyword_expression = keyword_expression
        self.traceback = traceback
        self.dry_run = dry_run
        self.custom_args = custom_args
        self.verbose_level = verbose_level
        self.log_level = log_level
        self.markers = markers
        self.hosts = hosts
        super().__init__(tests_path, tests_run_dir, tests_result_path)

    def run(self, ansible_inventory_path):
        """Executes the current test with the specified options defined in attributes and bring back the reports
            to the host machine.

        Args:
            ansible_inventory_path (str): Path to ansible inventory file
        """
        # Paths used below
        assets_folder = 'assets/'
        assets_zip = "assets.zip"
        html_report_file_name = f"test_report-{datetime.now()}.html"
        plain_report_file_name = f"plain_report-{datetime.now()}.txt"
        playbook_file_path = os.path.join(tempfile.gettempdir(), 'playbook_file.yaml')
        plain_report_file_path = os.path.join(self.tests_run_dir, plain_report_file_name)
        html_report_file_path = os.path.join(self.tests_run_dir, html_report_file_name)
        assets_dest_directory = os.path.join(self.tests_result_path, assets_folder)
        assets_src_directory = os.path.join(self.tests_run_dir, assets_folder)
        zip_src_path = os.path.join(self.tests_run_dir, assets_zip)
        zip_dest_path = os.path.join(self.tests_result_path, assets_zip)

        if self.tests_result_path is None:
            self.tests_result_path = os.path.join(tempfile.gettempdir(), '')
        else:
            self.tests_result_path = os.path.join(self.tests_result_path, '')

        pytest_command = self.RUN_PYTEST

        if self.keyword_expression:
            pytest_command += os.path.join(self.tests_path, self.keyword_expression) + " "
        else:
            pytest_command += self.tests_path + " "
        if self.tiers:
            pytest_command += ' '.join([f"--tier={tier}" for tier in self.tiers]) + ' '
        if self.dry_run:
            pytest_command += '--collect-only '
        if self.stop_after_first_failure:
            pytest_command += '-x '
        if self.verbose_level:
            pytest_command += '--verbose '
        if self.custom_args:
            for custom_arg in self.custom_args:
                pytest_command += f"--metadata {custom_arg} "
        if self.log_level:
            pytest_command += f"--log-level={self.log_level} "
        if self.traceback:
            pytest_command += f"--tb={self.traceback} "
        if self.markers:
            pytest_command += f"-m {' '.join(self.markers)} "

        pytest_command += f"--html='{self.tests_run_dir}/{html_report_file_name}'"

        execute_test_task = {'name': f"Launch pytest in {self.tests_run_dir}",
                             'shell': pytest_command, 'vars':
                             {'chdir': self.tests_run_dir},
                             'register': 'test_output',
                             'ignore_errors': 'yes'}

        create_plain_report = {'name': f"Create plain report file in {plain_report_file_path}",
                               'copy': {'dest': plain_report_file_path,
                                        'content': "{{test_output.stdout}}"}}

        fetch_plain_report = {'name': f"Move {plain_report_file_name} from "
                              f"{plain_report_file_path} to {self.tests_result_path}",
                              'fetch': {'src': plain_report_file_path,
                                        'dest': self.tests_result_path, 'flat': 'yes'}}

        fetch_html_report = {'name': f"Move {html_report_file_name} from {html_report_file_path}"
                             f" to {self.tests_result_path}",
                             'fetch': {'src': html_report_file_path,
                                       'dest': self.tests_result_path, 'flat': 'yes'}}

        create_assets_directory = {'name': f"Create {assets_dest_directory} directory",
                                   'local_action': {'module': 'ansible.builtin.file',
                                                    'path': assets_dest_directory,
                                                    'state': 'directory'},
                                   'become': False}

        compress_assets_folder = {'name': "Compress assets folder",
                                  'community.general.archive': {'path': assets_src_directory,
                                                                'dest': zip_src_path,
                                                                'format': 'zip'}}

        fetch_compressed_assets = {'name': f"Copy compressed assets from {zip_src_path} to {self.tests_result_path}",
                                   'fetch': {'src': zip_src_path,
                                             'dest': self.tests_result_path, 'flat': 'yes'}}

        uncompress_assets = {'name': f"Uncompress {assets_zip} in {assets_dest_directory}",
                             'local_action': {'module': 'unarchive',
                                              'src': zip_dest_path,
                                              'dest': assets_dest_directory},
                             'become': False}

        ansible_tasks = [AnsibleTask(execute_test_task), AnsibleTask(create_plain_report),
                         AnsibleTask(fetch_plain_report), AnsibleTask(fetch_html_report),
                         AnsibleTask(create_assets_directory), AnsibleTask(compress_assets_folder),
                         AnsibleTask(fetch_compressed_assets), AnsibleTask(uncompress_assets)]

        playbook_parameters = {'become': True, 'tasks_list': ansible_tasks, 'playbook_file_path':
                               playbook_file_path, "hosts": self.hosts}

        AnsibleRunner.run_ephemeral_tasks(ansible_inventory_path, playbook_parameters, raise_on_error=False)

        self.result = TestResult(html_report_file_path=os.path.join(self.tests_result_path, html_report_file_name),
                                 plain_report_file_path=os.path.join(self.tests_result_path, plain_report_file_name))
