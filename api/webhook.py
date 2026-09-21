"""
Quantum Trading Fleet v2.0 - Serverless Webhook Relay
Directs all webhook traffic to api.index handler
"""
import sys
import os

# Ensure api directory is in sys.path
api_dir = os.path.dirname(__file__)
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

from index import handler
