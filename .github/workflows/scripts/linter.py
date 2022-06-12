
'''Run a code format analysis for the specified files, indicated by a data file passed to this script.

The analyses performed are as follows:

- Python: pycodestyle
'''
import os
import sys
import subprocess
import argparse


def get_script_parameters():
    """Process the script parameters

    Returns:
        ArgumentParser: Parameters and their values
    """
    parser = argparse.ArgumentParser()

    parser.add_argument('--file', '-f', type=str, action='store', required=False, dest='file',
                        help='Path with file changes in CSV format')

    script_parameters = parser.parse_args()

    return script_parameters


def get_update_files(data_file):
    """Read the file data and parse it to get the updated files.

    Args:
        data_file (str): Data file path that contains the updated files data in CSV format.

    Returns:
        list(str): Updated files list.
    """
    # Check if the specified file exists
    if not os.path.exists(data_file):
        raise Exception(f"Could not find the {data_file} data file")

    # Read the file content
    with open(data_file) as opened_file:
        data_file_content = opened_file.read()

    # Check if the file content is empty
    if data_file_content == '':
        raise Exception(f"{data_file} is empty")

    return data_file_content.replace('\n', '').split(',')


def get_python_files(updated_files):
    """Parse the updated files list and get only the python ones.

    Args:
        updated_files (list(str)): Updated files list

    Returns:
        list(str): Updated python files list.
    """
    return [python_file for python_file in updated_files if '.py' in python_file]


def run_python_linter(python_files):
    """Run the python linter process

    Args:
        python_files (list(str)): Python files list to process.

    Returns:
        int: Status code result of python linting
    """
    if len(python_files) == 0:
        print('No python files were found. Skipping python linter analysis')
        return 0

    return subprocess.run(['pycodestyle', '--max-line-length=120', ' '.join(python_files)]).returncode


def main():
    script_parameters = get_script_parameters()

    # Get updated files
    updated_files = get_update_files(script_parameters.file)

    # Get python files
    python_files = get_python_files(updated_files)

    # Run the python linter analysis process
    python_linter_status = run_python_linter(python_files)

    if python_linter_status != 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
