"""Tasks for use with Invoke.

Copyright (c) 2023, Network to Code, LLC
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
  http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import os
from pathlib import Path
from time import sleep

from invoke.collection import Collection
from invoke.tasks import task as invoke_task


def is_truthy(arg):
    """Convert "truthy" strings into Booleans.

    Examples
    --------
        >>> is_truthy('yes')
        True
    Args:
        arg (str): Truthy string (True values are y, yes, t, true, on and 1; false values are n, no,
        f, false, off and 0. Raises ValueError if val is anything else.
    """
    if isinstance(arg, bool):
        return arg

    val = str(arg).lower()
    if val in ("y", "yes", "t", "true", "on", "1"):
        return True
    elif val in ("n", "no", "f", "false", "off", "0"):
        return False
    else:
        raise ValueError(f"Invalid truthy value: `{arg}`")


# Use pyinvoke configuration for default values, see http://docs.pyinvoke.org/en/stable/concepts/configuration.html
# Variables may be overwritten in invoke.yml or by the environment variables INVOKE_NAUTOBOT_SSOT_xxx
namespace = Collection("nautobot_ssot")
namespace.configure(
    {
        "nautobot_ssot": {
            "nautobot_ver": "2.1.0",
            "project_name": "nautobot-ssot",
            "python_ver": "3.11",
            "local": False,
            "compose_dir": os.path.join(os.path.dirname(__file__), "development"),
            "compose_files": [
                "docker-compose.base.yml",
                "docker-compose.redis.yml",
                "docker-compose.postgres.yml",
                "docker-compose.dev.yml",
            ],
            "compose_http_timeout": "86400",
        }
    }
)


def _is_compose_included(context, name):
    return f"docker-compose.{name}.yml" in context.nautobot_ssot.compose_files


def _await_healthy_service(context, service):
    container_id = docker_compose(context, f"ps -q -- {service}", pty=False, echo=False, hide=True).stdout.strip()
    _await_healthy_container(context, container_id)


def _await_healthy_container(context, container_id):
    while True:
        result = context.run(
            "docker inspect --format='{{.State.Health.Status}}' " + container_id,
            pty=False,
            echo=False,
            hide=True,
        )
        if result.stdout.strip() == "healthy":
            break
        print(f"Waiting for `{container_id}` container to become healthy ...")
        sleep(1)


def task(function=None, *args, **kwargs):
    """Task decorator to override the default Invoke task decorator and add each task to the invoke namespace."""

    def task_wrapper(function=None):
        """Wrapper around invoke.task to add the task to the namespace as well."""
        if args or kwargs:
            task_func = invoke_task(*args, **kwargs)(function)
        else:
            task_func = invoke_task(function)
        namespace.add_task(task_func)
        return task_func

    if function:
        # The decorator was called with no arguments
        return task_wrapper(function)
    # The decorator was called with arguments
    return task_wrapper


def docker_compose(context, command, **kwargs):
    """Helper function for running a specific docker compose command with all appropriate parameters and environment.

    Args:
    ----
        context (obj): Used to run specific commands
        command (str): Command string to append to the "docker compose ..." command, such as "build", "up", etc.
        **kwargs: Passed through to the context.run() call.
    """
    build_env = {
        # Note: 'docker compose logs' will stop following after 60 seconds by default,
        # so we are overriding that by setting this environment variable.
        "COMPOSE_HTTP_TIMEOUT": context.nautobot_ssot.compose_http_timeout,
        "NAUTOBOT_VER": context.nautobot_ssot.nautobot_ver,
        "PYTHON_VER": context.nautobot_ssot.python_ver,
        **kwargs.pop("env", {}),
    }
    compose_command_tokens = [
        "docker compose",
        f"--project-name {context.nautobot_ssot.project_name}",
        f'--project-directory "{context.nautobot_ssot.compose_dir}"',
    ]

    for compose_file in context.nautobot_ssot.compose_files:
        compose_file_path = os.path.join(context.nautobot_ssot.compose_dir, compose_file)
        compose_command_tokens.append(f' -f "{compose_file_path}"')

    compose_command_tokens.append(command)

    # If `service` was passed as a kwarg, add it to the end.
    service = kwargs.pop("service", None)
    if service is not None:
        compose_command_tokens.append(service)

    print(f'Running docker compose command "{command}"')
    compose_command = " ".join(compose_command_tokens)

    return context.run(compose_command, env=build_env, **kwargs)


def run_command(context, command, **kwargs):
    """Wrapper to run a command locally or inside the nautobot container."""
    if is_truthy(context.nautobot_ssot.local):
        context.run(command, **kwargs)
    else:
        # Check if nautobot is running, no need to start another nautobot container to run a command
        docker_compose_status = "ps --services --filter status=running"
        results = docker_compose(context, docker_compose_status, hide="out")
        if "nautobot" in results.stdout:
            compose_command = f"exec nautobot {command}"
        else:
            compose_command = f"run --rm --entrypoint '{command}' nautobot"

        pty = kwargs.pop("pty", True)

        docker_compose(context, compose_command, pty=pty, **kwargs)


# ------------------------------------------------------------------------------
# BUILD
# ------------------------------------------------------------------------------
@task(
    help={
        "force_rm": "Always remove intermediate containers",
        "cache": "Whether to use Docker's cache when building the image (defaults to enabled)",
    }
)
def build(context, force_rm=False, cache=True):
    """Build Nautobot docker image."""
    command = "build"

    if not cache:
        command += " --no-cache"
    if force_rm:
        command += " --force-rm"

    print(f"Building Nautobot with Python {context.nautobot_ssot.python_ver}...")
    docker_compose(context, command)


@task
def generate_packages(context):
    """Generate all Python packages inside docker and copy the file locally under dist/."""
    command = "poetry build"
    run_command(context, command)


@task(
    help={
        "check": (
            "If enabled, check for outdated dependencies in the poetry.lock file, "
            "instead of generating a new one. (default: disabled)"
        )
    }
)
def lock(context, check=False):
    """Generate poetry.lock inside the Nautobot container."""
    run_command(context, f"poetry {'check' if check else 'lock --no-update'}")


# ------------------------------------------------------------------------------
# START / STOP / DEBUG
# ------------------------------------------------------------------------------
@task(help={"service": "If specified, only affect this service."})
def debug(context, service=""):
    """Start specified or all services and its dependencies in debug mode."""
    print(f"Starting {service} in debug mode...")
    docker_compose(context, "up", service=service)


@task(help={"service": "If specified, only affect this service."})
def start(context, service=""):
    """Start specified or all services and its dependencies in detached mode."""
    print("Starting Nautobot in detached mode...")
    docker_compose(context, "up --detach", service=service)


@task(help={"service": "If specified, only affect this service."})
def restart(context, service=""):
    """Gracefully restart specified or all services."""
    print("Restarting Nautobot...")
    docker_compose(context, "restart", service=service)


@task(help={"service": "If specified, only affect this service."})
def stop(context, service=""):
    """Stop specified or all services, if service is not specified, remove all containers."""
    print("Stopping Nautobot...")
    docker_compose(context, "stop" if service else "down --remove-orphans", service=service)


@task(
    aliases=("down",),
    help={
        "volumes": "Remove Docker compose volumes (default: True)",
        "import-db-file": "Import database from `import-db-file` file into the fresh environment (default: empty)",
    },
)
def destroy(context, volumes=True, import_db_file=""):
    """Destroy all containers and volumes."""
    print("Destroying Nautobot...")
    docker_compose(context, f"down --remove-orphans {'--volumes' if volumes else ''}")

    if not import_db_file:
        return

    if not volumes:
        raise ValueError("Cannot specify `--no-volumes` and `--import-db-file` arguments at the same time.")

    print(f"Importing database file: {import_db_file}...")

    input_path = Path(import_db_file).absolute()
    if not input_path.is_file():
        raise ValueError(f"File not found: {input_path}")

    command = [
        "run",
        "--rm",
        "--detach",
        f"--volume='{input_path}:/docker-entrypoint-initdb.d/dump.sql'",
        "--",
        "db",
    ]

    container_id = docker_compose(context, " ".join(command), pty=False, echo=False, hide=True).stdout.strip()
    _await_healthy_container(context, container_id)
    print("Stopping database container...")
    context.run(f"docker stop {container_id}", pty=False, echo=False, hide=True)

    print("Database import complete, you can start Nautobot with the following command:")
    print("invoke start")


@task
def export(context):
    """Export docker compose configuration to `compose.yaml` file.

    Useful to:

    - Debug docker compose configuration.
    - Allow using `docker compose` command directly without invoke.
    """
    docker_compose(context, "convert > compose.yaml")


@task(name="ps", help={"all": "Show all, including stopped containers"})
def ps_task(context, all=False):
    """List containers."""
    docker_compose(context, f"ps {'--all' if all else ''}")


@task
def vscode(context):
    """Launch Visual Studio Code with the appropriate Environment variables to run in a container."""
    command = "code nautobot.code-workspace"

    context.run(command)


@task(
    help={
        "service": "If specified, only display logs for this service (default: all)",
        "follow": "Flag to follow logs (default: False)",
        "tail": "Tail N number of lines (default: all)",
    }
)
def logs(context, service="", follow=False, tail=0):
    """View the logs of a docker compose service."""
    command = "logs "

    if follow:
        command += "--follow "
    if tail:
        command += f"--tail={tail} "

    docker_compose(context, command, service=service)


# ------------------------------------------------------------------------------
# ACTIONS
# ------------------------------------------------------------------------------
@task(help={"file": "Python file to execute"})
def nbshell(context, file=""):
    """Launch an interactive nbshell session."""
    command = [
        "nautobot-server",
        "nbshell",
        f"< '{file}'" if file else "",
    ]
    run_command(context, " ".join(command), pty=not bool(file))


@task
def shell_plus(context):
    """Launch an interactive shell_plus session."""
    command = "nautobot-server shell_plus"
    run_command(context, command)


@task
def cli(context):
    """Launch a bash shell inside the Nautobot container."""
    run_command(context, "bash")


@task(
    help={
        "user": "name of the superuser to create (default: admin)",
    }
)
def createsuperuser(context, user="admin"):
    """Create a new Nautobot superuser account (default: "admin"), will prompt for password."""
    command = f"nautobot-server createsuperuser --username {user}"

    run_command(context, command)


@task(
    help={
        "name": "name of the migration to be created; if unspecified, will autogenerate a name",
    }
)
def makemigrations(context, name=""):
    """Perform makemigrations operation in Django."""
    command = "nautobot-server makemigrations nautobot_ssot"

    if name:
        command += f" --name {name}"

    run_command(context, command)


@task
def migrate(context):
    """Perform migrate operation in Django."""
    command = "nautobot-server migrate"

    run_command(context, command)


@task(help={})
def post_upgrade(context):
    """
    Performs Nautobot common post-upgrade operations using a single entrypoint.

    This will run the following management commands with default settings, in order:

    - migrate
    - trace_paths
    - collectstatic
    - remove_stale_contenttypes
    - clearsessions
    - invalidate all
    """
    command = "nautobot-server post_upgrade"

    run_command(context, command)


@task(
    help={
        "service": "Docker compose service name to run command in (default: nautobot).",
        "command": "Command to run (default: bash).",
        "file": "File to run command with (default: empty)",
    },
)
def exec(context, service="nautobot", command="bash", file=""):
    """Launch a command inside the running container (defaults to bash shell inside nautobot container)."""
    command = [
        "exec",
        "--",
        service,
        command,
        f"< '{file}'" if file else "",
    ]
    docker_compose(context, " ".join(command), pty=not bool(file))


@task(
    help={
        "db-name": "Database name (default: Nautobot database)",
        "input-file": "SQL file to execute and quit (default: empty, start interactive CLI)",
        "output-file": "Ouput file, overwrite if exists (default: empty, output to stdout)",
        "query": "SQL command to execute and quit (default: empty)",
    }
)
def dbshell(context, db_name="", input_file="", output_file="", query=""):
    """Start database CLI inside the running `db` container.

    Doesn't use `nautobot-server dbshell`, using started `db` service container only.
    """
    if input_file and query:
        raise ValueError("Cannot specify both, `input_file` and `query` arguments")
    if output_file and not (input_file or query):
        raise ValueError("`output_file` argument requires `input_file` or `query` argument")

    env = {}
    if query:
        env["_SQL_QUERY"] = query

    command = [
        "exec",
        "--env=_SQL_QUERY" if query else "",
        "-- db sh -c '",
    ]

    if _is_compose_included(context, "mysql"):
        command += [
            "mysql",
            "--user=$MYSQL_USER",
            "--password=$MYSQL_PASSWORD",
            f"--database={db_name or '$MYSQL_DATABASE'}",
        ]
    elif _is_compose_included(context, "postgres"):
        command += [
            "psql",
            "--username=$POSTGRES_USER",
            f"--dbname={db_name or '$POSTGRES_DB'}",
        ]
    else:
        raise ValueError("Unsupported database backend.")

    command += [
        "'",
        '<<<"$_SQL_QUERY"' if query else "",
        f"< '{input_file}'" if input_file else "",
        f"> '{output_file}'" if output_file else "",
    ]

    docker_compose(context, " ".join(command), env=env, pty=not (input_file or output_file or query))


@task(
    help={
        "db-name": "Database name to create (default: Nautobot database)",
        "input-file": "SQL dump file to replace the existing database with. This can be generated using `invoke backup-db` (default: `dump.sql`).",
    }
)
def import_db(context, db_name="", input_file="dump.sql"):
    """Stop Nautobot containers and replace the current database with the dump into `db` container."""
    docker_compose(context, "stop -- nautobot worker beat")
    start(context, "db")
    _await_healthy_service(context, "db")

    command = ["exec -- db sh -c '"]

    if _is_compose_included(context, "mysql"):
        if not db_name:
            db_name = "$MYSQL_DATABASE"
        command += [
            "mysql --user root --password=$MYSQL_ROOT_PASSWORD",
            '--execute="',
            f"DROP DATABASE IF EXISTS {db_name};",
            f"CREATE DATABASE {db_name};",
            ""
            if db_name == "$MYSQL_DATABASE"
            else f"GRANT ALL PRIVILEGES ON {db_name}.* TO $MYSQL_USER; FLUSH PRIVILEGES;",
            '"',
            "&&",
            "mysql",
            f"--database={db_name}",
            "--user=$MYSQL_USER",
            "--password=$MYSQL_PASSWORD",
        ]
    elif _is_compose_included(context, "postgres"):
        if not db_name:
            db_name = "$POSTGRES_DB"
        command += [
            f"dropdb --if-exists --user=$POSTGRES_USER {db_name} &&",
            f"createdb --user=$POSTGRES_USER {db_name} &&",
            f"psql --user=$POSTGRES_USER --dbname={db_name}",
        ]
    else:
        raise ValueError("Unsupported database backend.")

    command += [
        "'",
        f"< '{input_file}'",
    ]

    docker_compose(context, " ".join(command), pty=False)

    print("Database import complete, you can start Nautobot now: `invoke start`")


@task(
    help={
        "db-name": "Database name to backup (default: Nautobot database)",
        "output-file": "Ouput file, overwrite if exists (default: `dump.sql`)",
        "readable": "Flag to dump database data in more readable format (default: `True`)",
    }
)
def backup_db(context, db_name="", output_file="dump.sql", readable=True):
    """Dump database into `output_file` file from `db` container."""
    start(context, "db")
    _await_healthy_service(context, "db")

    command = ["exec -- db sh -c '"]

    if _is_compose_included(context, "mysql"):
        command += [
            "mysqldump",
            "--user=root",
            "--password=$MYSQL_ROOT_PASSWORD",
            "--skip-extended-insert" if readable else "",
            db_name if db_name else "$MYSQL_DATABASE",
        ]
    elif _is_compose_included(context, "postgres"):
        command += [
            "pg_dump",
            "--username=$POSTGRES_USER",
            f"--dbname={db_name or '$POSTGRES_DB'}",
            "--inserts" if readable else "",
        ]
    else:
        raise ValueError("Unsupported database backend.")

    command += [
        "'",
        f"> '{output_file}'",
    ]

    docker_compose(context, " ".join(command), pty=False)

    print(50 * "=")
    print("The database backup has been successfully completed and saved to the following file:")
    print(output_file)
    print("You can import this database backup with the following command:")
    print(f"invoke import-db --input-file '{output_file}'")
    print(50 * "=")


# ------------------------------------------------------------------------------
# DOCS
# ------------------------------------------------------------------------------
@task
def docs(context):
    """Build and serve docs locally for development."""
    command = "mkdocs serve -v"

    if is_truthy(context.nautobot_ssot.local):
        print(">>> Serving Documentation at http://localhost:8001")
        run_command(context, command)
    else:
        start(context, service="docs")


@task
def build_and_check_docs(context):
    """Build documentation to be available within Nautobot."""
    command = "mkdocs build --no-directory-urls --strict"
    run_command(context, command)


@task(name="help")
def help_task(context):
    """Print the help of available tasks."""
    import tasks  # pylint: disable=all

    root = Collection.from_module(tasks)
    for task_name in sorted(root.task_names):
        print(50 * "-")
        print(f"invoke {task_name} --help")
        context.run(f"invoke {task_name} --help")


@task(
    help={
        "version": "Version of Single Source of Truth to generate the release notes for.",
    }
)
def generate_release_notes(context, version=""):
    """Generate Release Notes using Towncrier."""
    command = "env DJANGO_SETTINGS_MODULE=nautobot.core.settings towncrier build"
    if version:
        command += f" --version {version}"
    run_command(context, command)


# ------------------------------------------------------------------------------
# TESTS
# ------------------------------------------------------------------------------
@task(
    help={
        "autoformat": "Apply formatting recommendations automatically, rather than failing if formatting is incorrect.",
    }
)
def black(context, autoformat=False):
    """Check Python code style with Black."""
    if autoformat:
        black_command = "black"
    else:
        black_command = "black --check --diff"

    command = f"{black_command} ."

    run_command(context, command)


@task
def flake8(context):
    """Check for PEP8 compliance and other style issues."""
    command = "flake8 . --config .flake8"
    run_command(context, command)


@task
def hadolint(context):
    """Check Dockerfile for hadolint compliance and other style issues."""
    command = "hadolint development/Dockerfile"
    run_command(context, command)


@task
def pylint(context):
    """Run pylint code analysis."""
    command = 'pylint --init-hook "import nautobot; nautobot.setup()" --rcfile pyproject.toml nautobot_ssot'
    run_command(context, command)


@task(aliases=("a",))
def autoformat(context):
    """Run code autoformatting."""
    black(context, autoformat=True)
    ruff(context, action="both", fix=True)


@task(
    help={
        "action": "One of 'lint', 'format', or 'both'",
        "fix": "Automatically fix selected action. May not be able to fix all.",
        "output_format": "see https://docs.astral.sh/ruff/settings/#output-format",
    },
)
def ruff(context, action="lint", fix=False, output_format="text"):
    """Run ruff to perform code formatting and/or linting."""
    if action != "lint":
        command = "ruff format"
        if not fix:
            command += " --check"
        command += " ."
        run_command(context, command)
    if action != "format":
        command = "ruff check"
        if fix:
            command += " --fix"
        command += f" --output-format {output_format} ."
        run_command(context, command)


@task
def bandit(context):
    """Run bandit to validate basic static code security analysis."""
    command = "bandit --recursive . --configfile .bandit.yml"
    run_command(context, command)


@task
def yamllint(context):
    """Run yamllint to validate formatting adheres to NTC defined YAML standards.

    Args:
    ----
        context (obj): Used to run specific commands
    """
    command = "yamllint . --format standard"
    run_command(context, command)


@task
def check_migrations(context):
    """Check for missing migrations."""
    command = "nautobot-server makemigrations --dry-run --check"

    run_command(context, command)


@task(
    help={
        "keepdb": "save and re-use test database between test runs for faster re-testing.",
        "label": "specify a directory or module to test instead of running all Nautobot tests",
        "failfast": "fail as soon as a single test fails don't run the entire test suite",
        "buffer": "Discard output from passing tests",
        "pattern": "Run specific test methods, classes, or modules instead of all tests",
        "verbose": "Enable verbose test output.",
    }
)
def unittest(
    context,
    keepdb=False,
    label="nautobot_ssot",
    failfast=False,
    buffer=True,
    pattern="",
    verbose=False,
):
    """Run Nautobot unit tests."""
    command = f"coverage run --module nautobot.core.cli test {label}"

    if keepdb:
        command += " --keepdb"
    if failfast:
        command += " --failfast"
    if buffer:
        command += " --buffer"
    if pattern:
        command += f" -k='{pattern}'"
    if verbose:
        command += " --verbosity 2"

    run_command(context, command)


@task
def unittest_coverage(context):
    """Report on code test coverage as measured by 'invoke unittest'."""
    command = "coverage report --skip-covered --include 'nautobot_ssot/*' --omit *migrations*"

    run_command(context, command)


@task(
    help={
        "failfast": "fail as soon as a single test fails don't run the entire test suite. (default: False)",
        "keepdb": "Save and re-use test database between test runs for faster re-testing. (default: False)",
        "lint-only": "Only run linters; unit tests will be excluded. (default: False)",
    }
)
def tests(context, failfast=False, keepdb=False, lint_only=False):
    """Run all tests for this app."""
    # If we are not running locally, start the docker containers so we don't have to for each test
    if not is_truthy(context.nautobot_ssot.local):
        print("Starting Docker Containers...")
        start(context)
    # Sorted loosely from fastest to slowest
    print("Running black...")
    black(context)
    print("Running ruff...")
    ruff(context)
    print("Running flake8...")
    flake8(context)
    print("Running bandit...")
    bandit(context)
    print("Running yamllint...")
    yamllint(context)
    print("Running poetry check...")
    lock(context, check=True)
    print("Running migrations check...")
    check_migrations(context)
    print("Running pylint...")
    pylint(context)
    print("Running mkdocs...")
    build_and_check_docs(context)
    if not lint_only:
        print("Running unit tests...")
        unittest(context, failfast=failfast, keepdb=keepdb)
        unittest_coverage(context)
    print("All tests have passed!")
