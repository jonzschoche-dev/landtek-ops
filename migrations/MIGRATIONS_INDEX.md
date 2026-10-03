# Migrations / Deploy SQL Index

*Rebuilt 2026-09-26 06:56 PhST by `scripts/rebuild_migrations_index.py` from `migrations/deploy_*.sql`.*

This is the **authoritative file census** of SQL deploys in the tree.
`DEPLOY_LOG.md` / `DEPLOY_LOG.csv` are the older cowork/workflow event log (May 2026 era) and
**do not** list schema deploys past the low 100s — do not treat them as the SQL inventory.

**Count:** 69 `deploy_*.sql` files · numbered: 63 · unnumbered: 6

| # | File | Header (first comment) |
|---|---|---|
| 642 | `deploy_642_deadline_coverage_proof_clients.sql` | deploy_NN: deadline / verified-date coverage on the two PROOF clients (MWK-001, Paracale-001) |
| 644 | `deploy_644_arta_cluster_deadlines.sql` | deploy_NN: ARTA-cluster deadline-coverage hardening on MWK-001 |
| 645 | `deploy_645_mwk_remaining_deadlines.sql` | deploy_645: MWK-001 remaining-deadline coverage hardening (guardianship grounded; OP/CV6839/LGU honestly blank) |
| 647 | `deploy_647_cv26360_aug12_grounding.sql` | deploy_647_cv26360_aug12_grounding.sql  (STAGED — do NOT auto-apply; hand-reviewed by operator) |
| 654 | `deploy_654_email_channel_activate.sql` | deploy_654: activate the email channel (INBOUND live; OUTBOUND send HELD) |
| 658 | `deploy_658_arta1378_label_fix.sql` | deploy_655_arta1378_label_fix.sql |
| 659 | `deploy_659_client_access_tokens.sql` | deploy_NN: client_access_tokens — the external, per-client entry credential. |
| 659 | `deploy_659_ombudsman_hunter.sql` | deploy_NN_ombudsman_hunter.sql |
| 662 | `deploy_662_whatsapp_channel_ready.sql` | deploy_662: mark the WhatsApp channel READY (code wired, awaiting token) — no external exposure yet. |
| 683 | `deploy_683_map_parcels.sql` | deploy_683: map_parcels — the geometry spine of the client-facing Mapping subsystem. |
| 684 | `deploy_684_hunter_trgm_indexes.sql` | Trigram GIN indexes so the Ombudsman Hunter combs the corpus fast at scale (pg_trgm already installed). |
| 687 | `deploy_687_geometry_priority.sql` | deploy_687: geometry_priority — the drip queue for stripping plot geometry from the corpus. |
| 699 | `deploy_699_constitution_regen_log.sql` | deploy_699_constitution_regen_log.sql |
| 703 | `deploy_703_work_orders.sql` | deploy_703_work_orders.sql — Supervisor v1 Phase 1 foundation. |
| 707 | `deploy_707_work_orders_grounding.sql` | deploy_707_work_orders_grounding.sql — Supervisor grounding + cancel. |
| 709 | `deploy_709_v_evidence_gaps.sql` | deploy_709_v_evidence_gaps.sql — gaps become a DERIVED query, not an asserted value. |
| 710 | `deploy_710_metadata_connect.sql` | deploy_710_metadata_connect.sql — connect the corpus (Step 2, done from RELIABLE existing data). |
| 711 | `deploy_711_validator_enforce.sql` | deploy_711_validator_enforce.sql — flip ontology_validator from SHADOW to ENFORCE. |
| 712 | `deploy_712_work_order_target.sql` | deploy_712_work_order_target.sql — a work order can point at a specific target (e.g. a document). |
| 716 | `deploy_716_v4_client_isolation_enforce.sql` | deploy_716_v4_client_isolation_enforce.sql — A5 client-isolation, ENFORCED (V4 shadow→block). |
| 717 | `deploy_717_outward_guard.sql` | deploy_717: outward-action guard — SHADOW-mode observation + a GOVERNED classifier. |
| 733 | `deploy_733_parcels_client_code.sql` | deploy_733: parcels.client_code — resolve decision 7.1 (operator: "add parcels.client_code"). |
| 750 | `deploy_750_ombudsman_client_isolation.sql` | deploy_750_ombudsman_client_isolation.sql |
| 766 | `deploy_766_incorporation_status.sql` | deploy_766_incorporation_status.sql — Phase 3: governed visibility into data-incorporation status. |
| 808 | `deploy_808_composition_layer.sql` | deploy_808_composition_layer.sql — COMPOSITION LAYER, shadow install. |
| 810 | `deploy_810_agent_registry.sql` | deploy_810: agent_registry — the A61 tier registry + Supervisor Phase-2 work-routing map. |
| 810 | `deploy_810_docket_aliases.sql` | deploy_810_docket_aliases.sql — operator-curated docket ALIASES for the ingest significance engine. |
| 811 | `deploy_811_thread_continuity_view.sql` | deploy_811_thread_continuity_view.sql — v_thread_continuity (COMPOSITION_MODEL_DRAFT §2.3, approved). |
| 813 | `deploy_813_title_registry_leads.sql` | deploy_813_title_registry_leads.sql — add the reenrich-surfaced high-value titles to the registry, |
| 814 | `deploy_814_v6_geometry_isolation_shadow.sql` | deploy_814 — V6 geometry client isolation (ONTOLOGY.md A9) · SHADOW (log) — RECORD OF REALITY. |
| 818 | `deploy_818_parcel_course_consensus.sql` | deploy_818: course-level consensus for parcel geometry (the anti-single-source layer). |
| 822 | `deploy_822_corrections_lot.sql` | deploy_822: lot-scope operator corrections. With lot clustering (one consensus ring per |
| 823 | `deploy_823_comms_interaction_spine.sql` | deploy_823: comms interaction spine — READ-ONLY VIEWS (greenlit: views-first, 6.2). |
| 824 | `deploy_824_channel_users_entity_id.sql` | deploy_824: channel_users.entity_id — the cross-channel person-key (greenlit: add now, 6.1). |
| 825 | `deploy_825_title_registry_leads.sql` | deploy_825_title_registry_leads.sql — add the reenrich unknown_titles LEADS to the titles registry, |
| 826 | `deploy_826_exhibit_spine_proposals.sql` | deploy_826_exhibit_spine_proposals.sql — staging table for Exhibit-Spine Suggestions v2. |
| 828 | `deploy_828_messenger_channel_ready.sql` | deploy_828: register the Messenger channel READY (adapter live, awaiting token) — no external exposure. |
| 829 | `deploy_829_course_proposals.sql` | deploy_829: parcel_course_proposals — the CLIENT-side entry to the geometry correction |
| 830 | `deploy_830_reocr_reground_guard.sql` | deploy_830: root-cause guard for the deploy-gate breach of 2026-07-09 (8 ungrounded verified facts). |
| 870 | `deploy_870_ingestion_truth_gates.sql` | deploy_870: A77/A78 ingestion-truth substrate — the DB-side pieces of the writer-lane gates. |
| 871 | `deploy_871_v11_null_owner_shadow.sql` | deploy_871 — V11: null-owner edge guard (A77(1)) · SHADOW (log). Idempotent. |
| 879 | `deploy_879_comms_role_policy.sql` | deploy_879: A79 role axis — comms_role_policy (the single policy the gate reads to clamp every |
| 881 | `deploy_881_propagation_log.sql` | deploy_881: A76 P2 — propagation_log, the SHADOW ledger for reactive ego-network recompute. |
| 891 | `deploy_891_chat_graph_nodes.sql` | deploy_888: chat-as-graph-node — every inbound chat becomes a first-class, matter-anchored node so the |
| 895 | `deploy_895_internal_targets_channels.sql` | deploy_895: make the operator reachable on Messenger (and unblock all channels in internal_targets). |
| 896 | `deploy_896_leo_inbound_notify.sql` | deploy_896: instant-reply signal — a trigger that pg_notify's on every new INBOUND channel_message so |
| 911 | `deploy_911_property_development_spine.sql` | deploy_911: Property Development + Revenue precondition spine (reconciled design). |
| 912 | `deploy_912_v12_property_spine_isolation_shadow.sql` | deploy_912 — V12: Property Development spine isolation (ONTOLOGY A81) · SHADOW (log). |
| 914 | `deploy_914_profitability_prep_cycle.sql` | deploy_914: Continuous profitability preparation cycle (doctrine). |
| 915 | `deploy_915_property_readiness_axes.sql` | deploy_915: Property readiness axes — what "prepare a property" means. |
| 934 | `deploy_934_equilibrium_spine.sql` | deploy_934: Reasoning-equilibrium spine (finally the durable tables) |
| 935 | `deploy_935_title_brief.sql` | deploy_935: title_brief — one digested row per title for property UI (later maps + classification) |
| 936 | `deploy_936_clarity_oversight.sql` | deploy_936: clarity + human-oversight flags on derived cards |
| 937 | `deploy_937_document_fields.sql` | deploy_937: document_fields — every doc's typed extractions (the bulk intake table) |
| 938 | `deploy_938_inquiry_agentic_stack.sql` | deploy_938: Agentic inquiry stack |
| 939 | `deploy_939_agent_stack_sim.sql` | deploy_939: Agent-stack simulator (grounded, mechanical) |
| 939 | `deploy_939_read_composer.sql` | deploy_939_read_composer.sql — Read Composer P0 substrate (docs/READ_CONSENSUS_DIRECTIVE.md §3/§4) |
| 940 | `deploy_940_register_fleet_mandates.sql` | deploy_940: register two fleet agents in agent_mandates (deploy_938 registry) |
| 947 | `deploy_947_plan_overlays.sql` | deploy_947: plan_overlays — georeferenced raster overlays of survey/cadastral plan images. |
| 973 | `deploy_973_mf_writer_key.sql` | deploy_973: idempotent fact-writer key (kills the matter_facts id churn) |
| 978 | `deploy_978_portfolio_publish.sql` | deploy_978_portfolio_publish.sql — Client portfolio publish set (curated storefront) |
| 979 | `deploy_979_client_money_chat.sql` | deploy_979_client_money_chat.sql — Client app Money + Chat substrate |
| 980 | `deploy_980_cos_awareness_bridge.sql` | deploy_980: CoS↔VPS awareness bridge — extend agent_registry.layer for Grok Bot + Claude seats. |
| — | `deploy_comms_artifacts_ledger.sql` | Universal comms-artifact intake ledger — makes "lossless intake" mechanically provable (T3). |
| — | `deploy_convergence_diff.sql` | deploy: convergence shadow-diff ledger. leo_instant runs the LIVE path (leo_service.process) and the |
| — | `deploy_leo_channel_mode.sql` | Per-channel cutover switch (the rollback flag) + link the shadow ledger to its approval order. |
| — | `deploy_leo_shadow_replies.sql` | leo_service shadow ledger — the headless Leo brain runs the full spine but SENDS NOTHING; |
| — | `deploy_relationship_graph.sql` | A76 P1 — the unified relationship graph, VIEW-ONLY. |
| — | `deploy_relationship_profile.sql` | deploy: the first LIVING ORGAN — relationship_profile. Per verified comms line, an evolving record of |

## Companion Python appliers (`apply_deploy_*.py`)

| File |
|---|
| `apply_deploy_032.py` |
| `apply_deploy_033.py` |
| `apply_deploy_034.py` |
| `apply_deploy_034b.py` |
| `apply_deploy_035.py` |
| `apply_deploy_036.py` |
| `apply_deploy_037.py` |
| `apply_deploy_038.py` |
| `apply_deploy_039.py` |
| `apply_deploy_040.py` |
| `apply_deploy_041.py` |
| `apply_deploy_042.py` |
| `apply_deploy_043.py` |
| `apply_deploy_044.py` |
| `apply_deploy_055.py` |
| `apply_deploy_055b.py` |
| `apply_deploy_056.py` |
| `apply_deploy_057.py` |
| `apply_deploy_057b.py` |
| `apply_deploy_057c.py` |
| `apply_deploy_057e.py` |
| `apply_deploy_058.py` |
| `apply_deploy_059.py` |
| `apply_deploy_060.py` |
| `apply_deploy_061.py` |
| `apply_deploy_062.py` |
| `apply_deploy_063.py` |
| `apply_deploy_064.py` |
| `apply_deploy_074.py` |
| `apply_deploy_075.py` |
| `apply_deploy_076.py` |
| `apply_deploy_077.py` |
| `apply_deploy_078.py` |
| `apply_deploy_079.py` |
| `apply_deploy_080.py` |
| `apply_deploy_081.py` |
| `apply_deploy_082.py` |
| `apply_deploy_087.py` |
| `apply_deploy_088.py` |
| `apply_deploy_089.py` |
| `apply_deploy_091.py` |
| `apply_deploy_092.py` |
| `apply_deploy_094.py` |
| `apply_deploy_102.py` |
| `apply_deploy_104.py` |
| `apply_deploy_105.py` |
| `apply_deploy_108.py` |
| `apply_deploy_109_extend_slashes.py` |
| `apply_deploy_111_schema.py` |
| `apply_deploy_113_schema.py` |
| `apply_deploy_113b_risk_schema.py` |
| `apply_deploy_114_channels_schema.py` |
| `apply_deploy_115_title_linkage.py` |
| `apply_deploy_116_onboarding_schema.py` |
| `apply_deploy_116b_slashes.py` |
| `apply_deploy_116c_workflow_wiring.py` |
| `apply_deploy_117_api_keys.py` |
| `apply_deploy_117b_finance_slashes.py` |
| `apply_deploy_118_filenames.py` |
| `apply_deploy_118b_slashes.py` |
| `apply_deploy_119_arta_chart.py` |
| `apply_deploy_119_party_schema.py` |
| `apply_deploy_120_analyzer_schema.py` |
| `apply_deploy_121_cost_logging.py` |
| `apply_deploy_122_drive_dedup.py` |
| `apply_deploy_123_stage_intake.py` |
| `apply_deploy_124_tg_inquiry_queue.py` |
| `apply_deploy_125_normalize_doc_date.py` |
| `apply_deploy_205_tn_calibration.py` |
| `apply_deploy_206_tn_entity_alias.py` |
| `apply_deploy_207_holes_schema.py` |
| `apply_deploy_212_subdivision_plans.py` |
| `apply_deploy_219_title_chain_plan_link.py` |
| `apply_deploy_220_plan_backfill_from_source_docs.py` |
| `apply_deploy_221A_fix_null_override.py` |
| `apply_deploy_221A_truth_lockdown_foundation.py` |
| `apply_deploy_221B_proposed_changes.py` |
| `apply_deploy_221D_compound_claim_drift.py` |
| `apply_deploy_226_gmail_matter_linkage.py` |
| `apply_deploy_227_arta_cases_enrichment.py` |
| `apply_deploy_229_resolutions_table.py` |
| `apply_deploy_231_heuristic_doc_classification.py` |
| `apply_deploy_232_resolution_disposition_refinement.py` |
| `apply_deploy_234_documents_matter_backfill.py` |
| `apply_deploy_235_escalations_table.py` |
| `apply_deploy_236_documents_doc_date_backfill.py` |
| `apply_deploy_238_accuracy_pass.py` |
| `apply_deploy_243_resolution_matter_backfill.py` |
| `apply_deploy_244_doc_classification.py` |
| `apply_deploy_245_adjudicator_identification.py` |
| `apply_deploy_246_truth_tests_nightly.py` |
| `apply_deploy_247_audit_trigger_fix.py` |
| `apply_deploy_247_content_hash_backfill.py` |
| `apply_deploy_247_lock_ceremony.py` |
| `apply_deploy_250_apply_high_conf_proposals.py` |
| `apply_deploy_251_torralba_balane_linkage.py` |
| `apply_deploy_252_entity_graph_guard.py` |
| `apply_deploy_253_text_level_guard.py` |
| `apply_deploy_254_close_audit_gaps.py` |
| `apply_deploy_255_donata_king_case_file_audit.py` |
| `apply_deploy_256_case_file_domain_cleanup.py` |
| `apply_deploy_257_owner_mwk_crosslinks.py` |
| `apply_deploy_258_inocalla_martial_arts.py` |
| `apply_deploy_259_mwk_doc_date_backfill.py` |
| `apply_deploy_260_mwk_matter_assignment.py` |
| `apply_deploy_261_gmail_matter_backfill_v2.py` |
| `apply_deploy_262_phase_222_lock_ceremony.py` |
| `apply_deploy_263_safe_reply_optimized.py` |
| `apply_deploy_264_active_landscape.py` |
| `apply_deploy_265_nightly_wrapper_install.py` |
| `apply_deploy_265_telegram_reliability.py` |
| `apply_deploy_266_bulletproof_tier1.py` |
| `apply_deploy_268_no_empty_promises.py` |
| `apply_deploy_269_webhook_watchdog_install.py` |
| `apply_deploy_270_drive_links_in_replies.py` |
| `apply_deploy_271_empty_promise_guard.py` |
| `apply_deploy_272_drive_proxy.py` |
| `apply_deploy_275_singson_meeting.py` |
| `apply_deploy_276_agentic_calendar.py` |
| `apply_deploy_277_email_awareness.py` |
| `apply_deploy_278_deadline_extraction.py` |
| `apply_deploy_279_document_matter_links.py` |
| `apply_deploy_280_triage_flow.py` |
| `apply_deploy_294_multichannel_onboarding.py` |
| `apply_deploy_298_leo_qa_loop.py` |
| `apply_deploy_298b_qa_probe_library.py` |
| `apply_deploy_298c_simulator.py` |
| `apply_deploy_299_opus_probe_generator.py` |
| `apply_deploy_300_sim_send_gate.py` |
| `apply_deploy_305_improvement_loop.py` |
| `apply_deploy_306_sim_awareness.py` |
| `apply_deploy_307_mandate_invariant_probes.py` |
| `apply_deploy_308_sim_auth_elevation.py` |
| `apply_deploy_308b_context_builder_elevation.py` |
| `apply_deploy_309_autonomous_loop.py` |
| `apply_deploy_311_sentinel_sim_aware_and_privacy.py` |
| `apply_deploy_312_title_chain_context.py` |
| `apply_deploy_313_sim_monitor.py` |
| `apply_deploy_314_security_first_monitor.py` |
| `apply_deploy_315_smartness_loop_hardening.py` |
| `apply_deploy_316_regression_gate.py` |
| `apply_deploy_317_evidence_trail.py` |
| `apply_deploy_318_filing_discipline.py` |
| `apply_deploy_320_evidence_population.py` |
| `apply_deploy_321_intent_tagging.py` |
| `apply_deploy_322_rule_s8.py` |
| `apply_deploy_323_bonafide_rebalance.py` |
| `apply_deploy_324_opus_doc_role_classifier.py` |
| `apply_deploy_325_companion.py` |
| `apply_deploy_325_realtime_preparation.py` |
| `apply_deploy_326_companion.py` |
| `apply_deploy_326_obligations_phases_needs.py` |
| `apply_deploy_327_perpetual.py` |
| `apply_deploy_328_substance.py` |
| `apply_deploy_329_strict_rails.py` |
| `apply_deploy_330_rule_s13.py` |
| `apply_deploy_332_objectives.py` |
| `apply_deploy_333_layer1_complete.py` |
| `apply_deploy_334_canonical_client_history.py` |
| `apply_deploy_336_sim_pause.py` |
| `apply_deploy_337_lean_simulator.py` |
| `apply_deploy_341_ontology_hardening.py` |
| `apply_deploy_342_correspondence_spine.py` |
| `apply_deploy_343_mwk_priority_queue.py` |
| `apply_deploy_345_mediation_capture_fraud_reframe.py` |
| `apply_deploy_346_ida_spa_revocation_primary.py` |
| `apply_deploy_347_hard_facts_discipline.py` |
| `apply_deploy_348_arta_op_spine.py` |
| `apply_deploy_349_strip_unverified_blockers.py` |
| `apply_deploy_350_dual_arta_manifestations.py` |
| `apply_deploy_351_email_clues_arta_manifestations.py` |
| `apply_deploy_352_email_log_search.py` |
| `apply_deploy_353_archived_email_canonical_history.py` |
| `apply_deploy_354_legal_event_email_policy.py` |
| `apply_deploy_355_arta_autolink_fix.py` |
| `apply_deploy_356_dilg_not_cv26360.py` |
| `apply_deploy_357_rapid_fire_simulator.py` |
| `apply_deploy_358_simulator_improvement_loop.py` |
| `apply_deploy_360_arch_sim_context.py` |
| `apply_deploy_361_vault_schema.py` |
| `apply_deploy_362_vault_tools.py` |
| `apply_deploy_363_rule_m_fluid.py` |
| `apply_deploy_364_ops_dashboard.py` |
| `apply_deploy_364_sim_guard_syntax_fix.py` |
| `apply_deploy_365_db_group_focus.py` |
| `apply_deploy_366_strip_vault_connections.py` |
| `apply_deploy_367_silence_empty.py` |
| `apply_deploy_368_kb_pollution_eradication.py` |
| `apply_deploy_368_never_ghost.py` |
| `apply_deploy_369_need_only_email_onboard.py` |
| `apply_deploy_369_telegram_inbox.py` |
| `apply_deploy_649_calendar_sync_timer.py` |
| `apply_deploy_656_assistant_cadence_timer.py` |
| `apply_deploy_691_ontology_validator.py` |
| `apply_deploy_743_ontology_validator_v7.py` |
| `apply_deploy_769_ontology_validator_v8.py` |
| `apply_deploy_837_assistant_inbound.py` |
| `apply_deploy_839_pulse_orchestrator_timer.py` |
| `apply_deploy_841_date_proposer_timer.py` |

## Gaps / notes
- Numbered series is **not contiguous** (legacy skips are normal).
- Highest numbered SQL in tree: **980**.
- Apply on VPS via the usual psql/docker path; Mac may lack PG reachability.
- After adding a `deploy_NNNN_*.sql`, re-run: `python3 scripts/rebuild_migrations_index.py`

