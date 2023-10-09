# Imports
import datetime
import logging
import os
import sys
from . import rt

def run(job_obj):
    logger = logging.getLogger('BL/RUN')
    workdir, newbldir, blstore = set_directories(job_obj)
    pr_repo_loc, repo_dir_str = clone_pr_repo(job_obj, workdir)
    bldate = get_bl_date(job_obj, pr_repo_loc)
    bldir = f'{blstore}/main-{bldate}/{job_obj.compiler.upper()}'
    bldirbool = check_for_bl_dir(bldir, job_obj)
    run_regression_test(job_obj, pr_repo_loc)
    post_process(job_obj, pr_repo_loc, repo_dir_str, newbldir, bldir, bldate, blstore)


def set_directories(job_obj):
    logger = logging.getLogger('BL/SET_DIRECTORIES')
    if job_obj.machine == 'hera':
        rt_dir = '/scratch1/BMC/gmtb/CCPP_regression_testing/NCAR_ufs-weather-model/'
        blstore = f'{rt_dir}/baselines'
        newbldir = f'{rt_dir}/FV3_RT/'\
                 f'REGRESSION_TEST_{job_obj.compiler.upper()}'
    elif job_obj.machine == 'cheyenne':
        workdir = '/glade/scratch/epicufsrt/GMTB/ufs-weather-model/RT/auto_RT/Pull_Requests'
        blstore = '/glade/scratch/epicufsrt/GMTB/ufs-weather-model/RT/NCAR'
        newbldir = '/glade/scratch/epicufsrt/GMTB/ufs-weather-model/RT/'\
                 f'REGRESSION_TEST_{job_obj.compiler.upper()}'
    else:
        logger.critical(f'Machine {job_obj.machine} is not supported for this job')
        raise KeyError

    workdir = job_obj.workdir

    logger.info(f'machine: {job_obj.machine}')
    logger.info(f'workdir: {workdir}')
    logger.info(f'blstore: {blstore}')
    logger.info(f'newbldir: {newbldir}')

    return workdir, newbldir, blstore


def check_for_bl_dir(bldir, job_obj):
    logger = logging.getLogger('BL/CHECK_FOR_BL_DIR')
    logger.info('Checking if baseline directory exists')
    if os.path.exists(bldir):
        logger.critical(f'Baseline dir: {bldir} exists. It should not, yet.')
        job_obj.comment_text_append(f'[BL] ERROR: Baseline location exists before '
                                    f'creation:\n{bldir}')
        raise FileExistsError
    return False


def create_bl_dir(bldir, job_obj):
    logger = logging.getLogger('BL/CREATE_BL_DIR')
    if not check_for_bl_dir(bldir, job_obj):
        os.makedirs(bldir)
        if not os.path.exists(bldir):
            logger.critical(f'Someting went wrong creating {bldir}')
            raise FileNotFoundError


#def get_bl_date(job_obj):
#    logger = logging.getLogger('BL/GET_BL_DATE')
#    for line in job_obj.preq_dict['preq'].body.splitlines():
#        if 'BL_DATE:' in line:
#            bldate = line
#            bldate = bldate.replace('BL_DATE:', '')
#            bldate = bldate.replace(' ', '')
#            if len(bldate) != 8:
#                print(f'Date: {bldate} is not formatted YYYYMMDD')
#                raise ValueError
#            logger.info(f'BL_DATE: {bldate}')
#            bl_format = '%Y%m%d'
#            try:
#                datetime.datetime.strptime(bldate, bl_format)
#            except ValueError:
#                logger.info(f'Date {bldate} is not formatted YYYYMMDD')
#                raise ValueError
#            return bldate
#    logger.critical('"BL_DATE:YYYYMMDD" needs to be in the PR body.'\
#                    'On its own line. Stopping')
#    raise ValueError


def run_regression_test(job_obj, pr_repo_loc):
    logger = logging.getLogger('BL/RUN_REGRESSION_TEST')
    if job_obj.compiler == 'gnu':
        rt_command = [[f'export RT_COMPILER="{job_obj.compiler}" && cd tests '
                       '&& /bin/bash --login ./rt.ncar.sh -e -c -l rt_gnu.conf -p {job_obj.machine}',
                       pr_repo_loc]]
    elif job_obj.compiler == 'intel':
        rt_command = [[f'export RT_COMPILER="{job_obj.compiler}" && cd tests '
                       '&& /bin/bash --login ./rt.ncar.sh -e -c -p {job_obj.machine}', pr_repo_loc]]
    job_obj.run_commands(logger, rt_command)


def remove_pr_data(job_obj, pr_repo_loc, repo_dir_str, rt_dir):
    logger = logging.getLogger('BL/REMOVE_PR_DATA')
    rm_command = [
                 [f'rm -rf {rt_dir}', pr_repo_loc],
                 [f'rm -rf {repo_dir_str}', pr_repo_loc]
                 ]
    job_obj.run_commands(logger, rm_command)


