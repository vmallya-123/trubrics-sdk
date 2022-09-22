import importlib.util
import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint

from trubrics.exceptions import MissingConfigPathError, MissingTrubricRunFileError
from trubrics.utils.trubrics_manager_connector import make_request
from trubrics.validations.run import TrubricRun, run_trubric

app = typer.Typer()


@app.command()
def run(
    save_ui: bool = False,
    trubric_config_path: str = typer.Option(
        ...,
        prompt=(
            "Enter the path to your trubric config .json file (this file can be generated by running `trubrics init`)"
        ),
    ),
    trubric_output_file_path: str = typer.Option(
        ".", prompt="Enter a path to save your output trubric file. The default path is"
    ),
    trubric_output_file_name: str = typer.Option(
        "my_new_trubric.json", prompt="Enter the file name of your output trubric file. The default file name is"
    ),
):
    """The CLI `trubrics run` command for running trubrics.

    Example:
        ```
        trubrics run <trubric_init_path>.py
        ```

    Args:
        trubric_init_path: a path towards a .py file that initialises data, model and trubrics contexts.
                           This file must contain the TrubricRun object that holds all contexts to run a
                           trubric. The TrubricRun object must be set to a variable `RUN_CONTEXT` to be recognised.
                           For example `RUN_CONTEXT=TrubricRun(...)`.

    """
    trubric_config_file_path = Path(trubric_config_path) / ".trubrics_config.json"
    if not trubric_config_file_path.exists():
        raise MissingConfigPathError(
            f"The trubric configuration file '{trubric_config_file_path}' has not been found. Run `trubrics init` to"
            " create file."
        )
    with open(trubric_config_file_path, "r") as file:
        trubrics_config = json.load(file)
    trubric_run_path = trubrics_config["trubric_run_path"]

    tc = _import_module(module_path=trubric_run_path)
    if hasattr(tc, "RUN_CONTEXT"):
        if isinstance(tc.RUN_CONTEXT, TrubricRun):
            run_context = tc.RUN_CONTEXT
        else:
            raise TypeError("'RUN_CONTEXT' attribute must be of type TrubricRun.")
    else:
        raise AttributeError("Trubrics config python module must contain an attribute 'RUN_CONTEXT'.")

    typer.echo(
        typer.style(
            f"Running trubric from file '{trubric_run_path}' with model '{run_context.trubric_context.model_name}' and"
            f" dataset '{tc.data_context.name}'.",
            fg=typer.colors.BLUE,
        )
    )
    all_validation_results = run_trubric(tr=run_context)
    validations = []
    for validation_result in all_validation_results:
        validations.append(validation_result)

        message_start = f"{validation_result.validation_type} - {validation_result.severity.upper()}"
        completed_dots = (100 - len(message_start)) * "."
        if validation_result.outcome == "pass":
            ending = typer.style("PASSED", fg=typer.colors.GREEN, bold=True)
        else:
            ending = typer.style("FAILED", fg=typer.colors.WHITE, bg=typer.colors.RED)
        message = typer.style(message_start, bold=True) + completed_dots + ending
        typer.echo(message)

    # save new trubric .json
    new_trubric_context = tc.trubric_context
    new_trubric_context.validations = validations
    new_trubric_context.save_local(path=trubric_output_file_path, file_name=trubric_output_file_name)

    # save new trubric to ui
    if save_ui is True:
        if "user_id" in trubrics_config.keys():
            new_trubric_context.save_ui(url=trubrics_config["api_url"], user_id=trubrics_config["user_id"])
        else:
            typer.echo(
                typer.style(
                    "ERROR: You must authenticate with the trubrics manager by running `trubrics init` to remotely save"
                    " trubrics runs.",
                    fg=typer.colors.RED,
                )
            )


@app.command()
def init(
    trubrics_api_url: Optional[str] = None,
    trubric_run_path: str = typer.Option(
        ..., prompt="Enter the path to your trubric run .py file (e.g. examples/cli/trubric_run.py)"
    ),
    trubric_config_path: str = typer.Option(
        ".", prompt="Enter a path to save your .trubrics_config.json. The default path is"
    ),
):
    """The CLI `trubrics init` command for initialising trubrics config."""

    if trubrics_api_url:
        uid = typer.prompt("Enter your User ID (generated in the trubrics manager)")

        res = make_request(f"{trubrics_api_url}/api/is_user/{uid}", headers={"Content-Type": "application/json"})
        res = json.loads(res)
        if "is_user" in res.keys():
            message = typer.style(res["msg"], fg=typer.colors.RED, bold=True)
            typer.echo(message)
            raise typer.Abort()
        typer.echo(
            typer.style(
                "Trubrics configuration has been set and user is authenticated with the trubrics manager UI:",
                fg=typer.colors.GREEN,
                bold=True,
            )
        )
        res["api_url"] = trubrics_api_url
    else:
        typer.echo(
            typer.style(
                "Trubrics config set without trubrics manager authentication:", fg=typer.colors.GREEN, bold=True
            )
        )
        res = {}

    if not Path(trubric_run_path).exists() or not trubric_run_path.endswith(".py"):
        raise MissingTrubricRunFileError("Trubric run file path does not exist or is not a .py file.")

    res["trubric_run_path"] = trubric_run_path

    rprint(res)
    with open(
        Path(trubric_config_path) / ".trubrics_config.json",
        "w",
    ) as file:
        file.write(json.dumps(res, indent=4))


def _import_module(module_path: str):
    try:
        spec = importlib.util.spec_from_file_location("module.name", module_path)
        lib = importlib.util.module_from_spec(spec)  # type: ignore
        sys.modules["module.name"] = lib
        spec.loader.exec_module(lib)  # type: ignore
    except FileNotFoundError as e:
        raise e
    return lib


if __name__ == "__main__":
    app()
