-- Initialize default GDPR data retention policies
-- Run this after database migrations to set up baseline compliance policies
--
-- These policies align with common regulatory requirements:
-- - GDPR (General Data Protection Regulation)
-- - HIPAA (Health Insurance Portability and Accountability Act)
-- - PCI-DSS (Payment Card Industry Data Security Standard)
-- - SOX (Sarbanes-Oxley Act)
--
-- Adjust retention periods based on your jurisdiction and business needs

-- ============================================================================
-- Audit Log Retention Policies
-- ============================================================================

-- Authentication Events (Login, Logout, Token Refresh)
INSERT INTO data_retention_policies (
  id,
  policy_name,
  data_type,
  description,
  retention_period_days,
  retention_basis,
  auto_delete_enabled,
  delete_method,
  legal_hold_exempt,
  minimum_retention_days,
  regulations,
  is_active,
  archive_after_days,
  approved_by,
  approved_at,
  next_review_date
) VALUES (
  gen_random_uuid()::text,
  'Audit Logs - Authentication Events',
  'audit_logs_auth',
  'Retain authentication events (login, logout, token operations) for 90 days for security monitoring and fraud detection.',
  90,
  'security_requirement',
  true,
  'hard_delete',
  false,
  30,
  '["GDPR", "PCI-DSS"]'::json,
  true,
  null,
  'System Administrator',
  NOW(),
  NOW() + INTERVAL '1 year'
) ON CONFLICT (policy_name) DO NOTHING;

-- Data Modification Events (Create, Update, Delete)
INSERT INTO data_retention_policies (
  id,
  policy_name,
  data_type,
  description,
  retention_period_days,
  retention_basis,
  auto_delete_enabled,
  delete_method,
  legal_hold_exempt,
  minimum_retention_days,
  regulations,
  is_active,
  archive_after_days,
  approved_by,
  approved_at,
  next_review_date
) VALUES (
  gen_random_uuid()::text,
  'Audit Logs - Data Modification',
  'audit_logs_data_modify',
  'Retain data modification audit logs for 7 years to comply with HIPAA and healthcare data protection requirements.',
  2555,  -- 7 years
  'legal_requirement',
  true,
  'hard_delete',
  false,
  2555,
  '["GDPR", "HIPAA", "SOX"]'::json,
  true,
  1825,  -- Archive after 5 years
  'Data Protection Officer',
  NOW(),
  NOW() + INTERVAL '1 year'
) ON CONFLICT (policy_name) DO NOTHING;

-- Security Events (Failed logins, suspicious activity, breaches)
INSERT INTO data_retention_policies (
  id,
  policy_name,
  data_type,
  description,
  retention_period_days,
  retention_basis,
  auto_delete_enabled,
  delete_method,
  legal_hold_exempt,
  minimum_retention_days,
  regulations,
  is_active,
  archive_after_days,
  approved_by,
  approved_at,
  next_review_date
) VALUES (
  gen_random_uuid()::text,
  'Audit Logs - Security Events',
  'audit_logs_security',
  'Retain security events for 2 years for incident investigation and compliance audits.',
  730,  -- 2 years
  'security_requirement',
  true,
  'hard_delete',
  false,
  365,
  '["GDPR", "PCI-DSS", "SOC2"]'::json,
  true,
  365,  -- Archive after 1 year
  'Chief Security Officer',
  NOW(),
  NOW() + INTERVAL '1 year'
) ON CONFLICT (policy_name) DO NOTHING;

-- General Audit Logs (All other events)
INSERT INTO data_retention_policies (
  id,
  policy_name,
  data_type,
  description,
  retention_period_days,
  retention_basis,
  auto_delete_enabled,
  delete_method,
  legal_hold_exempt,
  minimum_retention_days,
  regulations,
  is_active,
  archive_after_days,
  approved_by,
  approved_at,
  next_review_date
) VALUES (
  gen_random_uuid()::text,
  'Audit Logs - General',
  'audit_logs',
  'Retain general audit logs for 1 year for compliance and operational purposes.',
  365,
  'business_need',
  true,
  'hard_delete',
  false,
  90,
  '["GDPR", "SOC2"]'::json,
  true,
  null,
  'System Administrator',
  NOW(),
  NOW() + INTERVAL '1 year'
) ON CONFLICT (policy_name) DO NOTHING;

