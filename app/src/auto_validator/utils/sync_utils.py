import difflib
import json
import logging

import requests
import yaml
from django.conf import settings
from django.db import transaction
from requests.exceptions import RequestException

GITHUB_VALIDATORS_CONFIG_PATH = settings.GITHUB_VALIDATORS_CONFIG_PATH
LOCAL_VALIDATORS_CONFIG_PATH = settings.LOCAL_VALIDATORS_CONFIG_PATH

logger = logging.getLogger(__name__)


def sync_validators(
    validator_model,
    subnet_model,
    external_hotkey_model,
    validator_hotkey_model,
    validator_manager_sync: bool = False,
) -> None:
    try:
        validators = load_validators_from_yaml(LOCAL_VALIDATORS_CONFIG_PATH)
        with transaction.atomic():
            for validator_data in validators:
                process_validator(
                    validator_data,
                    validator_manager_sync,
                    validator_model,
                    subnet_model,
                    external_hotkey_model,
                    validator_hotkey_model,
                )
        logger.info("Synchronization completed successfully.")
    except Exception as e:
        logger.exception(f"An error occurred during synchronization: {str(e)}")
        raise


def process_validator(
    validator_data: dict,
    validator_manager_sync: bool,
    validator_model,
    subnet_model,
    external_hotkey_model,
    validator_hotkey_model,
) -> None:
    validator, _ = validator_model.objects.update_or_create(
        long_name=validator_data["long_name"],
        short_name=validator_data["short_name"],
        defaults={"last_stake": validator_data["last_stake"]},
    )

    associated_subnets = handle_hotkeys(
        validator, validator_data, validator_manager_sync, subnet_model, external_hotkey_model, validator_hotkey_model
    )

    if associated_subnets:
        validator.subnets.set(associated_subnets)
    else:
        validator.subnets.clear()

    cleanup_old_hotkeys(validator, validator_data, validator_hotkey_model)


def process_hotkey(
    validator,
    hotkey_value: str,
    name: str,
    subnet,
    is_default: bool,
    validator_manager_sync: bool,
    external_hotkey_model,
    validator_hotkey_model,
    current_default_hotkey=None,
) -> None:
    defaults = {
        "name": name,
        "subnet": subnet,
    }

    if not validator_manager_sync:
        defaults["delegate_stake_percentage"] = 0.0

    external_hotkey, _ = external_hotkey_model.objects.get_or_create(hotkey=hotkey_value, defaults=defaults)

    validator_hotkey_model.objects.update_or_create(
        validator=validator, external_hotkey=external_hotkey, defaults={"is_default": is_default}
    )

    if is_default and current_default_hotkey and current_default_hotkey != external_hotkey:
        # Remove old default hotkey if it's different
        validator_hotkey_model.objects.filter(
            validator=validator, external_hotkey=current_default_hotkey, is_default=True
        ).delete()


def handle_hotkeys(
    validator,
    validator_data: dict,
    validator_manager_sync: bool,
    subnet_model,
    external_hotkey_model,
    validator_hotkey_model,
) -> list:
    associated_subnets = []

    # Handle Default Hotkey
    default_hotkey_hk = validator_data.get("default_hotkey")
    if default_hotkey_hk:
        name = f"{validator.short_name}-default"
        subnet = None  # Default hotkey is not linked to a subnet
        is_default = True
        current_default_hotkey = validator.default_hotkey

        process_hotkey(
            validator=validator,
            hotkey_value=default_hotkey_hk,
            name=name,
            subnet=subnet,
            is_default=is_default,
            validator_manager_sync=validator_manager_sync,
            external_hotkey_model=external_hotkey_model,
            validator_hotkey_model=validator_hotkey_model,
            current_default_hotkey=current_default_hotkey,
        )
    else:
        # If no default_hotkey in YAML data, remove existing default if any
        validator_hotkey_model.objects.filter(validator=validator, is_default=True).delete()

    # Handle Subnet Hotkeys
    subnet_hotkeys = validator_data.get("subnet_hotkeys", {})
    for subnet_codename, hotkeys in subnet_hotkeys.items():
        if validator_manager_sync:
            subnet, _ = subnet_model.objects.get_or_create(
                codename=subnet_codename, defaults={"codename": subnet_codename}
            )
        else:
            subnet = subnet_model.objects.filter(codename=subnet_codename).first()

        if not subnet:
            continue

        associated_subnets.append(subnet)

        for idx, hk in enumerate(hotkeys):
            extension = f"[{idx}]" if idx > 0 else ""
            name = f"{validator.short_name}{extension}"
            is_default = False

            process_hotkey(
                validator=validator,
                hotkey_value=hk,
                name=name,
                subnet=subnet,
                is_default=is_default,
                validator_manager_sync=validator_manager_sync,
                external_hotkey_model=external_hotkey_model,
                validator_hotkey_model=validator_hotkey_model,
            )

    return associated_subnets


def cleanup_old_hotkeys(validator, validator_data: dict, validator_hotkey_model) -> None:
    existing_hk = validator_hotkey_model.objects.filter(validator=validator, is_default=False)
    subnet_hotkeys = validator_data.get("subnet_hotkeys", {})
    desired_hk = set(hk for hotkeys in subnet_hotkeys.values() for hk in hotkeys)
    for hk_instance in existing_hk:
        if hk_instance.external_hotkey.hotkey not in desired_hk:
            hk_instance.external_hotkey.delete()


def load_yaml_data(file_path: str) -> dict:
    with open(file_path) as file:
        data = yaml.safe_load(file)
    return data


def load_remote_validators_config() -> list[dict]:
    try:
        response = requests.get(GITHUB_VALIDATORS_CONFIG_PATH, timeout=30)
        response.raise_for_status()  # Raises HTTPError for bad responses (4xx/5xx)
    except RequestException as req_err:
        raise Exception(f"An error occurred while fetching the remote file: {req_err}")

    return yaml.safe_load(response.content)


def generate_diff(db_data: list[dict], yaml_data: list[dict], db_label: str, yaml_label: str) -> str:
    db_data_str = json.dumps(db_data, indent=2, sort_keys=True)
    yaml_data_str = json.dumps(yaml_data, indent=2, sort_keys=True)
    diff = difflib.unified_diff(
        db_data_str.splitlines(), yaml_data_str.splitlines(), fromfile=db_label, tofile=yaml_label, lineterm=""
    )
    return "\n".join(diff)


def prepare_validator_data_for_comparison(validators: list[dict]) -> list[dict]:
    return sorted(validators, key=lambda x: x["last_stake"], reverse=True)


def prepare_subnet_data_for_comparison(yaml_data: dict) -> list[dict]:
    data_list = []
    for codename, subnet in yaml_data.items():
        subnet["codename"] = codename
        subnet.pop("bittensor_id", None)
        subnet.pop("twitter", None)
        data_list.append(subnet)
    return data_list


def load_validators_from_yaml(file_path: str) -> list[dict]:
    data = load_yaml_data(file_path)
    validators = []
    for validator_short_name, validator_info in data.items():
        validators.append(
            {
                "short_name": validator_short_name,
                "long_name": validator_info.get("long_name"),
                "last_stake": validator_info.get("last_stake", 0),
                "default_hotkey": validator_info.get("default_hotkey"),
                "subnet_hotkeys": validator_info.get("subnet_hotkeys", {}),
            }
        )
    return validators
