import csv
import json
import logging
import os
import pathlib

import bittensor as bt  # type: ignore
import requests
import yaml
from django.conf import settings  # type: ignore
from django.http.response import HttpResponse, HttpResponseRedirect  # type: ignore
from django.shortcuts import redirect, render  # type: ignore

from auto_validator.utils.sync_utils import (
    generate_diff,
    load_validators_from_yaml,
    load_yaml_data,
    prepare_subnet_data_for_comparison,
    prepare_validator_data_for_comparison,
    sync_validators,
)

from ..models import ExternalHotkey, Subnet, Validator, ValidatorHotkey
from .ssh import SSH_Manager

logger = logging.getLogger("django")

GITHUB_SUBNETS_CONFIG_PATH = settings.GITHUB_SUBNETS_CONFIG_PATH
LOCAL_SUBNETS_CONFIG_PATH = settings.LOCAL_SUBNETS_CONFIG_PATH

GITHUB_SUBNETS_SCRIPTS_PATH = settings.GITHUB_SUBNETS_SCRIPTS_PATH
LOCAL_SUBNETS_SCRIPTS_PATH = settings.LOCAL_SUBNETS_SCRIPTS_PATH

GITHUB_VALIDATORS_CONFIG_PATH = settings.GITHUB_VALIDATORS_CONFIG_PATH
LOCAL_VALIDATORS_CONFIG_PATH = settings.LOCAL_VALIDATORS_CONFIG_PATH

BITTENSOR_WALLET_PATH = settings.BITTENSOR_WALLET_PATH
BITTENSOR_WALLET_NAME = settings.BITTENSOR_WALLET_NAME
BITTENSOR_HOTKEY_NAME = settings.BITTENSOR_HOTKEY_NAME
VALIDATOR_SECRET_VALUE_TYPES = settings.VALIDATOR_SECRET_VALUE_TYPES
MAINNET_CHAIN_ENDPOINT = settings.MAINNET_CHAIN_ENDPOINT
TESTNET_CHAIN_ENDPOINT = settings.TESTNET_CHAIN_ENDPOINT


def fetch_and_compare_subnets(request: requests.Request) -> requests.Response | HttpResponse | HttpResponseRedirect:
    github_data = load_local_subnets_config()
    github_data_list = prepare_subnet_data_for_comparison(github_data)

    db_data = list(Subnet.objects.values())
    db_data = [{k: v for k, v in subnet.items() if k != "id"} for subnet in db_data]

    diff_str = generate_diff(db_data, github_data_list, "db_data", "github_data")

    if request.method == "POST":
        for subnet_data in github_data_list:
            Subnet.objects.update_or_create(codename=subnet_data.get("codename"), defaults=subnet_data)
        return redirect("admin:core_subnet_changelist")

    return render(
        request,
        "admin/sync_subnets.html",
        {
            "diff_str": diff_str,
            "github_data": json.dumps(github_data, indent=2),
        },
    )


def fetch_and_compare_validators(request: requests.Request) -> requests.Response | HttpResponse | HttpResponseRedirect:
    github_validators = load_validators_from_yaml(LOCAL_VALIDATORS_CONFIG_PATH)
    github_sorted = prepare_validator_data_for_comparison(github_validators)

    db_validators = fetch_db_validators()
    db_sorted = prepare_validator_data_for_comparison(db_validators)

    diff_str = generate_diff(db_sorted, github_sorted, "db_data", "github_data")

    if request.method == "POST":
        try:
            sync_validators(
                validator_model=Validator,
                subnet_model=Subnet,
                external_hotkey_model=ExternalHotkey,
                validator_hotkey_model=ValidatorHotkey,
            )
            return redirect("admin:core_validator_changelist")
        except Exception as e:
            return render(
                request,
                "admin/sync_validators_error.html",
                {"error": f"An error occurred during synchronization: {str(e)}"},
            )

    return render(
        request,
        "admin/sync_validators.html",
        {
            "diff_str": diff_str,
            "github_data": json.dumps(github_sorted, indent=2),
        },
    )