-- ============================================================================
-- User Data Retention Policies
-- ============================================================================

-- API Execution History
INSERT INTO data_retention_policies (
  id,
  policy_name,
  data_type,
  description,
  retention_period_days,
  retention_basis,
  auto_delete_enabled,
  delete_method,
  legal_hold_exempt,
  minimum_retention_days,
  regulations,
  is_active,
  archive_after_days,
  approved_by,
  approved_at,
  next_review_date
) VALUES (
  gen_random_uuid()::text,
  'API Execution History',
  'executions',
  'Retain API execution history for 1 year for troubleshooting and usage analysis.',
  365,
  'business_need',
  true,
  'hard_delete',
  true,
  90,
  '["GDPR"]'::json,
  true,
  180,  -- Archive after 6 months
  'Engineering Lead',
  NOW(),
  NOW() + INTERVAL '1 year'
) ON CONFLICT (policy_name) DO NOTHING;

-- User Projects and Artifacts
INSERT INTO data_retention_policies (
  id,
  policy_name,
  data_type,
  description,
  retention_period_days,
  retention_basis,
  auto_delete_enabled,
  delete_method,
  legal_hold_exempt,
  minimum_retention_days,
  regulations,
  is_active,
  archive_after_days,
  approved_by,
  approved_at,
  next_review_date
) VALUES (
  gen_random_uuid()::text,
  'User Projects and Artifacts',
  'user_data',
  'User projects and artifacts are retained indefinitely until user requests deletion or account is closed. Inactive accounts (no login for 2 years) will be notified before archival.',
  null,  -- Indefinite retention
  'service_provision',
  false,  -- Manual review required
  'soft_delete',
  true,
  null,
  '["GDPR"]'::json,
  true,
  730,  -- Archive inactive accounts after 2 years
  'Product Manager',
  NOW(),
  NOW() + INTERVAL '1 year'
) ON CONFLICT (policy_name) DO NOTHING;

-- ============================================================================
-- GDPR-Specific Data Retention
-- ============================================================================

-- Cookie Consents
INSERT INTO data_retention_policies (
  id,
  policy_name,
  data_type,
  description,
  retention_period_days,
  retention_basis,
  auto_delete_enabled,
  delete_method,
  legal_hold_exempt,
  minimum_retention_days,
  regulations,
  is_active,
  archive_after_days,
  approved_by,
  approved_at,
  next_review_date
) VALUES (
  gen_random_uuid()::text,
  'Cookie Consents',
  'cookie_consents',
  'Delete cookie consents immediately upon expiration (typically 12 months from grant date).',
  null,  -- Deleted based on expires_at field
  'legal_requirement',
  true,
  'hard_delete',
  false,
  null,
  '["GDPR", "ePrivacy"]'::json,
  true,
  null,
  'Data Protection Officer',
  NOW(),
  NOW() + INTERVAL '1 year'
) ON CONFLICT (policy_name) DO NOTHING;

-- Data Subject Access Requests (DSAR)
INSERT INTO data_retention_policies (
  id,
  policy_name,
  data_type,
  description,
  retention_period_days,
  retention_basis,
  auto_delete_enabled,
  delete_method,
  legal_hold_exempt,
  minimum_retention_days,
  regulations,
  is_active,
  archive_after_days,
  approved_by,
  approved_at,
  next_review_date
) VALUES (
  gen_random_uuid()::text,
  'Data Subject Access Requests',
  'data_requests',
  'Retain completed DSAR records for 3 years for compliance verification and dispute resolution.',
  1095,  -- 3 years
  'legal_requirement',
  true,
  'soft_delete',
  false,
  1095,
  '["GDPR"]'::json,
  true,
  null,
  'Data Protection Officer',
  NOW(),
  NOW() + INTERVAL '1 year'
) ON CONFLICT (policy_name) DO NOTHING;

