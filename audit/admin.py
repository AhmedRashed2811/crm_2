from django.contrib import admin
from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "entity_type", "entity_id", "actor", "request_id", "source")
    list_filter = ("action", "entity_type", "source", "created_at")
    search_fields = ("entity_id", "request_id", "action", "entity_type", "message", "actor__username", "actor__email")
    readonly_fields = [field.name for field in AuditEvent._meta.fields]

    def has_add_permission(self, request):
        return False  # only system creates these

    def has_change_permission(self, request, obj=None):
        return False  # immutable

    def has_delete_permission(self, request, obj=None):
        return False  # keep audit trail forever
