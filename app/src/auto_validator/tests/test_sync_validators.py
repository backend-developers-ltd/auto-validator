from unittest.mock import patch

import pytest

from auto_validator.core.models import (
    ExternalHotkey as core_external_hotkey,
)
from auto_validator.core.models import (
    Subnet as core_subnet,
)
from auto_validator.core.models import (
    Validator as core_validator,
)
from auto_validator.core.models import (
    ValidatorHotkey as core_validator_hotkey,
)
from auto_validator.utils.sync_utils import sync_validators
from auto_validator.validator_manager.models import (
    ExternalHotkey as vm_external_hotkey,
)
from auto_validator.validator_manager.models import (
    Subnet as vm_subnet,
)
from auto_validator.validator_manager.models import (
    Validator as vm_validator,
)
from auto_validator.validator_manager.models import (
    ValidatorHotkey as vm_validator_hotkey,
)


def generate_hotkey(prefix, index):
    base = f"{prefix}_{index}"
    padding_length = 48 - len(base)
    return base + ("0" * padding_length)


@pytest.fixture(autouse=True)
def clear_db():
    # Clear models before each test
    vm_external_hotkey.objects.all().delete()
    vm_subnet.objects.all().delete()
    vm_validator.objects.all().delete()
    vm_validator_hotkey.objects.all().delete()
    core_external_hotkey.objects.all().delete()
    core_subnet.objects.all().delete()
    core_validator.objects.all().delete()
    core_validator_hotkey.objects.all().delete()


@pytest.mark.django_db(transaction=True)
@patch("auto_validator.utils.sync_utils.load_validators_from_yaml")
def test_validator_manager_validators_sync_success(mock_load_validators_from_yaml):
    mock_response_data = [
        {
            "short_name": "OTF",
            "long_name": "Opentensor Foundation",
            "last_stake": 1064117,
            "default_hotkey": generate_hotkey("hk_default_OTF", 1),
            "subnet_hotkeys": {
                "macrocosm-os": [generate_hotkey("hk_subnet1_OTF", 1), generate_hotkey("hk_subnet1_OTF", 2)],
                "omron": [generate_hotkey("hk_subnet2_OTF", 1), generate_hotkey("hk_subnet2_OTF", 2)],
            },
        },
        {
            "short_name": "Foundry",
            "long_name": "Foundry",
            "last_stake": 123456,
            "default_hotkey": generate_hotkey("hk_default_Foundry", 1),
            "subnet_hotkeys": {
                "ComputeHorde": [generate_hotkey("hk_subnet1_Foundry", 1), generate_hotkey("hk_subnet1_Foundry", 2)],
                "omron": [generate_hotkey("hk_subnet2_Foundry", 1)],
            },
        },
    ]

    mock_load_validators_from_yaml.return_value = mock_response_data

    sync_validators(
        validator_model=vm_validator,
        subnet_model=vm_subnet,
        external_hotkey_model=vm_external_hotkey,
        validator_hotkey_model=vm_validator_hotkey,
        validator_manager_sync=True,
    )

    otf = vm_validator.objects.get(short_name="OTF")
    assert otf.long_name == "Opentensor Foundation"
    assert otf.last_stake == 1064117
    assert otf.default_hotkey is not None
    assert otf.default_hotkey.hotkey == generate_hotkey("hk_default_OTF", 1)
    assert otf.subnets.count() == 2

    foundry = vm_validator.objects.get(short_name="Foundry")
    assert foundry.long_name == "Foundry"
    assert foundry.last_stake == 123456
    assert foundry.default_hotkey is not None
    assert foundry.default_hotkey.hotkey == generate_hotkey("hk_default_Foundry", 1)
    assert foundry.subnets.count() == 2

    subnet_macrocosm_os = vm_subnet.objects.get(codename="macrocosm-os")
    subnet_omron = vm_subnet.objects.get(codename="omron")
    assert subnet_macrocosm_os in otf.subnets.all()
    assert subnet_omron in otf.subnets.all()

    subnet_compute_horde = vm_subnet.objects.get(codename="ComputeHorde")
    subnet_omron_foundry = vm_subnet.objects.get(codename="omron")
    assert subnet_compute_horde in foundry.subnets.all()
    assert subnet_omron_foundry in foundry.subnets.all()

    otf_external_hotkeys = vm_external_hotkey.objects.filter(validatorhotkey__validator=otf)
    expected_otf_hotkeys = {
        generate_hotkey("hk_default_OTF", 1),
        generate_hotkey("hk_subnet1_OTF", 1),
        generate_hotkey("hk_subnet1_OTF", 2),
        generate_hotkey("hk_subnet2_OTF", 1),
        generate_hotkey("hk_subnet2_OTF", 2),
    }
    actual_otf_hotkeys = set(otf_external_hotkeys.values_list("hotkey", flat=True))
    assert actual_otf_hotkeys == expected_otf_hotkeys

    foundry_external_hotkeys = vm_external_hotkey.objects.filter(validatorhotkey__validator=foundry)
    expected_foundry_hotkeys = {
        generate_hotkey("hk_default_Foundry", 1),
        generate_hotkey("hk_subnet1_Foundry", 1),
        generate_hotkey("hk_subnet1_Foundry", 2),
        generate_hotkey("hk_subnet2_Foundry", 1),
    }
    actual_foundry_hotkeys = set(foundry_external_hotkeys.values_list("hotkey", flat=True))
    assert actual_foundry_hotkeys == expected_foundry_hotkeys