def clone_pr_repo(job_obj, workdir):
    ''' clone the GitHub pull request repo, via command line '''
    logger = logging.getLogger('BL/CLONE_PR_REPO')
    repo_name = job_obj.preq_dict['preq'].head.repo.name
    branch = job_obj.preq_dict['preq'].head.ref
    #git_url = job_obj.preq_dict['preq'].head.repo.html_url.split('//')
    #git_url = f'{git_url[0]}//${{ghapitoken}}@{git_url[1]}'
    #logger.debug(f'GIT URL: {git_url}')
    git_ssh_url = job_obj.preq_dict['preq'].head.repo.ssh_url
    logger.debug(f'GIT SSH_URL: {git_ssh_url}')
    logger.info('Starting repo clone')
    repo_dir_str = f'{workdir}/'\
                   f'{str(job_obj.preq_dict["preq"].id)}/'\
                   f'{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}'
    pr_repo_loc = f'{repo_dir_str}/{repo_name}'
    job_obj.comment_text_append(f'[BL] Repo location: {pr_repo_loc}')
    create_repo_commands = [
        [f'mkdir -p "{repo_dir_str}"', os.getcwd()],
        [f'git clone -b {branch} {git_ssh_url}', repo_dir_str],
        ['git submodule update --init --recursive',
         f'{repo_dir_str}/{repo_name}'],
        ['git config user.email "kavulich@ucar.edu"',
         f'{repo_dir_str}/{repo_name}'],
        ['git config user.name "mkavulich"',
         f'{repo_dir_str}/{repo_name}']
    ]

    job_obj.run_commands(logger, create_repo_commands)

    logger.info('Finished repo clone')
    return pr_repo_loc, repo_dir_str


def post_process(job_obj, pr_repo_loc, repo_dir_str, newbldir, bldir, bldate, blstore):
    logger = logging.getLogger('BL/MOVE_RT_LOGS')
    rt_log = f'tests/RegressionTests_{job_obj.machine}'\
             f'.{job_obj.compiler}.log'
    filepath = f'{pr_repo_loc}/{rt_log}'
    rt_dir, logfile_pass = process_logfile(job_obj, filepath)
    if logfile_pass:
        create_bl_dir(bldir, job_obj)
        move_bl_command = [[f'mv {newbldir}/* {bldir}/', pr_repo_loc]]
        job_obj.run_commands(logger, move_bl_command)
        job_obj.comment_text_append('[BL] Baseline creation and move successful')
        logger.info('Starting RT Job')
        rt.run(job_obj)
        logger.info('Finished with RT Job')


def get_bl_date(job_obj, pr_repo_loc):
    logger = logging.getLogger('BL/UPDATE_RT_NCAR_SH')
    BLDATEFOUND = False
    with open(f'{pr_repo_loc}/tests/rt.ncar.sh', 'r') as f:
        for line in f:
            if 'BL_DATE=' in line:
                logger.info('Found BL_DATE in line')
                BLDATEFOUND = True
                bldate = line
                bldate = bldate.rstrip('\n')
                bldate = bldate.replace('BL_DATE=', '')
                bldate = bldate.strip(' ')
                logger.info(f'bldate is "{bldate}"')
                logger.info(f'Type bldate: {type(bldate)}')
                bl_format = '%Y%m%d'
                try:
                    datetime.datetime.strptime(bldate, '%Y%m%d')
                except ValueError:
                    logger.info(f'Date {bldate} is not formatted YYYYMMDD')
                    raise ValueError
    if not BLDATEFOUND:
        job_obj.comment_text_append('[BL] ERROR: Variable "BL_DATE" not found in rt.ncar.sh.')
        job_obj.job_failed(logger, 'get_bl_date()')
    logger.info('Finished get_bl_date')

    return bldate


def process_logfile(job_obj, logfile):
    logger = logging.getLogger('BL/PROCESS_LOGFILE')
    rt_dir = []
    fail_string_list = ['Test', 'failed']
    if os.path.exists(logfile):
        with open(logfile) as f:
            for line in f:
                if all(x in line for x in fail_string_list):
                # if 'FAIL' in line and 'Test' in line:
                    job_obj.comment_text_append(f'[BL] Error: {line.rstrip(chr(10))}')
                elif 'working dir' in line and not rt_dir:
                    logger.info(f'Found "working dir" in line: {line}')
                    rt_dir = os.path.split(line.split()[-1])[0]
                    logger.info(f'It is: {rt_dir}')
                elif 'SUCCESSFUL' in line:
                    logger.info('RT Successful')
                    return rt_dir, True
        logger.critical(f'Log file exists but is not complete')
        job_obj.job_failed(logger, f'{job_obj.preq_dict["action"]}')
    else:
        logger.critical(f'Could not find {job_obj.machine}'
                        f'.{job_obj.compiler} '
                        f'{job_obj.preq_dict["action"]} log')
        raise FileNotFoundError
