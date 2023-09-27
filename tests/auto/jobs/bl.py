# Imports
import datetime
import logging
import os
import sys
from . import rt

def run(job_obj):
    logger = logging.getLogger('BL/RUN')
    new_baseline, blstore = set_directories(job_obj)
    pr_repo_loc, repo_dir_str = clone_pr_repo(job_obj)
    bldate = get_bl_date(job_obj, pr_repo_loc)
    bldir = f'{blstore}/main-{bldate}/{job_obj.compiler.upper()}'
    bldirbool = check_for_bl_dir(bldir, job_obj)
    run_regression_test(job_obj, pr_repo_loc)
    post_process(job_obj, pr_repo_loc, repo_dir_str, new_baseline, bldir, bldate, blstore)


def set_directories(job_obj):
    logger = logging.getLogger('BL/SET_DIRECTORIES')
    workdir = ''
    blstore = ''
    new_baseline = ''
    machine = job_obj.clargs.machine
    if machine == 'hera':
        rt_dir = '/scratch1/NCEPDEV/nems/emc.nemspara/'
        workdir = f'{rt_dir}/autort/pr'
        blstore = f'{rt_dir}/RT/NEMSfv3gfs'
        new_baseline = f'{rt_dir}/FV3_RT/'\
                 f'REGRESSION_TEST_{job_obj.compiler.upper()}'
    elif machine == 'jet':
        rt_dir = '/lfs4/HFIP/h-nems/emc.nemspara/'
        workdir = f'{rt_dir}/autort/pr'
        blstore = f'{rt_dir}/RT/NEMSfv3gfs'
        new_baseline = '{rt_dir}/RT_BASELINE/'\
                 f'emc.nemspara/FV3_RT/REGRESSION_TEST_{job_obj.compiler.upper()}'
    elif machine == 'gaea':
        workdir = '/lustre/f2/pdata/ncep/emc.nemspara/autort/pr'
        blstore = '/lustre/f2/pdata/ncep_shared/emc.nemspara/RT/NEMSfv3gfs'
        new_baseline = '/lustre/f2/scratch/emc.nemspara/FV3_RT/'\
                 f'REGRESSION_TEST_{job_obj.compiler.upper()}'
    elif machine == 'orion':
        workdir = '/work/noaa/nems/emc.nemspara/autort/pr'
        blstore = '/work/noaa/nems/emc.nemspara/RT/NEMSfv3gfs'
        new_baseline = '/work/noaa/stmp/bcurtis/stmp/bcurtis/FV3_RT/'\
                 f'REGRESSION_TEST_{job_obj.compiler.upper()}'
    elif machine == 'cheyenne':
        workdir = '/glade/scratch/dtcufsrt/autort/tests/auto/pr'
        blstore = '/glade/p/ral/jntp/GMTB/ufs-weather-model/RT/NEMSfv3gfs'
        new_baseline = '/glade/scratch/dtcufsrt/FV3_RT/'\
                 f'REGRESSION_TEST_{job_obj.compiler.upper()}'

    if not job_obj.clargs.workdir:
        job_obj.workdir = workdir
    if job_obj.clargs.baseline:
        blstore = job_obj.clargs.baseline
    if job_obj.clargs.new_baseline:
        new_baseline = job_obj.clargs.new_baseline

    logger.info(f'machine: {machine}')
    logger.info(f'workdir: {job_obj.workdir}')
    logger.info(f'blstore: {blstore}')
    logger.info(f'new_baseline: {new_baseline}')

    if not job_obj.workdir or not blstore or not new_baseline:
        logger.critical(f'One of workdir, blstore, or new_baseline has not been specified')
        logger.critical(f'Provide these on the command line or specify a supported machine')
        raise KeyError


    return new_baseline, blstore


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


def run_regression_test(job_obj, pr_repo_loc):
    logger = logging.getLogger('BL/RUN_REGRESSION_TEST')

    rt_command = 'cd tests'
    rt_command += f' && export RT_COMPILER="{job_obj.compiler}"'
    if job_obj.workdir:
        rt_command += f' && export RUNDIR_ROOT={job_obj.workdir}'
    rt_command += f' && /bin/bash --login ./rt.sh -e -a {job_obj.clargs.account} -c -p {job_obj.clargs.machine} -n control_p8 intel'
    if job_obj.compiler == 'gnu':
        rt_command += f' -l rt_gnu.conf'
    if job_obj.clargs.envfile:
        rt_command += f' -s {job_obj.clargs.envfile}'
    rt_command += f' {job_obj.clargs.additional_args}'

    job_obj.run_commands(logger, [[rt_command, pr_repo_loc]])


