"""Automation of UFS Regression Testing

This script automates the process of UFS regression testing for code managers
at NOAA-EMC

This script should be started through rt_auto.sh so that env vars are set up
prior to start.
"""
from github import Github as gh
import argparse
import datetime
import subprocess
import re
import os
from glob import glob
import logging
import importlib
from shutil import rmtree
import yaml

class GHInterface:
    '''
    This class stores information for communicating with GitHub
    ...

    Attributes
    ----------
    GHACCESSTOKEN : str
      API token to autheticate with GitHub
    client : pyGitHub communication object
      The connection to GitHub to make API requests
    '''

    def __init__(self):
        self.logger = logging.getLogger('GHINTERFACE')

        filename = 'accesstoken'

        if os.path.exists(filename):
            if oct(os.stat(filename).st_mode)[-3:] != 600:
                with open(filename) as f:
                    os.environ['ghapitoken'] = f.readline().strip('\n')
            else:
                raise Exception('File permission needs to be "600" ')
        else:
            raise FileNotFoundError('Cannot find file "accesstoken"')

        try:
            self.client = gh(os.getenv('ghapitoken'))
        except Exception as e:
            self.logger.critical(f'Exception is {e}')
            raise(e)


def set_action_from_label(machine, actions, label):
    ''' Match the label that initiates a job with an action in the dict'''
    # <machine>-<compiler>-<test> i.e. hera-gnu-RT
    logger = logging.getLogger('MATCH_LABEL_WITH_ACTIONS')
    logger.info('Setting action from Label')
    split_label = label.name.split('-')
    # Make sure it has three parts
    if len(split_label) != 3:
        return False, False
    # Break the parts into their variables
    label_machine = split_label[0]
    label_compiler = split_label[1]
    label_action = split_label[2]
    # check machine name matches
    if not re.match(label_machine, machine):
        return False, False
    # Compiler must be intel or gnu
    if not str(label_compiler) in ["intel", "gnu"]:
        return False, False
    action_match = next((action for action in actions
                         if re.match(action, label_action)), False)

    logging.info(f'Compiler: {label_compiler}, Action: {action_match}')
    return label_compiler, action_match

def delete_pr_dirs(each_pr, machine, workdir):
    ids = [str(pr.id) for pr in each_pr]
    logging.debug(f'ids are: {ids}')
    dirs = [x.split('/')[-2] for x in glob(f'{workdir}/*/')]
    logging.debug(f'dirs: {dirs}')
    for dir in dirs:
        if dir != 'pr':
            logging.debug(f'Checking dir {dir}')
            if not dir in ids:
                logging.debug(f'ID NOT A MATCH, DELETING {dir}')
                delete_rt_dirs(dir, machine, workdir)
                if os.path.isdir(f'{workdir}/{dir}'):
                    logging.debug(f'Executing rmtree in "{workdir}/{dir}"')
                    rmtree(f'{workdir}/{dir}')
                else:
                    logging.debug(f'{workdir}/{dir} does not exist, not attempting to remove')
            else:
                logging.debug(f'ID A MATCH, NOT DELETING {dir}')
    # job_obj.preq_dict["preq"].id
    

def delete_rt_dirs(in_dir, machine, workdir):
    globdir = f'{workdir}/{in_dir}/**/compile_*.log'
    logging.debug(f'globdir: {globdir}')
    logfiles = glob(globdir, recursive=True)
    if not logfiles:
      return
    logging.debug(f'logfiles: {logfiles}')
    matches = []
    for logfile in logfiles:
        with open(logfile, "r") as fp:
            lines = [line.split('/') for line in fp if 'rt_' in line]
            lines = list(set([item for sublist in lines for item in sublist]))
            lines = [s for s in lines if 'rt_' in s and '\n' not in s]
            if lines:
                matches.append(lines)
    logging.debug(f'lines: {lines}')
    matches = list(set([item for sublist in matches for item in sublist]))
    logging.debug(f'matches: {matches}')
    for match in matches:
        if os.path.isdir(f'{rt_dir}/{match}'):
            logging.debug(f'Executing rmtree in "{rt_dir}/{match}"')
            rmtree(f'{rt_dir}/{match}')
        else:
            logging.debug(f'{rt_dir}/{match} does not exist, not attempting to remove')