-- Consent Records
INSERT INTO data_retention_policies (
  id,
  policy_name,
  data_type,
  description,
  retention_period_days,
  retention_basis,
  auto_delete_enabled,
  delete_method,
  legal_hold_exempt,
  minimum_retention_days,
  regulations,
  is_active,
  archive_after_days,
  approved_by,
  approved_at,
  next_review_date
) VALUES (
  gen_random_uuid()::text,
  'Consent Records',
  'consent_records',
  'Retain consent records for 3 years after withdrawal to demonstrate compliance with consent requirements.',
  1095,  -- 3 years after withdrawal
  'legal_requirement',
  false,  -- Manual review (need to calculate from withdrawn_at)
  'soft_delete',
  false,
  1095,
  '["GDPR"]'::json,
  true,
  null,
  'Data Protection Officer',
  NOW(),
  NOW() + INTERVAL '1 year'
) ON CONFLICT (policy_name) DO NOTHING;

-- Data Breach Incidents
INSERT INTO data_retention_policies (
  id,
  policy_name,
  data_type,
  description,
  retention_period_days,
  retention_basis,
  auto_delete_enabled,
  delete_method,
  legal_hold_exempt,
  minimum_retention_days,
  regulations,
  is_active,
  archive_after_days,
  approved_by,
  approved_at,
  next_review_date
) VALUES (
  gen_random_uuid()::text,
  'Data Breach Incidents',
  'data_breach_incidents',
  'Retain data breach incident records for 5 years for regulatory compliance and incident response improvement.',
  1825,  -- 5 years
  'legal_requirement',
  false,  -- Never auto-delete breach records
  'soft_delete',
  false,
  1825,
  '["GDPR", "HIPAA", "PCI-DSS"]'::json,
  true,
  null,
  'Chief Security Officer',
  NOW(),
  NOW() + INTERVAL '1 year'
) ON CONFLICT (policy_name) DO NOTHING;

-- ============================================================================
-- Session and Temporary Data
-- ============================================================================

-- Redis Session Data (handled by TTL in Redis, but documented here)
INSERT INTO data_retention_policies (
  id,
  policy_name,
  data_type,
  description,
  retention_period_days,
  retention_basis,
  auto_delete_enabled,
  delete_method,
  legal_hold_exempt,
  minimum_retention_days,
  regulations,
  is_active,
  archive_after_days,
  approved_by,
  approved_at,
  next_review_date
) VALUES (
  gen_random_uuid()::text,
  'Session Data',
  'sessions',
  'Session data expires automatically via Redis TTL: 15 min (short), 1 hour (default), 8 hours (long), 24 hours (workflow).',
  1,  -- 1 day max
  'business_need',
  true,
  'hard_delete',
  true,
  null,
  '["GDPR"]'::json,
  true,
  null,
  'System Administrator',
  NOW(),
  NOW() + INTERVAL '1 year'
) ON CONFLICT (policy_name) DO NOTHING;

-- DSAR Export Files
INSERT INTO data_retention_policies (
  id,
  policy_name,
  data_type,
  description,
  retention_period_days,
  retention_basis,
  auto_delete_enabled,
  delete_method,
  legal_hold_exempt,
  minimum_retention_days,
  regulations,
  is_active,
  archive_after_days,
  approved_by,
  approved_at,
  next_review_date
) VALUES (
  gen_random_uuid()::text,
  'DSAR Export Files',
  'dsar_exports',
  'Delete export files 30 days after generation. Users should download within this period.',
  30,
  'data_minimization',
  true,
  'hard_delete',
  true,
  30,
  '["GDPR"]'::json,
  true,
  null,
  'Data Protection Officer',
  NOW(),
  NOW() + INTERVAL '1 year'
) ON CONFLICT (policy_name) DO NOTHING;

-- ============================================================================
-- Summary Report
-- ============================================================================

-- Display all policies
SELECT
  policy_name,
  data_type,
  retention_period_days,
  CASE
    WHEN retention_period_days IS NULL THEN 'Indefinite'
    WHEN retention_period_days >= 365 THEN (retention_period_days / 365)::text || ' years'
    ELSE retention_period_days::text || ' days'
  END as retention_period,
  retention_basis,
  auto_delete_enabled,
  delete_method,
  regulations,
  is_active
FROM data_retention_policies
ORDER BY data_type, retention_period_days NULLS LAST;

-- Policy count by regulation
SELECT
  regulation,
  COUNT(*) as policy_count
FROM (
  SELECT jsonb_array_elements_text(regulations::jsonb) as regulation
  FROM data_retention_policies
  WHERE is_active = true
) reg_policies
GROUP BY regulation
ORDER BY policy_count DESC;

COMMIT;
