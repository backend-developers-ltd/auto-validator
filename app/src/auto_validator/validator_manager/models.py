from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


def validate_hotkey_length(value):
    if len(value) != 48:
        raise ValidationError("Hotkey must be exactly 48 characters long.")


class Subnet(models.Model):
    codename = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.codename


class Validator(models.Model):
    short_name = models.CharField(max_length=255, unique=True)
    long_name = models.CharField(max_length=255, unique=True)
    last_stake = models.IntegerField()
    subnets = models.ManyToManyField(Subnet, related_name="validator_list", blank=True)

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
    subnet = models.ForeignKey(
        Subnet, on_delete=models.SET_NULL, related_name="external_hotkeys", null=True, blank=True
    )

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
                fields=["validator"],
                condition=Q(is_default=True),
                name="validator_manager_unique_default_hotkey_per_validator",
            ),
            models.UniqueConstraint(
                fields=["external_hotkey"], name="validator_manager_unique_external_hotkey_assignment"
            ),
        ]

    def __str__(self):
        role = "Default" if self.is_default else "Subnet"
        return f"{self.validator} - {self.external_hotkey} ({role})"
