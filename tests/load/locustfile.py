"""
Calloway Load Test Harness — Locust definitions.

Simulates realistic webhook traffic against the Calloway API:
  - 70% inbound SMS (Twilio)
  - 20% Vapi post-call transcripts
  - 10% health-check pings

Safety:
  The target server MUST be started with DRY_RUN=true so that the pipeline
  processes messages but Twilio/Vapi sends are skipped.  The seed_data.py
  script creates the test agent referenced by these payloads.

Usage:
  locust -f tests/load/locustfile.py --host http://localhost:8000
"""

import random
import string
import uuid

from locust import HttpUser, between, task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Must match seed_data.py values
TEST_AGENT_TWILIO_NUMBER = "+15550000001"
TEST_CONTACT_NUMBERS = [f"+1555010{str(i).zfill(4)}" for i in range(100)]

SMS_BODIES = [
    "Hey, is the house on Elm Street still available?",
    "Can I schedule a showing for Saturday at 2pm?",
    "What's the price on MLS 12345?",
    "STOP",
    "Thanks for the info!",
    "I'm interested in the 3-bed listing near downtown.",
    "Do you have any open houses this weekend?",
    "Can you send me the disclosure docs?",
    "We'd like to make an offer.",
    "1",  # feedback score
    "2",  # feedback score
    "What are the HOA fees?",
    "Is the seller willing to negotiate?",
    "START",
    "HELP",
]

VAPI_TRANSCRIPTS = [
    "Hi, I saw your listing on Zillow and wanted to learn more about the property.",
    "I'm looking for a 3-bedroom home under 500K in the downtown area.",
    "Can we schedule a tour for tomorrow afternoon?",
    "What's the school district for the Oak Street property?",
    "I'd like to discuss making an offer on the house we saw last week.",
]


def _random_phone() -> str:
    return random.choice(TEST_CONTACT_NUMBERS)


def _random_message_sid() -> str:
    return "SM" + uuid.uuid4().hex[:32]


def _random_call_id() -> str:
    return "call_" + uuid.uuid4().hex[:24]


# ---------------------------------------------------------------------------
# Twilio SMS payload builder
# ---------------------------------------------------------------------------

def build_twilio_sms_payload() -> dict:
    """Build a realistic Twilio inbound SMS webhook payload."""
    return {
        "ToCountry": "US",
        "ToState": "",
        "SmsMessageSid": _random_message_sid(),
        "NumMedia": "0",
        "ToCity": "",
        "FromZip": "",
        "SmsSid": _random_message_sid(),
        "FromState": "CA",
        "SmsStatus": "received",
        "FromCity": "Los Angeles",
        "Body": random.choice(SMS_BODIES),
        "FromCountry": "US",
        "To": TEST_AGENT_TWILIO_NUMBER,
        "MessagingServiceSid": "MG" + uuid.uuid4().hex[:32],
        "ToZip": "",
        "NumSegments": "1",
        "MessageSid": _random_message_sid(),
        "AccountSid": "AC" + uuid.uuid4().hex[:32],
        "From": _random_phone(),
        "ApiVersion": "2010-04-01",
    }


# ---------------------------------------------------------------------------
# Vapi post-call payload builder
# ---------------------------------------------------------------------------

def build_vapi_post_call_payload() -> dict:
    """Build a realistic Vapi post-call webhook payload."""
    caller_phone = _random_phone()
    duration = random.randint(30, 600)
    return {
        "call_id": _random_call_id(),
        "type": "end-of-call-report",
        "status": "completed",
        "phoneNumber": {
            "number": TEST_AGENT_TWILIO_NUMBER,
            "twilioAccountSid": "AC" + uuid.uuid4().hex[:32],
        },
        "customer": {
            "number": caller_phone,
        },
        "duration": duration,
        "transcript": random.choice(VAPI_TRANSCRIPTS),
        "summary": "Caller inquired about a property listing.",
        "messages": [
            {"role": "assistant", "content": "Hello, thanks for calling!"},
            {"role": "user", "content": random.choice(VAPI_TRANSCRIPTS)},
            {"role": "assistant", "content": "I'd be happy to help with that."},
        ],
        "recordingUrl": f"https://example.com/recordings/{uuid.uuid4().hex}.wav",
    }


# ---------------------------------------------------------------------------
# Locust User classes
# ---------------------------------------------------------------------------

class SimulatedSMSUser(HttpUser):
    """Simulates inbound SMS traffic via Twilio webhook.

    Weight 7 = 70% of total traffic.
    """
    weight = 7
    wait_time = between(0.5, 3)

    @task
    def send_sms(self):
        payload = build_twilio_sms_payload()
        self.client.post(
            "/webhooks/twilio/inbound",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            name="/webhooks/twilio/inbound",
        )


class SimulatedVapiUser(HttpUser):
    """Simulates Vapi post-call webhook traffic.

    Weight 2 = 20% of total traffic.
    """
    weight = 2
    wait_time = between(2, 8)

    @task
    def post_call(self):
        payload = build_vapi_post_call_payload()
        self.client.post(
            "/webhooks/vapi/post-call",
            json=payload,
            name="/webhooks/vapi/post-call",
        )


class HealthCheckUser(HttpUser):
    """Simulates health-check pings.

    Weight 1 = 10% of total traffic.
    """
    weight = 1
    wait_time = between(1, 5)

    @task
    def check_health(self):
        self.client.get("/health", name="/health")
