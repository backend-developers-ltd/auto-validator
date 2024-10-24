import os
import shutil

import bittensor as bt  # type: ignore
import structlog
from celery import shared_task  # type: ignore
from celery.utils.log import get_task_logger  # type: ignore
from constance import config
from django.conf import settings
from git import GitCommandError, Repo

from auto_validator.celery import app
from auto_validator.utils.sync_utils import sync_validators

from .models import ExternalHotkey, Subnet, SubnetSlot, Validator, ValidatorHotkey, ValidatorInstance

GITHUB_SUBNETS_SCRIPTS_PATH = settings.GITHUB_SUBNETS_SCRIPTS_PATH
LOCAL_SUBNETS_SCRIPTS_PATH = settings.LOCAL_SUBNETS_SCRIPTS_PATH

logger = structlog.wrap_logger(get_task_logger(__name__))


@app.task
def demo_task(x, y):
    logger.info("adding two numbers", x=x, y=y)
    return x + y


@app.task
def schedule_update_validator_status():
    subnet_slots = SubnetSlot.objects.order_by("id")
    for slot in subnet_slots:
        update_validator_status_for_slot.delay(slot.id)


@shared_task
def update_validator_status_for_slot(slot_id):
    try:
        slot = SubnetSlot.objects.get(id=slot_id)
    except SubnetSlot.DoesNotExist:
        logger.warning(f"Subnet slot with ID {slot_id} does not exist.")
        return

    try:
        subtensor = bt.subtensor(network=settings.BT_NETWORK_NAME)
        validators = ValidatorInstance.objects.filter(subnet_slot=slot)
        if validators.exists():
            metagraph = subtensor.metagraph(netuid=slot.netuid, lite=True)
            current_block = subtensor.get_current_block()
            for validator in validators:
                last_updated = fetch_last_updated_from_metagraph(metagraph, validator.hotkey.hotkey)
                validator.last_updated = current_block - last_updated
                validator.save()
                logger.info(f"Validator:{validator.hotkey}, subnet slot:{slot} was successfully updated!")
        else:
            logger.warning(f"No validators found for subnet slot with ID {slot.id}.")
    except Exception:
        logger.exception("Failed to update validators for subnet slot on %s", slot)
    finally:
        subtensor.close()


def fetch_last_updated_from_metagraph(metagraph, public_key):
    return metagraph.last_update[metagraph.hotkeys.index(public_key)]


@app.task
def schedule_fetch_subnet_scripts():
    fetch_subnet_scripts.delay()


@shared_task
def fetch_subnet_scripts():
    logger.info("Fetching subnet scripts")
    try:
        # Clone the subnet scripts repository using GitPython
        if os.path.exists(LOCAL_SUBNETS_SCRIPTS_PATH):
            # If the directory already exists, remove it
            shutil.rmtree(LOCAL_SUBNETS_SCRIPTS_PATH)

        Repo.clone_from(GITHUB_SUBNETS_SCRIPTS_PATH, LOCAL_SUBNETS_SCRIPTS_PATH)
    except GitCommandError as e:
        logger.error(f"Error while cloning the repository: {e}")
        return

    logger.info("Successfully fetched subnet scripts")
    return


@shared_task
def sync_validators_task_core():
    if not config.ENABLE_VALIDATOR_AUTO_SYNC:
        logger.info("[Core] Auto-sync is disabled. Exiting task.")
        return
    logger.info("[Core] Auto-sync is enabled. Running sync_validators().")
    sync_validators(
        validator_model=Validator,
        subnet_model=Subnet,
        external_hotkey_model=ExternalHotkey,
        validator_hotkey_model=ValidatorHotkey,
    )
