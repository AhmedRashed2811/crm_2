from django.contrib import admin
from .models import Lead, LeadIdentityPoint, LeadTimelineEvent, LeadTask, ReasonCode


@admin.register(ReasonCode)
class ReasonCodeAdmin(admin.ModelAdmin):
    list_display = ("type", "code", "label", "is_active", "created_at", "updated_at")
    list_filter = ("type", "is_active")
    search_fields = ("code", "label")
    ordering = ("type", "code")


class LeadIdentityPointInline(admin.TabularInline):
    model = LeadIdentityPoint
    extra = 0
    readonly_fields = ("id", "created_at", "updated_at", "is_deleted", "deleted_at")
    fields = ("type", "value", "is_primary", "created_at")
    can_delete = False


class LeadTaskInline(admin.TabularInline):
    model = LeadTask
    extra = 0
    readonly_fields = ("id", "created_at", "updated_at", "completed_at")
    fields = ("title", "status", "assigned_to", "due_at", "completed_at")
    show_change_link = True


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "full_name",
        "primary_phone",
        "primary_email",
        "stage",
        "owner",
        "locked",
        "do_not_contact",
        "marketing_opt_in",
        "created_at",
        "updated_at",
    )
    list_filter = ("stage", "locked", "do_not_contact", "marketing_opt_in", "source", "medium")
    search_fields = ("full_name", "primary_phone", "primary_email", "id")
    ordering = ("-created_at",)

    readonly_fields = ("id", "created_at", "updated_at", "is_deleted", "deleted_at")
    fieldsets = (
        ("Identity", {"fields": ("id", "full_name", "primary_phone", "primary_email")}),
        ("Attribution", {"fields": ("source", "medium", "campaign", "content", "term", "utm")}),
        ("Consent", {"fields": ("marketing_opt_in", "do_not_contact")}),
        ("Ownership", {"fields": ("owner", "locked", "locked_at")}),
        ("Lifecycle", {"fields": ("stage", "score_bucket", "qualification")}),
        ("SLA", {"fields": ("first_response_due_at", "first_contact_at")}),
        ("Integrations", {"fields": ("external_refs",)}),
        ("System", {"fields": ("created_at", "updated_at", "is_deleted", "deleted_at")}),
    )

    inlines = [LeadIdentityPointInline, LeadTaskInline]


@admin.register(LeadIdentityPoint)
class LeadIdentityPointAdmin(admin.ModelAdmin):
    list_display = ("type", "value", "lead", "is_primary", "created_at", "is_deleted")
    list_filter = ("type", "is_primary", "is_deleted")
    search_fields = ("value", "lead__id", "lead__full_name")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at", "is_deleted", "deleted_at")


@admin.register(LeadTimelineEvent)
class LeadTimelineEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "lead", "type", "title", "actor")
    list_filter = ("type", "created_at")
    search_fields = ("lead__id", "lead__full_name", "title", "body")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at", "is_deleted", "deleted_at")

    def has_change_permission(self, request, obj=None):
        # timeline is append-only
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LeadTask)
class LeadTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "lead", "status", "assigned_to", "due_at", "completed_at", "created_at")
    list_filter = ("status", "due_at")
    search_fields = ("title", "lead__id", "lead__full_name")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at", "completed_at")