@pytest.mark.django_db(transaction=True)
@patch("auto_validator.utils.sync_utils.load_validators_from_yaml")
def test_core_validators_sync_no_subnets_success(mock_load_validators_from_yaml):
    mock_response_data = [
        {
            "short_name": "OTF",
            "long_name": "Opentensor Foundation",
            "last_stake": 1064117,
            "default_hotkey": generate_hotkey("hk_default_OTF", 1),
            "subnet_hotkeys": {
                "macrocosm-os": [
                    generate_hotkey("hk_subnet1_OTF", 1),
                ],
                "omron": [
                    generate_hotkey("hk_subnet2_OTF", 1),
                ],
            },
        },
        {
            "short_name": "Foundry",
            "long_name": "Foundry",
            "last_stake": 123456,
            "default_hotkey": generate_hotkey("hk_default_Foundry", 1),
            "subnet_hotkeys": {
                "ComputeHorde": [
                    generate_hotkey("hk_subnet1_Foundry", 1),
                ],
                "omron": [generate_hotkey("hk_subnet2_Foundry", 1)],
            },
        },
    ]

    mock_load_validators_from_yaml.return_value = mock_response_data

    sync_validators(
        validator_model=core_validator,
        subnet_model=core_subnet,
        external_hotkey_model=core_external_hotkey,
        validator_hotkey_model=core_validator_hotkey,
    )

    otf = core_validator.objects.get(short_name="OTF")
    assert otf.long_name == "Opentensor Foundation"
    assert otf.last_stake == 1064117
    assert otf.default_hotkey is not None
    assert otf.default_hotkey.hotkey == generate_hotkey("hk_default_OTF", 1)
    assert otf.subnets.count() == 0

    foundry = core_validator.objects.get(short_name="Foundry")
    assert foundry.long_name == "Foundry"
    assert foundry.last_stake == 123456
    assert foundry.default_hotkey is not None
    assert foundry.default_hotkey.hotkey == generate_hotkey("hk_default_Foundry", 1)
    assert foundry.subnets.count() == 0

    otf_external_hotkeys = core_external_hotkey.objects.filter(validatorhotkey__validator=otf)
    expected_otf_hotkeys = {
        generate_hotkey("hk_default_OTF", 1),
    }
    actual_otf_hotkeys = set(otf_external_hotkeys.values_list("hotkey", flat=True))
    assert actual_otf_hotkeys == expected_otf_hotkeys

    foundry_external_hotkeys = core_external_hotkey.objects.filter(validatorhotkey__validator=foundry)
    expected_foundry_hotkeys = {
        generate_hotkey("hk_default_Foundry", 1),
    }
    actual_foundry_hotkeys = set(foundry_external_hotkeys.values_list("hotkey", flat=True))
    assert actual_foundry_hotkeys == expected_foundry_hotkeys
    assert core_subnet.objects.count() == 0


