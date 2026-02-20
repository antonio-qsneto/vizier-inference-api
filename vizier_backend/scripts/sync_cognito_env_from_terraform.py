#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TerraformOutput:
    name: str
    dotenv_key: str


OUTPUTS: tuple[TerraformOutput, ...] = (
    TerraformOutput(name="region", dotenv_key="COGNITO_REGION"),
    TerraformOutput(name="region", dotenv_key="AWS_REGION"),
    TerraformOutput(name="cognito_user_pool_id", dotenv_key="COGNITO_USER_POOL_ID"),
    TerraformOutput(name="cognito_user_pool_client_id", dotenv_key="COGNITO_CLIENT_ID"),
    TerraformOutput(name="cognito_hosted_ui_base_url", dotenv_key="COGNITO_HOSTED_UI_BASE_URL"),
    TerraformOutput(name="cognito_oauth_token_url", dotenv_key="COGNITO_OAUTH_TOKEN_URL"),
)


def _repo_root() -> Path:
    # repo_root/vizier_backend/scripts/this_file.py
    return Path(__file__).resolve().parents[2]


def _run_terraform_output_json(terraform_dir: Path) -> dict:
    proc = subprocess.run(
        ["terraform", "output", "-json"],
        cwd=str(terraform_dir),
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "Terraform failed.\n\n"
            f"cwd: {terraform_dir}\n"
            f"cmd: terraform output -json\n"
            f"stdout:\n{proc.stdout}\n\n"
            f"stderr:\n{proc.stderr}\n"
        )

    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Failed to parse `terraform output -json`.\n\n"
            f"cwd: {terraform_dir}\n"
            f"error: {exc}\n"
            f"raw stdout:\n{proc.stdout}\n"
        ) from exc


def _get_output_value(outputs: dict, name: str) -> str:
    if name not in outputs:
        raise KeyError(f"Terraform output not found: {name}")
    value = outputs[name].get("value")
    if value is None:
        raise ValueError(f"Terraform output has no value: {name}")
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


def _upsert_dotenv(env_path: Path, updates: dict[str, str]) -> tuple[int, int]:
    if not env_path.exists():
        raise FileNotFoundError(f".env not found: {env_path}")

    original_lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines: list[str] = []
    found: dict[str, bool] = {k: False for k in updates}

    for line in original_lines:
        replaced = False
        for key, value in updates.items():
            if line.startswith(f"{key}="):
                new_lines.append(f"{key}={value}\n")
                found[key] = True
                replaced = True
                break
            if line.startswith(f"export {key}="):
                new_lines.append(f"export {key}={value}\n")
                found[key] = True
                replaced = True
                break
        if not replaced:
            new_lines.append(line)

    missing = [k for k, was_found in found.items() if not was_found]
    if missing:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] = f"{new_lines[-1]}\n"
        if new_lines and new_lines[-1].strip():
            new_lines.append("\n")
        for key in missing:
            new_lines.append(f"{key}={updates[key]}\n")

    env_path.write_text("".join(new_lines), encoding="utf-8")
    return (len(updates) - len(missing), len(missing))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Sync AWS Cognito-related values from Terraform outputs into vizier_backend/.env"
    )
    parser.add_argument(
        "--terraform-dir",
        type=Path,
        default=_repo_root() / "vizier-inference-infra/terraform/envs/dev",
        help="Terraform env directory (default: vizier-inference-infra/terraform/envs/dev).",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=_repo_root() / "vizier_backend/.env",
        help="Path to .env file to update (default: vizier_backend/.env).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write changes into the .env file (default: only print values).",
    )
    args = parser.parse_args(argv)

    outputs = _run_terraform_output_json(args.terraform_dir)

    updates: dict[str, str] = {}
    for output in OUTPUTS:
        updates[output.dotenv_key] = _get_output_value(outputs, output.name)

    if not args.write:
        for key, value in updates.items():
            print(f"{key}={value}")
        return 0

    updated, added = _upsert_dotenv(args.env_file, updates)
    print(f"Updated {updated} and added {added} keys in {args.env_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

