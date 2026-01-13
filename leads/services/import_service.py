import pandas as pd
from typing import Dict, Any
from django.db import transaction

from core.api.exceptions import ValidationError
from core.utils.context import RequestContext
from leads.models import ImportBatch
from leads.services.leads_service import create_lead
from leads.utils.security import ensure_can_import_leads

def process_import_batch(ctx: RequestContext, batch_id: str) -> Dict[str, Any]:
    ensure_can_import_leads(ctx)

    batch = ImportBatch.objects.get(id=batch_id)
    batch.status = 'PROCESSING'
    batch.save()

    # 1. Read File into DataFrame
    try:
        if batch.file.name.endswith('.csv'):
            df = pd.read_csv(batch.file.path)
        else:
            df = pd.read_excel(batch.file.path)
            
        # Standardize empty values to None (NaN -> None)
        df = df.where(pd.notnull(df), None)
        
    except Exception as e:
        batch.status = 'FAILED'
        batch.summary = {"error": f"File read error: {str(e)}"}
        batch.save()
        return batch.summary

    # 2. Normalize Columns
    # Map common variations to your internal field names
    column_map = {
        'Mobile': 'primary_phone', 'Phone': 'primary_phone', 'Tel': 'primary_phone', 'Mobile No': 'primary_phone',
        'Name': 'full_name', 'Full Name': 'full_name', 'Client Name': 'full_name',
        'Email': 'primary_email', 'E-mail': 'primary_email',
        'Source': 'source',
        'Budget': 'budget', # Will go into qualification
        'Campaign': 'campaign'
    }
    
    # Rename columns in the dataframe
    df.rename(columns=column_map, inplace=True)

    results = {
        "total": len(df),
        "success": 0,
        "failed": 0,
        "errors": []
    }

    # 3. Iterate & Create
    for index, row in df.iterrows():
        try:
            # Construct Payload
            # We explicitly pull known fields. 
            # Unknown fields could be added to 'qualification' if you wanted more flexibility.
            
            payload = {
                "full_name": str(row.get('full_name', '') or '').strip(),
                "primary_phone": str(row.get('primary_phone', '') or '').strip(),
                "primary_email": str(row.get('primary_email', '') or '').strip(),
                "source": str(row.get('source', '') or 'import_batch').strip(),
                "campaign": str(row.get('campaign', '') or '').strip(),
                "qualification": {}
            }
            
            # Map extra data to qualification
            if row.get('budget'):
                payload['qualification']['budget'] = str(row['budget'])

            # Skip empty rows
            if not payload['primary_phone'] and not payload['primary_email']:
                continue

            # CALL CORE SERVICE
            # This triggers: Validation -> Creation -> Scoring -> Routing -> Workflow -> Audit
            create_lead(ctx, payload, allow_duplicates=False)
            
            results["success"] += 1

        except ValidationError as e:
            results["failed"] += 1
            # Store readable error
            msg = e.message if hasattr(e, 'message') else str(e)
            if hasattr(e, 'details') and e.details:
                msg += f" {str(e.details)}"
            
            results["errors"].append({
                "row": index + 2, # +2 matches Excel Row Number (Header is 1)
                "name": row.get('full_name', 'Unknown'),
                "error": msg
            })
            
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "row": index + 2,
                "error": f"System Error: {str(e)}"
            })

    # 4. Finalize Batch
    batch.summary = results
    if results["failed"] == 0:
        batch.status = 'COMPLETED'
    elif results["success"] == 0:
        batch.status = 'FAILED'
    else:
        batch.status = 'PARTIAL_FAILURE'
        
    batch.save()
    
    return results