@pytest.mark.django_db(transaction=True)
@patch("auto_validator.utils.sync_utils.load_validators_from_yaml")
def test_sync_validators_with_existing_subnets(mock_load_validators_from_yaml):
    """
    Test that validators are correctly synchronized with existing subnets.
    Ensures that existing subnets are used and not duplicated.
    """
    (
        core_subnet.objects.create(
            name="Macrocosm OS",
            codename="macrocosm-os",
            description="Existing subnet for Macrocosm OS",
            # Add other required fields if any
        ),
    )
    (
        core_subnet.objects.create(
            name="Omron",
            codename="omron",
            description="Existing subnet for Omron",
        ),
    )
    core_subnet.objects.create(
        name="ComputeHorde",
        codename="ComputeHorde",
        description="Existing subnet for ComputeHorde",
    )

    mock_response_data = [
        {
            "short_name": "OTF",
            "long_name": "Opentensor Foundation",
            "last_stake": 1064117,
            "default_hotkey": generate_hotkey("hk_default_OTF", 1),
            "subnet_hotkeys": {
                "macrocosm-os": [
                    generate_hotkey("hk_subnet1_OTF", 1),
                ],
                "omron": [
                    generate_hotkey("hk_subnet2_OTF", 1),
                ],
            },
        },
        {
            "short_name": "Foundry",
            "long_name": "Foundry",
            "last_stake": 123456,
            "default_hotkey": generate_hotkey("hk_default_Foundry", 1),
            "subnet_hotkeys": {
                "ComputeHorde": [
                    generate_hotkey("hk_subnet1_Foundry", 1),
                ],
                "omron": [generate_hotkey("hk_subnet2_Foundry", 1)],
            },
        },
    ]

    mock_load_validators_from_yaml.return_value = mock_response_data

    sync_validators(
        validator_model=core_validator,
        subnet_model=core_subnet,
        external_hotkey_model=core_external_hotkey,
        validator_hotkey_model=core_validator_hotkey,
        validator_manager_sync=True,
    )

    otf = core_validator.objects.get(short_name="OTF")
    assert otf.long_name == "Opentensor Foundation"
    assert otf.last_stake == 1064117
    assert otf.default_hotkey is not None
    assert otf.default_hotkey.hotkey == generate_hotkey("hk_default_OTF", 1)
    assert otf.subnets.count() == 2

    foundry = core_validator.objects.get(short_name="Foundry")
    assert foundry.long_name == "Foundry"
    assert foundry.last_stake == 123456
    assert foundry.default_hotkey is not None
    assert foundry.default_hotkey.hotkey == generate_hotkey("hk_default_Foundry", 1)
    assert foundry.subnets.count() == 2

    subnet_macrocosm_os = core_subnet.objects.get(codename="macrocosm-os")
    subnet_omron = core_subnet.objects.get(codename="omron")
    assert subnet_macrocosm_os in otf.subnets.all()
    assert subnet_omron in otf.subnets.all()

    subnet_compute_horde = core_subnet.objects.get(codename="ComputeHorde")
    subnet_omron_foundry = core_subnet.objects.get(codename="omron")
    assert subnet_compute_horde in foundry.subnets.all()
    assert subnet_omron_foundry in foundry.subnets.all()

    otf_external_hotkeys = core_external_hotkey.objects.filter(validatorhotkey__validator=otf)
    expected_otf_hotkeys = {
        generate_hotkey("hk_default_OTF", 1),
        generate_hotkey("hk_subnet1_OTF", 1),
        generate_hotkey("hk_subnet2_OTF", 1),
    }
    actual_otf_hotkeys = set(otf_external_hotkeys.values_list("hotkey", flat=True))
    assert actual_otf_hotkeys == expected_otf_hotkeys

    foundry_external_hotkeys = core_external_hotkey.objects.filter(validatorhotkey__validator=foundry)
    expected_foundry_hotkeys = {
        generate_hotkey("hk_default_Foundry", 1),
        generate_hotkey("hk_subnet1_Foundry", 1),
        generate_hotkey("hk_subnet2_Foundry", 1),
    }
    actual_foundry_hotkeys = set(foundry_external_hotkeys.values_list("hotkey", flat=True))
    assert actual_foundry_hotkeys == expected_foundry_hotkeys

    assert core_subnet.objects.count() == 3


