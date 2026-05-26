"""
Backwards-compatibility shim — re-exports everything from the focused repo modules.

New code should import directly from the relevant module:
  from backend.infra.db.job_repo import create_job, get_job
  from backend.infra.db.campaign_repo import create_campaign
  ...

This file exists so existing callers (server.py, executors, etc.) don't break
while the rest of Phase 1 migration is in progress.
"""
from backend.infra.db.pool import get_pool, close_pool  # noqa: F401

from backend.infra.db.mapping_repo import (  # noqa: F401
    save_field_mapping,
    get_field_mappings,
    get_field_mapping_by_id,
    update_field_mapping,
    delete_field_mapping,
)

from backend.infra.db.job_repo import (  # noqa: F401
    create_job,
    get_job,
    get_jobs,
    get_active_job,
    update_job_status,
    delete_job,
    get_running_jobs,
    create_batches,
    get_batches,
    get_batch,
    update_batch,
    save_batch_failures,
    reset_stale_batches,
    reset_stale_pipeline_runs,
    create_warm_path_run,
    update_warm_path_run,
    get_latest_warm_path_run,
    get_warm_path_run_by_job,
    get_warm_path_runs,
    create_embedding_run,
    update_embedding_run,
    get_embedding_run_by_job,
    get_latest_embedding_run,
    create_dedup_run,
    update_dedup_run,
    get_dedup_run_by_job,
    get_latest_dedup_run,
    reset_stale_dedup_runs,
)

from backend.infra.db.campaign_repo import (  # noqa: F401
    create_campaign,
    get_campaign,
    list_campaigns,
    update_campaign_status,
    set_campaign_tier_counts,
    increment_campaign_counter,
    delete_campaign,
    save_tier_insights,
    bulk_insert_campaign_contacts,
    count_queue,
    get_queue,
    get_campaign_contact,
    get_contact_by_record,
    send_contact,
    skip_contact,
    park_contact_later,
    move_contact_tier,
    get_campaign_stats,
    sample_queue,
    get_prior_sends,
    get_campaign_template,
    get_campaign_template_by_id,
    create_campaign_template,
    update_campaign_template_by_id,
    upsert_campaign_template,
    approve_campaign_template,
    count_scope_contacts,
    create_batch_send_job,
    list_batch_send_jobs,
    get_batch_send_job,
    update_batch_send_job,
    list_all_batch_send_jobs_for_table,
    cancel_or_delete_batch_send_job,
    create_campaign_file,
    get_campaign_files,
    delete_campaign_file,
)

from backend.infra.db.embedding_repo import (  # noqa: F401
    get_rag_scores,
    get_existing_hashes,
    upsert_contact_embedding,
)

from backend.infra.db.gmail_repo import (  # noqa: F401
    upsert_gmail_token,
    get_gmail_token,
    delete_gmail_token,
)
