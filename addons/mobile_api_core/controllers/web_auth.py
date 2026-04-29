import time

from odoo import http
from odoo.http import request

# Import the token store from auth router
from odoo.addons.mobile_api_core.routers.auth import _login_tokens


class MobileWebAuth(http.Controller):
    """Handle mobile app WebView authentication via one-time tokens."""

    @http.route('/mobile/web-login', type='http', auth='none', csrf=False)
    def web_login(self, token=None, **kwargs):
        """Consume one-time token and create Odoo web session.

        This endpoint is called from the mobile app WebView. It:
        1. Validates the one-time token
        2. Creates an authenticated Odoo session
        3. Redirects to the target URL
        """
        if not token:
            return request.make_response(
                'Missing token parameter',
                status='400 Bad Request',
                headers=[('Content-Type', 'text/plain')]
            )

        # Get and validate token
        token_data = _login_tokens.pop(token, None)
        if not token_data:
            return request.make_response(
                'Invalid or expired token',
                status='400 Bad Request',
                headers=[('Content-Type', 'text/plain')]
            )

        if time.time() > token_data['expires']:
            return request.make_response(
                'Token expired',
                status='400 Bad Request',
                headers=[('Content-Type', 'text/plain')]
            )

        user_id = token_data['user_id']
        redirect_url = token_data['redirect']

        # Get the user
        user = request.env['res.users'].sudo().browse(user_id)
        if not user.exists():
            return request.make_response(
                'User not found',
                status='400 Bad Request',
                headers=[('Content-Type', 'text/plain')]
            )

        # Authenticate the session using Odoo's built-in mechanism
        # This properly sets the session cookie
        request.session.uid = user.id
        request.session.login = user.login
        request.session.session_token = user._compute_session_token(request.session.sid)

        # Update the environment with the authenticated user
        request.update_env(user=user)

        # Redirect to the target URL
        return request.redirect(redirect_url)