@pytest.mark.django_db(transaction=True)
@patch("auto_validator.utils.sync_utils.load_validators_from_yaml")
def test_sync_validators_removes_old_hotkeys(mock_load_validators_from_yaml):
    old_hotkey_value = generate_hotkey("old_hotkey_OTF", 1)
    new_hotkey_value = generate_hotkey("new_hotkey_OTF", 1)
    default_hotkey_value = generate_hotkey("default_hotkey_OTF", 1)

    # Setup initial database state with OTF
    otf_validator = vm_validator.objects.create(long_name="Opentensor Foundation", short_name="OTF", last_stake=500)
    subnet_macrocosm_os = vm_subnet.objects.create(codename="macrocosm-os")
    old_hotkey = vm_external_hotkey.objects.create(
        hotkey=old_hotkey_value, name="OTF-macrocosm-os", subnet=subnet_macrocosm_os
    )
    vm_validator_hotkey.objects.create(validator=otf_validator, external_hotkey=old_hotkey, is_default=False)
    otf_validator.subnets.add(subnet_macrocosm_os)

    # Mock data with updated hotkeys
    mock_response_data = [
        {
            "short_name": "OTF",
            "long_name": "Opentensor Foundation",
            "last_stake": 1000,
            "default_hotkey": default_hotkey_value,
            "subnet_hotkeys": {
                "macrocosm-os": [new_hotkey_value],  # Replacing old hotkey
                "omron": [generate_hotkey("hk_subnet2_OTF", 1), generate_hotkey("hk_subnet2_OTF", 2)],
            },
        }
    ]

    mock_load_validators_from_yaml.return_value = mock_response_data

    sync_validators(
        validator_model=vm_validator,
        subnet_model=vm_subnet,
        external_hotkey_model=vm_external_hotkey,
        validator_hotkey_model=vm_validator_hotkey,
        validator_manager_sync=True,
    )

    # Refresh validator from DB
    otf_validator.refresh_from_db()

    # Assertions
    assert otf_validator.last_stake == 1000
    assert otf_validator.default_hotkey.hotkey == default_hotkey_value

    # Old hotkey should be removed
    assert not vm_external_hotkey.objects.filter(hotkey=old_hotkey_value).exists()

    # New hotkey should exist
    assert vm_external_hotkey.objects.filter(hotkey=new_hotkey_value).exists()

    # New subnet 'omron' should be added with its hotkeys
    subnet_omron = vm_subnet.objects.get(codename="omron")
    assert subnet_omron in otf_validator.subnets.all()

    # Validate new external hotkeys
    otf_external_hotkeys = vm_external_hotkey.objects.filter(validatorhotkey__validator=otf_validator)
    expected_otf_hotkeys = {
        default_hotkey_value,
        new_hotkey_value,
        generate_hotkey("hk_subnet2_OTF", 1),
        generate_hotkey("hk_subnet2_OTF", 2),
    }
    actual_otf_hotkeys = set(otf_external_hotkeys.values_list("hotkey", flat=True))
    assert actual_otf_hotkeys == expected_otf_hotkeys


@pytest.mark.django_db
@patch("auto_validator.utils.sync_utils.load_validators_from_yaml")
def test_sync_validators_fetch_failure(mock_load_validators_from_yaml):
    # Simulate an exception when loading validators
    mock_load_validators_from_yaml.side_effect = Exception("File read error")

    with pytest.raises(Exception) as exc_info:
        sync_validators(
            validator_model=core_validator,
            subnet_model=core_subnet,
            external_hotkey_model=core_external_hotkey,
            validator_hotkey_model=core_validator_hotkey,
        )

    assert "File read error" in str(exc_info.value)
    assert core_validator.objects.count() == 0


@pytest.mark.django_db
@patch("auto_validator.utils.sync_utils.load_validators_from_yaml")
def test_sync_validators_invalid_data_missing_fields(mock_load_validators_from_yaml):
    mock_response_data = [
        {
            "short_name": "OTF",
            # "long_name" is missing
            "last_stake": 1000,
            "default_hotkey": None,
            "subnet_hotkeys": {},
        },
        {
            "short_name": "Foundry",
            "long_name": "Foundry",
            # "last_stake" is missing
            "default_hotkey": None,
            "subnet_hotkeys": {},
        },
    ]

    mock_load_validators_from_yaml.return_value = mock_response_data

    with pytest.raises(KeyError) as exc_info:
        sync_validators(
            validator_model=core_validator,
            subnet_model=core_subnet,
            external_hotkey_model=core_external_hotkey,
            validator_hotkey_model=core_validator_hotkey,
        )

    assert "'long_name'" in str(exc_info.value)
    assert core_validator.objects.count() == 0
