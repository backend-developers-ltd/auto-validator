from constance import config
from django.contrib import admin, messages
from django.db.models import Case, IntegerField, Sum, Value, When
from django.shortcuts import redirect
from django.urls import path, reverse
from rest_framework.authtoken.admin import TokenAdmin

from auto_validator.core.models import (
    ExternalHotkey,
    Hotkey,
    Operator,
    Server,
    Subnet,
    SubnetSlot,
    UploadedFile,
    Validator,
    ValidatorHotkey,
    ValidatorInstance,
)
from auto_validator.core.utils.utils import (
    fetch_and_compare_subnets,
    fetch_and_compare_validators,
    process_delegate_stake_form,
    render_delegate_stake_form,
)

from .forms import DelegateStakeForm

admin.site.site_header = "auto_validator Administration"
admin.site.site_title = "auto_validator"
admin.site.index_title = "Welcome to auto_validator Administration"

TokenAdmin.raw_id_fields = ["user"]


@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ("file_name", "file_size", "hotkey", "description", "created_at")
    list_filter = ("hotkey", "created_at", "file_size")
    search_fields = ("file_name",)


@admin.register(Subnet)
class SubnetAdmin(admin.ModelAdmin):
    list_display = (
        "codename",
        "description",
        "mainnet_netuid",
        "testnet_netuid",
        "owner_nick",
        "registered_networks",
        "delegated_stake_percentage",
    )
    search_fields = ("name", "slots__netuid")

    @admin.action(description="Delegate stake")
    def delegate_stake(self, request, queryset):
        selected_ids = ",".join(map(str, queryset.values_list("id", flat=True)))
        return redirect(reverse("admin:delegate_stake_confirm") + f"?ids={selected_ids}")

    def delegate_stake_confirm(self, request):
        if request.method == "POST" and "apply" in request.POST:
            ids = request.POST.get("ids", "").split(",")
            subnets = Subnet.objects.filter(id__in=ids)
            form = DelegateStakeForm(request.POST, subnets=subnets)
            if form.is_valid():
                process_delegate_stake_form(request, form)
                self.message_user(request, "Stake delegated successfully.", messages.SUCCESS)
                return redirect("..")
            else:
                messages.error(request, "Please correct the errors below.")
                csv_ids = ",".join(map(str, subnets.values_list("id", flat=True)))
                return render_delegate_stake_form(request, form, subnets, csv_ids)
        else:
            ids = request.GET.get("ids", "")
            subnets = Subnet.objects.filter(id__in=ids.split(","))
            csv_ids = ",".join(map(str, subnets.values_list("id", flat=True)))
            form = DelegateStakeForm(subnets=subnets)
            return render_delegate_stake_form(request, form, subnets, csv_ids)

    actions = [delegate_stake]

    def create_server(self, request, queryset):
        subnet = queryset.first()
        return redirect("admin:select_provider", subnet_id=subnet.id)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("sync-subnets/", self.admin_site.admin_view(self.sync_subnet), name="sync_subnets"),
            path("sync-validators/", self.admin_site.admin_view(self.sync_validators), name="sync_validators"),
            path(
                "delegate-stake-confirm/",
                self.admin_site.admin_view(self.delegate_stake_confirm),
                name="delegate_stake_confirm",
            ),
            path(
                "automate-validators-sync/",
                self.admin_site.admin_view(self.automate_validators_sync),
                name="automate_validators_sync",
            ),
        ]
        return custom_urls + urls

    def sync_subnet(self, request):
        return fetch_and_compare_subnets(request)

    def sync_validators(self, request):
        return fetch_and_compare_validators(request)

    def automate_validators_sync(self, request):
        config.ENABLE_VALIDATOR_AUTO_SYNC = not config.ENABLE_VALIDATOR_AUTO_SYNC
        status = "enabled" if config.ENABLE_VALIDATOR_AUTO_SYNC else "disabled"
        messages.success(request, f"Automated validator sync has been {status}.")
        return redirect(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist")

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}

        extra_context["automate_validators_sync_url"] = reverse("admin:automate_validators_sync")
        extra_context["sync_subnets_url"] = reverse("admin:sync_subnets")
        extra_context["sync_validators_url"] = reverse("admin:sync_validators")
        extra_context["toggle_validator_auto_sync"] = (
            "Disable Validators Auto-Sync" if config.ENABLE_VALIDATOR_AUTO_SYNC else "Enable Validators Auto-Sync"
        )
        return super().changelist_view(request, extra_context=extra_context)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(total_delegate_percentage=Sum("external_hotkeys__delegate_stake_percentage"))
        return qs

    @admin.display(description="Delegated Stake", ordering="total_delegate_percentage")
    def delegated_stake_percentage(self, obj):
        total = obj.total_delegate_percentage or 0
        return f"{total:.2f}%"