def get_preqs_with_actions(repos, args, ghinterface_obj, actions, git_cfg):
    ''' Create list of dictionaries of a pull request
        and its machine label and action '''
    logger = logging.getLogger('GET_PREQS_WITH_ACTIONS')

    logger.info('Getting Pull Requests with Actions')
    gh_preqs = [ghinterface_obj.client.get_repo(repo['address'])
                .get_pulls(state='open', sort='created', base=repo['base'])
                for repo in repos]
    each_pr = [preq for gh_preq in gh_preqs for preq in gh_preq]
    delete_pr_dirs(each_pr, args.machine, args.workdir)
    preq_labels = [{'preq': pr, 'label': label} for pr in each_pr
                   for label in pr.get_labels()]

    jobs = []
    # return_preq = []
    for pr_label in preq_labels:
        compiler, match = set_action_from_label(args.machine, actions,
                                                pr_label['label'])
        if match:
            pr_label['action'] = match
            # return_preq.append(pr_label.copy())
            jobs.append(Job(pr_label.copy(), ghinterface_obj, args, compiler, git_cfg))

    return jobs


class Job:
    '''
    This class stores all information needed to run jobs on this machine.
    This class provides all methods needed to run all jobs.
    ...

    Attributes
    ----------
    preq_dict: dict
        Dictionary of all data that comes from the GitHub pull request
    ghinterface_obj: object
        An interface to GitHub setup through class GHInterface
    machine: dict
        Information about the machine the jobs will be running on
        provided by the bash script
    '''

    def __init__(self, preq_dict, ghinterface_obj, args, compiler, gitargs):
        self.logger = logging.getLogger('JOB')
        self.preq_dict = preq_dict
        self.job_mod = importlib.import_module(
                       f'jobs.{self.preq_dict["action"].lower()}')
        self.ghinterface_obj = ghinterface_obj
        self.clargs = args
        self.compiler = compiler
        self.gitargs = gitargs
        self.comment_text = '***Automated RT Failure Notification***\n'
        self.failed_tests = []

    def comment_text_append(self, newtext):
        self.comment_text += f'{newtext}\n'

    def remove_pr_label(self):
        ''' Removes the PR label that initiated the job run from PR '''
        self.logger.info(f'Removing Label: {self.preq_dict["label"]}')
#        self.preq_dict['preq'].remove_from_labels(self.preq_dict['label'])

    def check_label_before_job_start(self):
        # LETS Check the label still exists before the start of the job in the
        # case of multiple jobs
        label_to_check = f'{self.clargs.machine}'\
                         f'-{self.compiler}'\
                         f'-{self.preq_dict["action"]}'
        labels = self.preq_dict['preq'].get_labels()
        label_match = next((label for label in labels
                            if re.match(label.name, label_to_check)), False)

        return label_match

    def run_commands(self, logger, commands_with_cwd):
        for command, in_cwd in commands_with_cwd:
            logger.info(f'Running `{command}`')
            logger.info(f'in location "{in_cwd}"')
            try:
                output = subprocess.Popen(command, shell=True, cwd=in_cwd,
                                          stdout=subprocess.PIPE,
                                          stderr=subprocess.STDOUT)
            except Exception as e:
                self.job_failed(logger, 'subprocess.Popen')
            else:
                try:
                    out, err = output.communicate()
                    out = [] if not out else out.decode('utf8').split('\n')
                    logger.info(out)
                except Exception as e:
                    err = [] if not err else err.decode('utf8').split('\n')
                    self.job_failed(logger, f'Command {command}', exception=e,
                                    STDOUT=True, out=out, err=err)
                else:
                    logger.info(f'Finished running: {command}')

    def run(self):
        logger = logging.getLogger('JOB/RUN')
        logger.info(f'Starting Job: {self.preq_dict["label"]}')
        self.comment_text_append(newtext=f'Machine: {self.clargs.machine}')
        self.comment_text_append(f'Compiler: {self.compiler}')
        self.comment_text_append(f'Job: {self.preq_dict["action"]}')
        if self.check_label_before_job_start():
            try:
                logger.info('Calling remove_pr_label')
                self.remove_pr_label()
                logger.info('Calling Job to Run')
                self.job_mod.run(self)
            except Exception:
                self.job_failed(logger, 'run()')
                logger.info('Sending comment text')