def remove_pr_data(job_obj, pr_repo_loc, repo_dir_str, rt_dir):
    logger = logging.getLogger('BL/REMOVE_PR_DATA')
    rm_command = [
                 [f'rm -rf {rt_dir}', pr_repo_loc],
                 [f'rm -rf {repo_dir_str}', pr_repo_loc]
                 ]
    job_obj.run_commands(logger, rm_command)


def clone_pr_repo(job_obj):
    ''' clone the GitHub pull request repo, via command line '''
    logger = logging.getLogger('BL/CLONE_PR_REPO')
    repo_name = job_obj.preq_dict['preq'].head.repo.name
    branch = job_obj.preq_dict['preq'].head.ref
    git_ssh_url = job_obj.preq_dict['preq'].head.repo.ssh_url
    logger.debug(f'GIT SSH_URL: {git_ssh_url}')
    logger.info('Starting repo clone')
    repo_dir_str = f'{job_obj.workdir}/'\
                   f'{str(job_obj.preq_dict["preq"].id)}/'\
                   f'{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}'
    pr_repo_loc = f'{repo_dir_str}/{repo_name}'
    job_obj.comment_text_append(f'[BL] Repo location: {pr_repo_loc}')
    create_repo_commands = [
        [f'mkdir -p "{repo_dir_str}"', os.getcwd()],
        [f'git clone -b {branch} {git_ssh_url}', repo_dir_str],
        ['git submodule update --init --recursive',
         f'{repo_dir_str}/{repo_name}'],
        [f'git config user.email {job_obj.gitargs["config"]["user.email"]}',
         f'{repo_dir_str}/{repo_name}'],
        [f'git config user.name {job_obj.gitargs["config"]["user.name"]}',
         f'{repo_dir_str}/{repo_name}']
    ]

    job_obj.run_commands(logger, create_repo_commands)

    logger.info('Finished repo clone')
    return pr_repo_loc, repo_dir_str


def post_process(job_obj, pr_repo_loc, repo_dir_str, new_baseline, bldir, bldate, blstore):
    logger = logging.getLogger('BL/MOVE_RT_LOGS')
    rt_log = f'tests/logs/RegressionTests_{job_obj.clargs.machine}.log'
    filepath = f'{pr_repo_loc}/{rt_log}'
    rt_dir, logfile_pass = process_logfile(job_obj, filepath)
    if logfile_pass:
        create_bl_dir(bldir, job_obj)
        move_bl_command = [[f'mv {new_baseline}/* {bldir}/', pr_repo_loc]]
        job_obj.run_commands(logger, move_bl_command)
        job_obj.comment_text_append('[BL] Baseline creation and move successful')
        logger.info('Starting RT Job')
        rt.run(job_obj)
        logger.info('Finished with RT Job')


def get_bl_date(job_obj, pr_repo_loc):
    logger = logging.getLogger('BL/UPDATE_RT_NCAR_SH')
    BLDATEFOUND = False
    with open(f'{pr_repo_loc}/tests/bl_date.ncar.conf', 'r') as f:
        for line in f:
            if 'BL_DATE=' in line:
                logger.info('Found BL_DATE in line')
                BLDATEFOUND = True
                bldate = line.split('=')[1].strip()
                bldate = bldate.rstrip('\n')
                logger.info(f'bldate is "{bldate}"')
                logger.info(f'Type bldate: {type(bldate)}')
                bl_format = '%Y%m%d'
                try:
                    datetime.datetime.strptime(bldate, '%Y%m%d')
                except ValueError:
                    logger.info(f'Date {bldate} is not formatted YYYYMMDD')
                    raise ValueError
    if not BLDATEFOUND:
        job_obj.comment_text_append('[BL] ERROR: Variable "BL_DATE" not found in rt.sh.')
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
        logger.critical(f'Could not find {job_obj.clargs.machine}.{job_obj.compiler} '
                        f'{job_obj.preq_dict["action"]} log: {logfile}')
        raise FileNotFoundError
