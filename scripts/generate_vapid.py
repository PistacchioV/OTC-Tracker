#!/usr/bin/env python3
"""Generate a VAPID key pair for Web Push and print the env vars to set.

Usage:  python scripts/generate_vapid.py

Copy the printed VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY into your .env (never
commit them). VAPID_SUBJECT should be a mailto: or https: contact URI.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apps.pages.webpush import generate_keypair  # noqa: E402

pub, priv = generate_keypair()
print('# Add these to your .env (keep the private key secret):')
print('VAPID_PUBLIC_KEY=' + pub)
print('VAPID_PRIVATE_KEY=' + priv)
print('VAPID_SUBJECT=mailto:otc-tracker@example.com')