#                self.send_comment_text()
                raise
        else:
            logger.info(f'Cannot find label {self.preq_dict["label"]}')

    def send_comment_text(self):
        logger = logging.getLogger('JOB/SEND_COMMENT_TEXT')
        logger.info(f'Comment Text: {self.comment_text}')
        self.comment_text_append('Please make changes and add '
                                 'the following label back: '
                                 f'{self.clargs.machine}'
                                 f'-{self.compiler}'
                                 f'-{self.preq_dict["action"]}')

        self.preq_dict['preq'].create_issue_comment(self.comment_text)

    def job_failed(self, logger, job_name, exception=None, STDOUT=False,
                   out=None, err=None):
        logger.critical(f'{job_name} FAILED.')

        if STDOUT:
            logger.critical(f'STDOUT: {[item for item in out if not None]}')
            logger.critical(f'STDERR: {[eitem for eitem in err if not None]}')
        if exception is not None:
            raise

def setup_env(git_cfg):
    # Dictionary of GitHub repositories to check

    if not git_cfg.get('repo'):
        git_cfg['repo'] = 'ufs-weather-model'
    if not git_cfg.get('org'):
        git_cfg['org'] = 'ufs-community'
    if not git_cfg.get('base'):
        git_cfg['base'] = 'main'

    repo_dict = [{
        'name': git_cfg['repo'],
        'address': f"{git_cfg['org']}/{git_cfg['repo']}",
        'base': git_cfg['base']
    }]

    # Approved Actions
    action_list = ['RT', 'BL']

    return repo_dict, action_list


def main():

    # handle logging
    log_filename = f'rt_auto_'\
                   f'{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}.log'
    logging.basicConfig(filename=log_filename, filemode='w',
                        level=logging.INFO)
    logger = logging.getLogger('MAIN')
    logger.info('Starting Script')

    parser = argparse.ArgumentParser()
    parser.add_argument('-m','--machine', help='current machine name', default='')
    parser.add_argument('-a','--account', help='account to charge', default='')
    parser.add_argument('-w','--workdir', help='directory where tests will be staged and run', default='')
    parser.add_argument('-b','--baseline', help='directory where baseline data is stored', default='')
    parser.add_argument('-e','--envfile', help='environment file sourced by rt.sh', default='')
    parser.add_argument('--new_baseline', help='if creating a new baseline, directory where new baseline data is stored', default='')
    parser.add_argument('-y','--yamlfile', help='yaml file to load additional arguments from', default='rt_auto.yaml')
    parser.add_argument('-d','--debug', help='Set logging to more verbose output', action='store_true')
    parser.add_argument('--additional_args', help='Additional arguments to pass to rt.sh', default='')

    args = parser.parse_args()
    # Get command-line arguments as a dictionary
    dargs = vars(args)

    # Load yamlfile for additional arguments
    with open(args.yamlfile) as f:
        cfg = yaml.safe_load(f)

    # For each mandatory command-line argument, if not provided, check yaml file, and fail if not there either
    mandatory = ['machine','account']
    for md in mandatory:
        if not dargs[md]:
            if not cfg['args'].get(md):
                raise argparse.ArgumentTypeError(f'"{md}" is a required argument; you must provide it via command line or yaml config file "{args.yamlfile}"')

    # For each optional command-line argument, if it was not provided, attempt to get it from the yaml file
    for arg in dargs:
        if arg in mandatory:
            pass
        if not dargs[arg]:
            if cfg['args'].get(arg):
                logger.info(f"Reading argument from yaml file:\n{arg} = {cfg['args'][arg]}")
                dargs[arg] = cfg['args'][arg]

    if args.debug:
        logger.info('Setting logging level to debug')
        for handler in logger.handlers:
            handler.setLevel(logging.DEBUG)


    # setup environment
    logger.info('Getting the environment setup')
    repos, actions = setup_env(cfg['git']['github'])

    # setup interface with GitHub
    logger.info('Setting up GitHub interface.')
    ghinterface_obj = GHInterface()

    # get all pull requests from the GitHub object
    # and turn them into Job objects
    logger.info('Getting all pull requests, '
                'labels and actions applicable to this machine.')
    jobs = get_preqs_with_actions(repos, args, ghinterface_obj, actions, cfg['git'])
    [job.run() for job in jobs]

    logger.info('Script Finished')


if __name__ == '__main__':
    main()
