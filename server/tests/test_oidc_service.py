"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


import unittest
from unittest.mock import patch

from tests._env import ensure_test_env

ensure_test_env()

import pytest

from services.auth.oidc_service import OIDCService


class OidcServiceTests(unittest.TestCase):
    def test_is_fresh_respects_cache_ttl(self):
        service = OIDCService()
        service._cache_ttl_seconds = 10
        with patch('services.auth.oidc_service.time.time', return_value=100):
            self.assertTrue(service._is_fresh(95))
            self.assertFalse(service._is_fresh(89))

    def test_build_authorization_url_contains_required_params(self):
        service = OIDCService()
        with patch.object(service, '_get_well_known', return_value={'authorization_endpoint': 'https://idp.example/auth'}), \
             patch('services.auth.oidc_service.config.OIDC_CLIENT_ID', 'client-1'), \
             patch('services.auth.oidc_service.config.OIDC_SCOPES', 'openid profile'):
            url = service.build_authorization_url('http://localhost/callback', 'state123', 'nonce456')

        self.assertIn('https://idp.example/auth?', url)
        self.assertIn('client_id=client-1', url)
        self.assertIn('state=state123', url)
        self.assertIn('nonce=nonce456', url)

    def test_oidc_transaction_one_time_use(self):
        service = OIDCService()
        with patch.object(service, '_get_well_known', return_value={'authorization_endpoint': 'https://idp.example/auth'}), \
             patch('services.auth.oidc_service.config.OIDC_CLIENT_ID', 'client-1'), \
             patch('services.auth.oidc_service.config.OIDC_SCOPES', 'openid profile'):
            session = service.start_authorization_transaction(
                redirect_uri='http://localhost/callback',
                state='state123',
                nonce='nonce456',
            )
            first = service.consume_authorization_transaction(
                transaction_id=session['transaction_id'],
                state='state123',
                redirect_uri='http://localhost/callback',
            )
            self.assertEqual(first.get('nonce'), 'nonce456')
            with self.assertRaises(ValueError):
                service.consume_authorization_transaction(
                    transaction_id=session['transaction_id'],
                    state='state123',
                    redirect_uri='http://localhost/callback',
                )


def test_oidc_pkce_mismatch_is_rejected():
    service = OIDCService()
    with patch.object(service, '_get_well_known', return_value={'authorization_endpoint': 'https://idp.example/auth'}), \
         patch('services.auth.oidc_service.config.OIDC_CLIENT_ID', 'client-1'), \
         patch('services.auth.oidc_service.config.OIDC_SCOPES', 'openid profile'):
        verifier = "correct-verifier"
        challenge = service._pkce_s256(verifier)
        session = service.start_authorization_transaction(
            redirect_uri='http://localhost/callback',
            state='state123',
            nonce='nonce456',
            code_challenge=challenge,
            code_challenge_method='S256',
        )
        with pytest.raises(ValueError):
            service.consume_authorization_transaction(
                transaction_id=session['transaction_id'],
                state='state123',
                redirect_uri='http://localhost/callback',
                code_verifier='wrong-verifier',
            )


if __name__ == '__main__':
    unittest.main()
