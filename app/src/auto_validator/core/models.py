from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import models
from django.db.models import F, Q


def validate_hotkey_length(value):
    if len(value) != 48:
        raise ValidationError("Hotkey must be exactly 48 characters long.")


class UploadedFile(models.Model):
    hotkey = models.ForeignKey("Hotkey", on_delete=models.CASCADE)
    file_name = models.CharField(max_length=4095)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    storage_file_name = models.CharField(
        max_length=4095,
        db_comment="File name (id) in Django Storage",
    )
    file_size = models.PositiveBigIntegerField(db_comment="File size in bytes")

    def __str__(self):
        return f"{self.file_name!r} uploaded by {self.hotkey}"

    def get_full_url(self, request):
        """
        Return the full URL to the file, including the domain.
        """
        relative_url = default_storage.url(self.storage_file_name)
        return request.build_absolute_uri(relative_url)

    @property
    def url(self):
        return default_storage.url(self.storage_file_name)


class Block(models.Model):
    serial_number = models.IntegerField(primary_key=True, unique=True)
    timestamp = models.DateTimeField()

    def __str__(self):
        return f"{self.serial_number}"


class Subnet(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    operators = models.ManyToManyField("Operator", related_name="subnets", blank=True)
    codename = models.CharField(max_length=255, null=True, blank=True)
    mainnet_netuid = models.IntegerField(null=True, blank=True)
    testnet_netuid = models.IntegerField(null=True, blank=True)
    owner_nick = models.CharField(max_length=255, null=True, blank=True)
    owner_discord_id = models.CharField(max_length=255, null=True, blank=True)
    maintainer_discord_ids = ArrayField(models.CharField(max_length=255), null=True, blank=True)
    github_repo = models.CharField(max_length=255, null=True, blank=True)
    hardware_description = models.TextField(max_length=4095, null=True, blank=True)
    allowed_secrets = ArrayField(models.CharField(max_length=255), null=True, blank=True)
    dumper_commands = ArrayField(models.CharField(max_length=255), null=True, blank=True)

    def registered_networks(self):
        mainnet_slots = self.slots.filter(
            Q(
                Q(registration_block__isnull=False, deregistration_block__isnull=True)
                | Q(
                    registration_block__isnull=False,
                    deregistration_block__isnull=False,
                    registration_block__gt=F("deregistration_block"),
                )
            ),
            blockchain="mainnet",
        )
        testnet_slots = self.slots.filter(
            Q(
                Q(registration_block__isnull=False, deregistration_block__isnull=True)
                | Q(
                    registration_block__isnull=False,
                    deregistration_block__isnull=False,
                    registration_block__gt=F("deregistration_block"),
                )
            ),
            blockchain="testnet",
        )

        mainnet_indicator = f"sn{mainnet_slots.first().netuid}" if mainnet_slots.exists() else ""
        testnet_indicator = f"t{testnet_slots.first().netuid}" if testnet_slots.exists() else ""

        return f"{mainnet_indicator}{testnet_indicator}" or "-"

    def __str__(self):
        return self.name


class SubnetSlot(models.Model):
    subnet = models.ForeignKey(Subnet, on_delete=models.PROTECT, null=True, blank=True, related_name="slots")
    blockchain = models.CharField(max_length=50, choices=[("mainnet", "Mainnet"), ("testnet", "Testnet")])
    netuid = models.IntegerField()
    maximum_registration_price = models.IntegerField(default=0, help_text="Maximum registration price in RAO")
    registration_block = models.ForeignKey(
        "Block", on_delete=models.PROTECT, null=True, blank=True, related_name="registration_slots"
    )
    deregistration_block = models.ForeignKey(
        "Block", on_delete=models.PROTECT, null=True, blank=True, related_name="deregistration_slots"
    )
    restart_threshold = models.IntegerField(default=0)
    reinstall_threshold = models.IntegerField(default=0)

    def __str__(self):
        subnet_name = self.subnet.name if self.subnet else "No subnet"
        suffix = " (unregistered)" if self.registration_block and not self.registration_block else ""
        return f"{self.blockchain} / sn{self.netuid}: {subnet_name} {suffix}"


class Hotkey(models.Model):
    hotkey = models.CharField(max_length=48, validators=[validate_hotkey_length], unique=True)
    is_mother = models.BooleanField(default=False)

    def __str__(self):
        return self.hotkey


class ValidatorInstance(models.Model):
    subnet_slot = models.ForeignKey(SubnetSlot, on_delete=models.PROTECT, related_name="validator_instances")
    hotkey = models.ForeignKey(
        "Hotkey", on_delete=models.PROTECT, null=True, blank=True, related_name="validator_instances"
    )
    last_updated = models.PositiveIntegerField(null=True, blank=True)
    status = models.BooleanField(default=False)
    uses_child_hotkey = models.BooleanField(default=False)
    server = models.OneToOneField("Server", on_delete=models.PROTECT, related_name="validator_instances")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.hotkey)


class Validator(models.Model):
    short_name = models.CharField(max_length=255, unique=True)
    long_name = models.CharField(max_length=255, unique=True)
    last_stake = models.IntegerField()
    subnets = models.ManyToManyField("Subnet", related_name="validator_list", blank=True)

    def __str__(self):
        return self.long_name

    @property
    def default_hotkey(self):
        assignment = self.validatorhotkey_set.filter(is_default=True).first()
        return assignment.external_hotkey if assignment else None

    @property
    def subnet_hotkeys(self):
        assignments = self.validatorhotkey_set.filter(is_default=False)
        return ExternalHotkey.objects.filter(id__in=assignments.values_list("external_hotkey_id", flat=True))


class ExternalHotkey(models.Model):
    name = models.CharField(max_length=255)
    hotkey = models.CharField(max_length=48, validators=[validate_hotkey_length], unique=True)
    subnet = models.ForeignKey(Subnet, on_delete=models.PROTECT, related_name="external_hotkeys", null=True, blank=True)
    delegate_stake_percentage = models.FloatField(default=0.0)

    def __str__(self):
        return f"{self.name} ({self.hotkey})"

    @property
    def validator(self):
        return self.validatorhotkey.validator if hasattr(self, "validatorhotkey") else None

    @property
    def is_default(self):
        return self.validatorhotkey.is_default if hasattr(self, "validatorhotkey") else None


class ValidatorHotkey(models.Model):
    validator = models.ForeignKey(Validator, on_delete=models.CASCADE, related_name="validatorhotkey_set")
    external_hotkey = models.OneToOneField(ExternalHotkey, on_delete=models.CASCADE, related_name="validatorhotkey")
    is_default = models.BooleanField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["validator"], condition=Q(is_default=True), name="unique_default_hotkey_per_validator"
            ),
            models.UniqueConstraint(fields=["external_hotkey"], name="unique_external_hotkey_assignment"),
        ]

    def __str__(self):
        role = "Default" if self.is_default else "Subnet"
        return f"{self.validator} - {self.external_hotkey} ({role})"


class Operator(models.Model):
    name = models.CharField(max_length=255)
    discord_id = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class Server(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True)
    ip_address = models.GenericIPAddressField()
    ssh_private_key = models.CharField(
        max_length=255, null=True, blank=True, help_text="Path to the SSH private key file"
    )
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.ip_address
