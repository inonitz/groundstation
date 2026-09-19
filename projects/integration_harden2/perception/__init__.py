"""The perception engine package. engine.py is pure logic (models injected); detectors.py owns
the vision models; vlm_client.py talks to the resident model (the VLM). Requires the integration_harden
root on sys.path (every consumer already does this)."""
from .engine import PerceptionEngine, parse_highlight, ascii_only, scale_vlm_box, selftest, parse_count