def fetch_db_validators() -> list[dict]:
    db_validators = []
    validators = Validator.objects.all().prefetch_related("validatorhotkey_set__external_hotkey")
    for validator in validators:
        db_validator = {
            "short_name": validator.short_name,
            "long_name": validator.long_name,
            "last_stake": validator.last_stake,
            "default_hotkey": validator.default_hotkey.hotkey if validator.default_hotkey else None,
            "subnet_hotkeys": {},
        }
        for vh in validator.validatorhotkey_set.filter(is_default=False):
            subnet_codename = vh.external_hotkey.subnet.codename if vh.external_hotkey.subnet else None
            if subnet_codename not in db_validator["subnet_hotkeys"]:
                db_validator["subnet_hotkeys"][subnet_codename] = []
            db_validator["subnet_hotkeys"][subnet_codename].append(vh.external_hotkey.hotkey)
        db_validators.append(db_validator)
    return db_validators


def render_delegate_stake_form(request, form, subnets, csv_ids) -> HttpResponse:
    context = {
        "form": form,
        "subnets": subnets,
        "csv_ids": csv_ids,
        "title": "Delegate Stake",
    }
    return render(
        request,
        "admin/delegate_stake.html",
        context,
    )


def process_delegate_stake_form(request, form) -> None:
    cleaned_data = form.clean()
    for field_name, value in cleaned_data.items():
        if value is not None and value != "":
            parts = field_name.split("_")
            if len(parts) == 2 and parts[0] == "stake":
                external_hotkey_id = int(parts[1])
                percentage = float(value)

                external_hotkey = ExternalHotkey.objects.get(id=external_hotkey_id)
                external_hotkey.delegate_stake_percentage = percentage
                external_hotkey.save()


def get_user_ip(request: requests.Request) -> str:
    ip_address = request.META.get("HTTP_X_FORWARDED_FOR")
    if ip_address:
        ip_address = ip_address.split(",")[0]
    else:
        ip_address = request.META.get("REMOTE_ADDR")
    return ip_address


def generate_pre_config_file(
    subnet_codename: str, blockchain: str, netuid: int, remote_ip_address: str, yaml_file_path: str, csv_file_path: str
):
    yaml_file_path = os.path.expanduser(yaml_file_path)
    csv_file_path = os.path.expanduser(csv_file_path)
    pre_config_path = os.path.expanduser(f"{LOCAL_SUBNETS_SCRIPTS_PATH}/{subnet_codename}/pre_config.json")
    with open(yaml_file_path) as file:
        data = yaml.safe_load(file)
    if subnet_codename not in data:
        raise ValueError("Subnet codename %s not found in YAML file.", subnet_codename)
    allowed_secrets = data[subnet_codename].get("allowed_secrets", [])

    secrets = {}
    with open(csv_file_path) as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            if row["SECRET_KEYS"] in allowed_secrets:
                if row["SECRET_VALUES"] == VALIDATOR_SECRET_VALUE_TYPES.get("RANDOM"):
                    secrets[row["SECRET_KEYS"]] = os.urandom(32).hex()
                elif row["SECRET_VALUES"] == VALIDATOR_SECRET_VALUE_TYPES.get("HOTKEY_SS58_ADDRESS"):
                    secrets[row["SECRET_KEYS"]] = bt.Wallet(
                        name=BITTENSOR_WALLET_NAME, hotkey=BITTENSOR_HOTKEY_NAME
                    ).hotkey.ss58_address
                elif row["SECRET_VALUES"] == VALIDATOR_SECRET_VALUE_TYPES.get("IP_ADDRESS"):
                    secrets[row["SECRET_KEYS"]] = remote_ip_address
                else:
                    secrets[row["SECRET_KEYS"]] = row["SECRET_VALUES"]
    secrets["SUBNET_CODENAME"] = subnet_codename
    secrets["BITTENSOR_NETWORK"] = "finney" if blockchain == "mainnet" else "test"
    secrets["BITTENSOR_CHAIN_ENDPOINT"] = MAINNET_CHAIN_ENDPOINT if blockchain == "mainnet" else TESTNET_CHAIN_ENDPOINT
    secrets["BITTENSOR_NETUID"] = netuid

    with open(pre_config_path, "w") as file:
        json.dump(secrets, file, indent=4)

    return pre_config_path


