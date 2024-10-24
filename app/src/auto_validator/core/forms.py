from django import forms
from django.db.models import Prefetch

from .models import ExternalHotkey, Validator, ValidatorHotkey


class DelegateStakeForm(forms.Form):
    def __init__(self, *args, **kwargs):
        subnets = kwargs.pop("subnets", None)
        super().__init__(*args, **kwargs)

        self.grouped_fields = {}
        self.default_hotkeys = []

        subnets = subnets.prefetch_related(
            Prefetch(
                "validator_list",
                queryset=Validator.objects.prefetch_related(
                    Prefetch("validatorhotkey_set", queryset=ValidatorHotkey.objects.select_related("external_hotkey"))
                ),
            )
        )

        for subnet in subnets:
            validators = subnet.validator_list.all()
            for validator in validators:
                subnet_validator_hotkeys = validator.validatorhotkey_set.filter(
                    is_default=False, external_hotkey__subnet=subnet
                ).select_related("external_hotkey")

                if subnet.name not in self.grouped_fields:
                    self.grouped_fields[subnet.name] = {}

                if validator.long_name not in self.grouped_fields[subnet.name]:
                    self.grouped_fields[subnet.name][validator.long_name] = []

                for validator_hotkey in subnet_validator_hotkeys:
                    external_hotkey = validator_hotkey.external_hotkey
                    field_name = f"stake_{external_hotkey.id}"
                    field_label = f"{external_hotkey.name}"
                    self.fields[field_name] = forms.FloatField(
                        label=field_label,
                        required=False,
                        min_value=0,
                        max_value=100,
                        initial=external_hotkey.delegate_stake_percentage,
                    )
                    hotkey_data = {
                        "field": self[field_name],
                        "field_label": field_label,
                        "validator": validator,
                    }

                    self.grouped_fields[subnet.name][validator.long_name].append(hotkey_data)

        default_hotkeys = (
            ExternalHotkey.objects.filter(validatorhotkey__is_default=True)
            .select_related("validatorhotkey__validator")
            .distinct()
        )

        for external_hotkey in default_hotkeys:
            field_name = f"stake_{external_hotkey.id}"
            field_label = f"{external_hotkey.name}"
            self.fields[field_name] = forms.FloatField(
                label=field_label,
                required=False,
                min_value=0,
                max_value=100,
                initial=external_hotkey.delegate_stake_percentage,
            )

            hotkey_data = {
                "field": self[field_name],
                "field_label": field_label,
                "validator": validator,
            }

            if external_hotkey not in self.default_hotkeys:
                self.default_hotkeys.append(hotkey_data)

    def clean(self):
        cleaned_data = super().clean()
        total_percentage = 0
        for field_name, value in cleaned_data.items():
            total_percentage += value or 0
        if total_percentage > 100:
            raise forms.ValidationError("Total stake percentage cannot be more then 100.")
        return cleaned_data
