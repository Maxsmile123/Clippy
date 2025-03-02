import datetime
import os
import re
import yaml
import shutil
import subprocess

import click
import github
from github import Github
import git

from . import helpers
from . import highlight
from .echo import echo
from .exceptions import ClientError
from .config import Config


CONFIG_TEMPLATE = {
    "github.user": "-",
    "github.token": "-",
    "name.first": "-",
    "name.last": "-",
    "group": "group",
    "assignee": "-",
    "tags": "",
}

# Solutions local repository


class Solutions(object):
    def __init__(self, repo_dir, tasks_repo_dir, default_assignee, master_branch):
        if repo_dir and not os.path.exists(repo_dir):
            raise RuntimeError(
                "Solutions repository not found at '{}'".format(repo_dir))

        self.repo_dir = repo_dir
        self.tasks_repo_dir = tasks_repo_dir
        self.default_assignee = default_assignee
        self.master_branch = master_branch

        if repo_dir:
            self._open_config()


    def setup_git_config(self):
        cur_dir = os.getcwd()
        os.chdir(self.repo_dir)
        self._git(["config", "--global", "credential.helper", "cache"])
        try:
            self._git(["config", "--get", "user.email"])
        except subprocess.CalledProcessError:
            self._git(["config", "user.email", ""])
        try:
            self._git(["config", "--get", "user.name"])
        except subprocess.CalledProcessError:
            self._git(["config", "user.name", '"{} {}"'.format(
                self.config.get("name.first"), self.config.get("name.last"))])
        finally:
            os.chdir(cur_dir)

    def _open_config(self):
        config_path = os.path.join(self.repo_dir, ".clippy-user.json")

        template = CONFIG_TEMPLATE
        if not os.path.exists(config_path):
            template = self._config_init_template()

        self.config_ = Config(config_path, template=template)

    def _config_init_template(self):
        template = CONFIG_TEMPLATE

        print(self.remote)

        if self.default_assignee:
            template["assignee"] = self.default_assignee

        return template

    @staticmethod
    def open(tasks_repo, config):
        tasks_repo_dir = tasks_repo.working_tree_dir

        link_path = os.path.join(tasks_repo_dir, "client/.solutions")

        solutions_repo_dir = None

        if os.path.exists(link_path):
            with open(link_path) as link:
                solutions_repo_dir = link.read().strip()

        if solutions_repo_dir:
            if not os.path.exists(solutions_repo_dir):
                os.remove(link_path)  # outdated
                solutions_repo_dir = None

        default_assignee = config.get_or("default_assignee", None)
        master_branch = config.get_or("solutions_master", "master")

        return Solutions(solutions_repo_dir, tasks_repo_dir, default_assignee, master_branch)

    @property
    def attached(self):
        return self.repo_dir is not None

    def _check_attached(self):
        if not self.attached:
            raise RuntimeError("Solutions repository not attached")

    @property
    def config(self):
        self._check_attached()
        return self.config_

    def print_config(self):
        echo.echo(highlight.path(self.config.path) + ":")
        echo.write(self.config.format())

    @property
    def remote(self):
        self._check_attached()
        git_repo = git.Repo(self.repo_dir)
        return git_repo.remotes.origin.url

    def _git(self, cmd, **kwargs):
        self._check_attached()
        echo.echo("Running git: {}".format(cmd))
        subprocess.check_call(["git"] + cmd, **kwargs)

    def _git_output(self, cmd, **kwargs):
        self._check_attached()
        echo.echo("Running git: {}".format(cmd))
        return subprocess.check_output(["git"] + cmd, **kwargs)

    @staticmethod
    def _task_branch_name(task):
        return "{}/{}".format(task.topic, task.name)

    @staticmethod
    def _task_dir(task):
        return "tasks/{}/{}".format(task.topic, task.name)

    def _switch_to_or_create_branch(self, branch):
        try:
            self._switch_to_target(branch)
        except subprocess.CalledProcessError:
            self._git(["checkout", "-b", branch, "--"], cwd=self.repo_dir)

    # target - commit sha or branch name
    def _switch_to_target(self, target):
        self._git(["checkout", target, "--"], cwd=self.repo_dir)

    def _switch_to_branch(self, name):
        self._switch_to_target(name)

    def _switch_to_commit(self, hash):
        self._switch_to_target(hash)

    def _switch_to_master(self):
        self._switch_to_branch(self.master_branch)

    @staticmethod
    def _default_commit_message(task):
        return "Bump task {}/{}".format(task.topic, task.name)
    

    @staticmethod
    def _update_commit_message():
        return "Update from https://github.com/Maxsmile123/Algorithms-And-DataStructure-Course/tree/master"

    def _unstage_all(self):
        self._git(["reset", "HEAD", "."], cwd=self.repo_dir)
        
    def _stash(self):
        self._git(["stash"], cwd=self.repo_dir)

    @staticmethod
    def _check_no_diff(task, files):
        for fname in files:
            fpath = os.path.join(task.dir, fname)
            diff = subprocess.check_output(["git", "diff", "origin/master", "--", fpath])
            if diff:
                raise ClientError("Commit aborted, please revert local changes in '{}'".format(fname))
            
    def _open_deadlines_config(self, filename="deadlines.yaml"):
        deadlines_cofnig_path = os.path.join(self.tasks_repo_dir, filename)
        with open(deadlines_cofnig_path) as f:
            conf = yaml.safe_load(f)
        
        return conf
    
    
    def _get_score_for_task(self, task_obj):
        deadline_conf = self._open_deadlines_config()
        now = datetime.datetime.now()
        result = ""
        score = None
        for task_group in deadline_conf:
            if task_group['group'].lower() == task_obj.topic:
                deadline = datetime.datetime.strptime(task_group['deadline'], '%d-%m-%Y %H:%M')
                print(f'сраниванию сейчас: {now} и дедлайн {deadline}')
                if now > deadline:
                    result += f"Deadline for {task_obj.name} was exceeded! "
                    score = 100
                else:
                    for task in task_group['tasks']:
                        print(f"Сравниваю {task['task']} и {task_obj.name}")
                        if task['task'].split('/')[1] == task_obj.name:
                            score = task['score']
                    
        result = result + f'Score is {score}'
        return result
                    
                    
    def _pre_commit_checks(self, task):
        do_not_change_files = task.conf.do_not_change_files
        if do_not_change_files:
            self._check_no_diff(task, do_not_change_files)

    def commit(self, task, message=None, bump=False):
        self._check_attached()
        
        self._pre_commit_checks(task)

        solution_files = task.conf.solution_files

        os.chdir(self.repo_dir)
        echo.echo("Moving to repo {}".format(highlight.path(self.repo_dir)))

        self._unstage_all()
        self._stash()
        self._switch_to_master()

        task_branch = self._task_branch_name(task)
        echo.echo("Switching to task branch '{}'".format(task_branch))
        self._switch_to_or_create_branch(task_branch)

        os.chdir(self.repo_dir)

        task_dir = self._task_dir(task)

        if not os.path.exists(task_dir):
            helpers.mkdir(task_dir, parents=True)

        echo.echo("Copying solution files: {}".format(solution_files))
        helpers.copy_files(task.dir, task_dir, solution_files, clear_dest=True, make_dirs=True)

        echo.echo("Adding solution files to index")
        self._git(["add"] + solution_files, cwd=task_dir)

        if bump:
            bumpfile = os.path.join(task_dir, "bump")
            now = datetime.datetime.now()
            with open(bumpfile, "w") as f:
                f.write(now.strftime("%Y-%m-%d %H:%M:%S"))
            self._git(["add", "bump"], cwd=task_dir)

        diff = self._git_output(["diff", "--staged", "."], cwd=self.repo_dir)
        if not diff:
            echo.note("Empty diff, nothing to commit")
            self._switch_to_master()
            return



        if not message:
            message = self._default_commit_message(task)
            
        message += '. ' + self._get_score_for_task(task)
            
        echo.note("Committing task solution")
        self._git(["commit", "-m", message], cwd=task_dir)

        self._switch_to_master()

    def push(self, task):
        self._check_attached()

        os.chdir(self.repo_dir)
        echo.echo("Moving to repo {}".format(highlight.path(self.repo_dir)))

        task_branch = self._task_branch_name(task)

        self._switch_to_branch(task_branch)

        token = self.config.get_or("github.token", None)
        if token is None:
            raise ClientError("Token for GitHub not found")

        self._git(["push", "origin", task_branch], cwd=self.repo_dir)

        self._switch_to_master()

    def _get_remote_repo_address(self):
        url = self.remote

        def _cut_dot_git(addr):
            if addr.endswith(".git"):
                addr = addr[:-4]
            return addr

        prefixes = ["https://github.com/", "git@github.com:"]
        for prefix in prefixes:
            if url.startswith(prefix):
                return _cut_dot_git(url[len(prefix):])

        raise ClientError(
            "Cannot get solutions repo address for '{}'".format(url))

    def merge(self, task):
        self._check_attached()

        echo.echo("Creating pull request...")

        task_branch_name = self._task_branch_name(task)

        # Create Github client

        token = self.config.get_or("github.token", None)
        if token is None:
            raise ClientError("Token for GitHub not found")

        auth = github.Auth.Token(token)
        github_client = Github(auth=auth)

        remote_repo_address = self._get_remote_repo_address()
        echo.echo("Solutions GitHub repo: {}".format(remote_repo_address))
        project = github_client.get_repo(remote_repo_address)

        task_branch = helpers.try_get_branch(project, task_branch_name)
        if not task_branch:
            raise ClientError(
                "Task branch not found in remote repository: {}".format(task_branch_name))

        labels = [
            self.config.get("group"),
            task.topic,
            task.fullname,
        ]

        custom_tags = helpers.parse_list(
            self.config.get_or("tags", ""))
        labels.extend(custom_tags)

        title = "[{group}] [{student}] {task}".format(
            group=self.config.get("group"),
            student="{}-{}".format(self.config.get("name.first"),
                                   self.config.get("name.last")),
            task="{}/{}".format(task.topic, task.name)
        )

        assignee_username = self.config.get_or("assignee", None)
        if assignee_username is None:
            raise ClientError(
                "Assignee not found")

        try:
            pr = project.create_pull(
                base=self.master_branch,
                head=task_branch_name,
                title=title
            )
            pr.add_to_assignees(assignee_username)
            for label in labels:
                pr.add_to_labels(label)
            echo.echo("Pull request created: {}".format(pr.html_url))
        except Exception:
            echo.note(
                "Pull Request for task {} already exists".format(
                    task.fullname))

    def apply_to(self, task, commit_hash=None, force=False):
        self._check_attached()

        os.chdir(self.repo_dir)
        echo.echo("Moving to repo {}".format(highlight.path(self.repo_dir)))

        if commit_hash is None:
            git_target = self._task_branch_name(task)
        else:
            git_target = commit_hash

        self._switch_to_target(git_target)

        task_dir = self._task_dir(task)

        if not os.path.exists(task_dir):
            raise ClientError(
                "Cannot find task directory '{}' in '{}'".format(
                    task_dir, git_target))

        if force or click.confirm(
                "Apply solutions to task {}?".format(task.fullname)):
            echo.echo("Applying solution from solutions repo...")
            helpers.copy_files(task_dir, task.dir, task.conf.solution_files, clear_dest=True)

        self._switch_to_master()

