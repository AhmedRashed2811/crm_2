from django.contrib import admin
from .models import WorkflowDefinition, WorkflowInstance, WorkflowEvent


@admin.register(WorkflowDefinition)
class WorkflowDefinitionAdmin(admin.ModelAdmin):
    list_display = ("key", "version", "status", "name", "created_at")
    list_filter = ("key", "status")
    search_fields = ("key", "name")


@admin.register(WorkflowInstance)
class WorkflowInstanceAdmin(admin.ModelAdmin):
    list_display = ("entity_type", "entity_id", "state", "definition", "created_at", "updated_at")
    list_filter = ("state", "definition")
    search_fields = ("entity_id", "entity_type")


@admin.register(WorkflowEvent)
class WorkflowEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "instance", "action", "from_state", "to_state", "actor", "request_id")
    list_filter = ("action", "from_state", "to_state", "created_at")
    search_fields = ("request_id", "instance__entity_id")
    readonly_fields = [field.name for field in WorkflowEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
