from typing import Dict, Any
from core.utils.context import RequestContext
from leads.services.leads_service import create_lead

def handle_facebook_webhook(ctx: RequestContext, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parses a simulated Facebook Lead Ad payload and creates a lead.
    """
    # 1. Parse the specific structure
    # Note: Real FB payloads usually just send an ID, requiring a callback.
    # For this mock, we assume the payload contains the data directly 
    # (Simulating a Zapier/Integration layer).
    
    lead_data = payload.get('lead_data', {})
    
    # 2. Map to our CRM fields
    crm_payload = {
        "full_name": lead_data.get('full_name', 'Unknown FB User'),
        "primary_phone": lead_data.get('phone_number'),
        "primary_email": lead_data.get('email'),
        "source": "facebook_ads",
        "campaign": lead_data.get('campaign_name', 'General FB'),
        "marketing_opt_in": True,
        "qualification": {
            "form_id": payload.get('form_id'),
            "ad_id": payload.get('ad_id')
        }
    }

    # 3. Create Lead (Triggers Scoring, Routing, Workflow)
    # We use allow_duplicates=False to prevent spam
    result = create_lead(ctx, crm_payload, allow_duplicates=False)
    
    return {
        "status": "success",
        "lead_id": result['id']
    }