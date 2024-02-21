# Imports
import datetime
import logging
import os


def run(job_obj):
    logger = logging.getLogger('RT/RUN')
    branch, pr_repo_loc, repo_dir_str = clone_pr_repo(job_obj)
    run_regression_test(job_obj, pr_repo_loc)
    post_process(job_obj, pr_repo_loc, repo_dir_str, branch)


def run_regression_test(job_obj, pr_repo_loc):
    logger = logging.getLogger('RT/RUN_REGRESSION_TEST')

    rt_command = 'cd tests'
    if job_obj.workdir:
        rt_command += f' && export RUNDIR_ROOT={job_obj.workdir}'
    if job_obj.baseline:
        rt_command += f' && export RTPWD={job_obj.baseline}'
    rt_command += f' && /bin/bash --login ./rt.sh -e -a {job_obj.clargs.account} -p {job_obj.clargs.machine}'
    if job_obj.clargs.envfile:
        rt_command += f' -s {job_obj.clargs.envfile}'
    rt_command += f' {job_obj.clargs.additional_args}'

    job_obj.run_commands(logger, [[rt_command, pr_repo_loc]])


def remove_pr_data(job_obj, pr_repo_loc, repo_dir_str, rt_dir):
    logger = logging.getLogger('RT/REMOVE_PR_DATA')
    rm_command = [
                 [f'rm -rf {rt_dir}', pr_repo_loc],
                 [f'rm -rf {repo_dir_str}', pr_repo_loc]
                 ]
    job_obj.run_commands(logger, rm_command)


def clone_pr_repo(job_obj):
    ''' clone the GitHub pull request repo, via command line '''
    logger = logging.getLogger('RT/CLONE_PR_REPO')
    repo_name = job_obj.preq_dict['preq'].head.repo.name
    branch = job_obj.preq_dict['preq'].head.ref
    git_ssh_url = job_obj.preq_dict['preq'].head.repo.ssh_url
    logger.debug(f'GIT SSH_URL: {git_ssh_url}')
    logger.info('Starting repo clone')
    repo_dir_str = f'{job_obj.workdir}/'\
                   f'{str(job_obj.preq_dict["preq"].id)}/'\
                   f'{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}'
    pr_repo_loc = f'{repo_dir_str}/{repo_name}'
    job_obj.comment_text_append(f'[RT] Repo location: {pr_repo_loc}')
    create_repo_commands = [
        [f'mkdir -p "{repo_dir_str}"', os.getcwd()],
        [f'git clone -b {branch} {git_ssh_url}', repo_dir_str],
        ['git submodule update --init --recursive',
         f'{repo_dir_str}/{repo_name}'],
        [f'git config user.email {job_obj.gitargs["config"]["user.email"]}',
         f'{repo_dir_str}/{repo_name}'],
        [f'git config user.name job_obj.gitargs["config"]["user.name"]',
         f'{repo_dir_str}/{repo_name}']
    ]

    job_obj.run_commands(logger, create_repo_commands)

    logger.info('Finished repo clone')
    return branch, pr_repo_loc, repo_dir_str


def post_process(job_obj, pr_repo_loc, repo_dir_str, branch):
    ''' This is the callback function associated with the "RT" command '''
    logger = logging.getLogger('RT/MOVE_RT_LOGS')
    rt_log = f'tests/logs/RegressionTests_{job_obj.clargs.machine}.log'
    filepath = f'{pr_repo_loc}/{rt_log}'
    print(filepath)
    rt_dir, logfile_pass = process_logfile(job_obj, filepath)
    if logfile_pass:
        #if job_obj.preq_dict['preq'].maintainer_can_modify:
        move_rt_commands = [
            [f'git pull --ff-only origin {branch}', pr_repo_loc],
            [f'git add {rt_log}', pr_repo_loc],
            [f'git commit -m "[AutoRT] {job_obj.clargs.machine} Job Completed.\n\n\n'
              f'on-behalf-of {job_obj.gitargs["github"]["org"]} @{job_obj.gitargs["config"]["user.name"]}"',
             pr_repo_loc],
            ['sleep 10', pr_repo_loc],
            [f'git push origin {branch}', pr_repo_loc]
        ]
#        job_obj.run_commands(logger, move_rt_commands)
        job_obj.comment_text_pop()
        job_obj.comment_text_append(f'***Regression test successful on {job_obj.clargs.machine}!***')
        job_obj.preq_dict['preq'].create_issue_comment(job_obj.comment_text)
    else:
        job_obj.comment_text_append(f'[RT] Log file shows failures.')
        job_obj.comment_text_append(f'[RT] Please obtain logs from {pr_repo_loc}')
        job_obj.preq_dict['preq'].create_issue_comment(job_obj.comment_text)


def process_logfile(job_obj, logfile):
    logger = logging.getLogger('RT/PROCESS_LOGFILE')
    rt_dir = []
    fail_string_list = ['Test', 'FAIL']
    if os.path.exists(logfile):
        logger.debug(f'processing log file {logfile}')
        with open(logfile) as f:
            for line in f:
                if all(x in line for x in fail_string_list):
                    job_obj.comment_text_append(f'[RT] Error: {line.rstrip(chr(10))}')
                elif 'working dir' in line and not rt_dir:
                    rt_dir = os.path.split(line.split()[-1])[0]
                elif 'SUCCESSFUL' in line:
                    return rt_dir, True
        job_obj.job_failed(logger, f'{job_obj.preq_dict["action"]}')
        return rt_dir, False
    else:
        logger.critical(f'Could not find {job_obj.clargs.machine} '
                        f'{job_obj.preq_dict["action"]} log:\n{logfile}')
        print(f'Could not find {job_obj.clargs.machine} '
              f'{job_obj.preq_dict["action"]} log:\n{logfile}')
        raise FileNotFoundError
