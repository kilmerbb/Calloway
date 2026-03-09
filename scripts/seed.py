"""Seed the database with test data for development."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg
from psycopg.rows import dict_row

from app.db.connection import get_connection_string


SEED_SQL = """
-- Test Agent
INSERT INTO agents (id, name, email, phone, brokerage, market, timezone, twilio_number,
    scheduling_prefs, style_profile, autonomy_rules, listing_rules, briefing_time, current_status)
VALUES (
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    'Jane Smith',
    'jane@smithrealty.com',
    '+12155551000',
    'Smith Realty Group',
    'Philadelphia, PA',
    'America/New_York',
    '+12155559999',
    '{"showing_hours": "Tue-Sat 9am-5pm", "buffer_mins": 30, "days_off": ["Sun","Mon"]}',
    '{"tone": "casual and friendly", "emoji": "occasionally"}',
    '{"level": "moderate", "escalation_topics": ["offers", "pricing", "legal", "contracts"]}',
    '{}',
    '07:30',
    'available'
) ON CONFLICT DO NOTHING;

-- Test Contacts
INSERT INTO contacts (id, agent_id, name, phone, email, role, lifecycle_stage, last_contact_at)
VALUES
    ('b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
     'Sarah Chen', '+12675551234', 'sarah@email.com', 'buyer', 'active_buyer', now() - interval '3 days'),
    ('b2eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
     'Mike Torres', '+12675552345', 'mike@email.com', 'buyer', 'active_buyer', now() - interval '1 day'),
    ('b3eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
     'The Johnsons', '+12675553456', 'johnsons@email.com', 'seller', 'active_seller', now() - interval '7 days'),
    ('b4eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
     'Lisa Park', '+12675554567', 'lisa@email.com', 'buyer', 'under_contract', now() - interval '2 days'),
    ('b5eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
     'Tom Rivera', '+12675555678', NULL, 'buyer_agent', 'other_agent', now() - interval '5 days')
ON CONFLICT DO NOTHING;

-- Lead Preferences for buyers
INSERT INTO lead_preferences (contact_id, areas, timeline, preapproved, property_type, bedrooms_min, bathrooms_min, price_min, price_max)
VALUES
    ('b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', '{"Fishtown","Northern Liberties"}', '1-3 months', true, 'townhouse', 3, 2, 400000, 500000),
    ('b2eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', '{"Fishtown","Kensington"}', '1-3 months', true, 'single_family', 3, 1, 350000, 500000)
ON CONFLICT DO NOTHING;

-- Test Listings
INSERT INTO listings (id, agent_id, address, price, beds, baths, sqft, hoa, features,
    showing_instructions, lockbox, access_rules, list_date, status)
VALUES
    ('c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
     '123 Oak St', 475000, 3, 2.0, 1800, 250,
     '["renovated kitchen", "hardwood floors", "large yard", "updated bathrooms"]',
     'Show weekdays 10am-4pm', '4521',
     '{"type": "vacant", "approval_required": false}',
     CURRENT_DATE - interval '21 days', 'active'),
    ('c2eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
     '456 Elm Ave', 460000, 3, 2.0, 1650, NULL,
     '["huge yard", "finished basement", "new roof"]',
     'Call to schedule', NULL,
     '{"type": "occupied", "notice_hours": 2, "approval_required": true, "seller_contact_id": "b3eebc99-9c0b-4ef8-bb6d-6bb9bd380a11", "special_instructions": "remove dog"}',
     CURRENT_DATE - interval '14 days', 'active'),
    ('c3eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
     '789 Front St', 465000, 3, 2.0, 1750, 200,
     '["open floor plan", "rooftop deck", "parking pad"]',
     'Lockbox on front door', '7890',
     '{"type": "vacant", "approval_required": false}',
     CURRENT_DATE - interval '7 days', 'active')
ON CONFLICT DO NOTHING;

-- Test Conversations
INSERT INTO conversations (id, agent_id, contact_id, channel, stage, last_message_at)
VALUES
    ('d1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
     'b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'rcs', 'active_search',
     now() - interval '3 days'),
    ('d2eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
     'b4eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'rcs', 'under_contract',
     now() - interval '2 days')
ON CONFLICT DO NOTHING;

-- Test Messages
INSERT INTO messages (agent_id, conversation_id, sender_type, body, intent, ai_generated, model_used, tokens_used)
VALUES
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
     'client', 'Can we see some houses this weekend?', 'scheduling', false, NULL, NULL),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
     'ai', 'Saturday looks great! Jane is free at 11am and 2pm. I found 3 properties that match your preferences. Want me to set up a tour?',
     'scheduling', true, 'sonnet', 450),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd2eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
     'client', 'When is the inspection deadline?', 'transaction', false, NULL, NULL),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd2eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
     'ai', 'Your inspection deadline for 123 Oak St is March 15th. Would you like me to remind you a few days before?',
     'transaction', true, 'haiku', 200)
ON CONFLICT DO NOTHING;

-- Test Triggers
INSERT INTO triggers (agent_id, entity_type, entity_id, trigger_type, scheduled_at, action_type, message_template, autonomy_level, status)
VALUES
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'contact', 'b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
     'follow_up', now() + interval '2 days', 'send_message',
     'Hey Sarah, any thoughts on the properties we saw?', 'auto', 'pending'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'contact', 'b4eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
     'deadline', now() + interval '5 days', 'both',
     'Inspection deadline is in 3 days', 'auto', 'pending'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'listing', 'c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
     'seller_report', now() + interval '3 days', 'compile_report',
     NULL, 'auto', 'pending'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'contact', 'b2eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
     'post_showing', now() - interval '1 hour', 'send_message',
     'How did you feel about the properties?', 'auto', 'pending'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'listing', 'c2eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
     'dom_check', now() + interval '7 days', 'notify_agent',
     NULL, 'ask_agent', 'pending')
ON CONFLICT DO NOTHING;
"""


def run_schema():
    """Run the schema SQL file against the database."""
    schema_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app", "db", "schema.sql"
    )
    with open(schema_path) as f:
        schema_sql = f.read()

    conn_str = get_connection_string()
    with psycopg.connect(conn_str, row_factory=dict_row) as conn:
        conn.execute(schema_sql)
        conn.commit()
    print("Schema created successfully.")


def run_seed():
    """Insert test data."""
    conn_str = get_connection_string()
    with psycopg.connect(conn_str, row_factory=dict_row) as conn:
        conn.execute(SEED_SQL)
        conn.commit()
    print("Seed data inserted successfully.")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "all"
    if action in ("schema", "all"):
        run_schema()
    if action in ("seed", "all"):
        run_seed()
    print("Done.")
