from django.urls import path
from .views import (
    LeadDuplicatesAPI,
    LeadListCreateAPI,
    LeadDetailAPI,
    LeadAssignCommandAPI,
    LeadChangeStageCommandAPI,
    LeadAddTimelineEventCommandAPI,
    LeadMergeCommandAPI,
    ReasonCodeListAPI,
    LeadTimelineAPI, 
    LeadWorkflowAPI, 
    LeadTasksAPI
)

urlpatterns = [
    path("v1/leads/", LeadListCreateAPI.as_view(), name="leads_list_create"),
    path("v1/leads/<uuid:lead_id>/", LeadDetailAPI.as_view(), name="leads_detail"),

    # Commands
    path("v1/leads/<uuid:lead_id>/commands/assign/", LeadAssignCommandAPI.as_view(), name="lead_assign"),
    path("v1/leads/<uuid:lead_id>/commands/change-stage/", LeadChangeStageCommandAPI.as_view(), name="lead_change_stage"),
    path("v1/leads/<uuid:lead_id>/commands/add-timeline-event/", LeadAddTimelineEventCommandAPI.as_view(), name="lead_add_timeline_event"),
    
    path("v1/reason-codes/", ReasonCodeListAPI.as_view(), name="reason_codes_list"),
    
    
    path("v1/leads/<uuid:lead_id>/timeline/", LeadTimelineAPI.as_view(), name="lead_timeline"),
    path("v1/leads/<uuid:lead_id>/workflow/", LeadWorkflowAPI.as_view(), name="lead_workflow"),
    path("v1/leads/<uuid:lead_id>/tasks/", LeadTasksAPI.as_view(), name="lead_tasks"),

    path("v1/leads/<uuid:lead_id>/duplicates/", LeadDuplicatesAPI.as_view(), name="lead_duplicates"),
    path("v1/leads/<uuid:lead_id>/commands/merge/", LeadMergeCommandAPI.as_view(), name="lead_merge"),

]