def install_validator_on_remote_server(
    subnet_codename: str,
    blockchain: str,
    netuid: int,
    ssh_ip_address: str,
    ssh_user: str,
    ssh_key_path: str,
    ssh_passphrase: str,
) -> dict:
    subnet_config_file_path = LOCAL_SUBNETS_CONFIG_PATH
    csv_file_path = os.path.abspath("../../secrets.csv")

    local_hotkey_path = BITTENSOR_WALLET_PATH / BITTENSOR_WALLET_NAME / "hotkeys" / BITTENSOR_HOTKEY_NAME
    local_coldkeypub_path = BITTENSOR_WALLET_PATH / BITTENSOR_WALLET_NAME / "coldkeypub.txt"

    generate_pre_config_file(
        subnet_codename, blockchain, netuid, ssh_ip_address, subnet_config_file_path, csv_file_path
    )

    # Extract remote path from .env.template file
    local_env_template_path = os.path.expanduser(LOCAL_SUBNETS_SCRIPTS_PATH / subnet_codename / ".env.template")

    with open(local_env_template_path) as env_file:
        for line in env_file:
            if line.startswith("TARGET_PATH"):
                remote_path = line.split("=")[1].strip()
                break
    local_directory = os.path.expanduser(LOCAL_SUBNETS_SCRIPTS_PATH / subnet_codename)
    local_files = [
        os.path.join(local_directory, file)
        for file in os.listdir(local_directory)
        if os.path.isfile(os.path.join(local_directory, file))
    ]
    local_generator_path = os.path.abspath("auto_validator/core/utils/generate_env.py")
    local_files.append(local_generator_path)
    with SSH_Manager(ssh_ip_address, ssh_user, ssh_key_path, ssh_passphrase) as ssh_manager:
        ssh_manager.copy_files_to_remote(local_files, remote_path)

        remote_hotkey_path = "~/.bittensor/wallets/validator/hotkeys/validator-hotkey"
        local_hotkey_file = [str(local_hotkey_path)]
        ssh_manager.copy_files_to_remote(local_hotkey_file, remote_hotkey_path)

        remote_coldkey_path = "~/.bittensor/wallets/validator/"
        local_coldkey_file = [str(local_coldkeypub_path)]
        ssh_manager.copy_files_to_remote(local_coldkey_file, remote_coldkey_path)

        # Generate .env file on remote server
        remote = pathlib.Path(remote_path)
        remote_env_template_path = remote / ".env.template"
        remote_pre_config_path = remote / "pre_config.json"
        remote_env_path = remote / ".env"
        command = f"python3 {os.path.join(remote_path, 'generate_env.py')} {remote_env_template_path} {remote_pre_config_path} {remote_env_path}"
        try:
            ssh_manager.execute_command(command)

            # Run install.sh on remote server
            remote_install_script_path = remote / "install.sh"
            ssh_manager.execute_command(f"bash {remote_install_script_path}")
            return {"status": "success", "message": "Validator installed successfully."}
        except Exception as e:
            return {"status": "error", "message": str(e)}


def get_dumper_commands(subnet_identifier: str, config_path: str) -> list:
    """
    Get dumper commands for a subnet with normalized subnet identifier.

    Examples:
        >>> get_dumper_commands("sn1", "subnets.yaml")
    """
    with open(config_path) as file:
        data = yaml.safe_load(file)
        codename_lower = subnet_identifier.lower()
        for codename, sn_config in data.items():
            mainnet_netuid = sn_config.get("mainnet_netuid")
            testnet_netuid = sn_config.get("testnet_netuid")
            possible_codenames = [str(mainnet_netuid), "sn" + str(mainnet_netuid), str(testnet_netuid), codename]
            if codename_lower in map(str.lower, possible_codenames):
                return sn_config.get("dumper_commands", [])
        return None


def load_local_subnets_config() -> list[dict]:
    try:
        return load_yaml_data(LOCAL_SUBNETS_CONFIG_PATH)
    except Exception as e:
        raise Exception(f"An error occurred while loading the local file: {str(e)}")