@admin.register(SubnetSlot)
class SubnetSlotAdmin(admin.ModelAdmin):
    list_display = (
        "subnet",
        "blockchain",
        "netuid",
        "is_registered",
        "max_registration_price_RAO",
        "registration_block",
        "deregistration_block",
    )
    search_fields = ("subnet__name", "netuid")
    list_filter = ("blockchain",)
    list_select_related = ("subnet", "registration_block", "deregistration_block")

    def registration_block(self, obj):
        return obj.registration_block.serial_number if obj.registration_block else "N/A"

    registration_block.short_description = "Registration Block"

    def deregistration_block(self, obj):
        return obj.deregistration_block.serial_number if obj.deregistration_block else "N/A"

    deregistration_block.short_description = "Deregistration Block"

    def max_registration_price_RAO(self, obj):
        return f"{obj.maximum_registration_price} RAO"

    def is_registered(self, obj):
        return obj.registration_block is not None and obj.deregistration_block is None

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(
            is_registered_sort=Case(
                When(registration_block__isnull=False, deregistration_block__isnull=True, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
        return qs.order_by("blockchain", "netuid")

    is_registered.boolean = True
    is_registered.admin_order_field = "is_registered_sort"
    is_registered.short_description = "Is Registered"


@admin.register(ValidatorInstance)
class ValidatorInstanceAdmin(admin.ModelAdmin):
    list_display = ("subnet_slot", "hotkey", "last_updated", "status", "server", "created_at")
    search_fields = ("hotkey", "subnet_slot__subnet__name", "server__name")


@admin.register(Server)
class ServerAdmin(admin.ModelAdmin):
    list_display = ("name", "ip_address", "subnet_slot", "validatorinstance_status", "description", "created_at")
    search_fields = ("name", "ip_address", "validator_instances__subnet_slot__subnet__name")

    def subnet_slot(self, obj):
        return obj.validator_instances.subnet_slot if obj.validator_instances else "N/A"

    def validatorinstance_status(self, obj):
        return getattr(obj.validator_instances, "status", False)

    validatorinstance_status.boolean = True

    list_select_related = ("validator_instances", "validator_instances__subnet_slot")


class ValidatorHotkeyInline(admin.TabularInline):
    model = ValidatorHotkey
    extra = 1
    fields = ("external_hotkey", "is_default")
    autocomplete_fields = ("external_hotkey",)


class ValidatorHotkeyInlineForExternalHotkey(admin.StackedInline):
    model = ValidatorHotkey
    extra = 0
    max_num = 1
    fields = ("validator", "is_default")
    autocomplete_fields = ("validator",)
    verbose_name = "Validator"
    verbose_name_plural = "Select Validator"


@admin.register(Validator)
class ValidatorAdmin(admin.ModelAdmin):
    list_display = ("long_name", "last_stake", "default_hotkey_display")
    search_fields = ("long_name",)
    inlines = [ValidatorHotkeyInline]

    @admin.display(description="Default Hotkey")
    def default_hotkey_display(self, obj):
        default_hotkey = obj.default_hotkey
        return default_hotkey.name if default_hotkey else "N/A"


@admin.register(ExternalHotkey)
class ExternalHotkeyAdmin(admin.ModelAdmin):
    list_display = ("name", "hotkey", "subnet", "validator_display", "delegate_stake_percentage")
    search_fields = ("name", "hotkey")
    list_filter = ("subnet",)
    autocomplete_fields = ("subnet",)
    inlines = [ValidatorHotkeyInlineForExternalHotkey]

    @admin.display(description="Validator")
    def validator_display(self, obj):
        validator = obj.validator
        return validator.long_name if validator else "N/A"


@admin.register(Operator)
class OperatorAdmin(admin.ModelAdmin):
    list_display = ("name", "discord_id")
    search_fields = ("name", "discord_id")


@admin.register(Hotkey)
class HotkeyAdmin(admin.ModelAdmin):
    list_display = ("hotkey", "is_mother")
    search_fields = ("hotkey",)
