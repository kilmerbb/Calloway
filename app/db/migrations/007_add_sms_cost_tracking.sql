-- Migration 007: Add SMS and voice cost tracking to usage_metrics
-- Tracks SMS segment counts, SMS costs, voice costs, and per-agent voice minute caps.

ALTER TABLE usage_metrics ADD COLUMN IF NOT EXISTS sms_segments_sent INT DEFAULT 0;
ALTER TABLE usage_metrics ADD COLUMN IF NOT EXISTS sms_segments_received INT DEFAULT 0;
ALTER TABLE usage_metrics ADD COLUMN IF NOT EXISTS sms_cost_cents INT DEFAULT 0;
ALTER TABLE usage_metrics ADD COLUMN IF NOT EXISTS voice_cost_cents INT DEFAULT 0;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS voice_daily_cap_minutes INT DEFAULT 30;
