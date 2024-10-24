import structlog
from celery import shared_task
from celery.utils.log import get_task_logger

from auto_validator.utils.sync_utils import sync_validators

from .models import ExternalHotkey, Subnet, Validator, ValidatorHotkey

logger = structlog.wrap_logger(get_task_logger(__name__))


@shared_task(bind=True)
def sync_validators_task_validator_manager(self):
    logger.info("[Validator Manager] Running sync_validators().")
    sync_validators(
        validator_model=Validator,
        subnet_model=Subnet,
        external_hotkey_model=ExternalHotkey,
        validator_hotkey_model=ValidatorHotkey,
        validator_manager_sync=True,
    )
