import logging
from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.home import Home

_logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Factory group mapping
# Key: factory code | Value: list of xmlids that belong to that factory
# Head Admin (group_vb_head_admin) is allowed for ANY factory selection.
# -------------------------------------------------------------------
FACTORY_GROUP_MAP = {
    'TQS': [
        'vehicle_borrow.group_vb_head_admin',
        'vehicle_borrow.group_vb_admin_tqs',
        'vehicle_borrow.group_vb_user_tqs',
    ],
    'CKR': [
        'vehicle_borrow.group_vb_head_admin',
        'vehicle_borrow.group_vb_admin_ckr',
        'vehicle_borrow.group_vb_user_ckr',
    ],
    'TPS': [
        'vehicle_borrow.group_vb_head_admin',
        'vehicle_borrow.group_vb_admin_tps',
        'vehicle_borrow.group_vb_user_tps',
    ],
}

VALID_FACTORIES = set(FACTORY_GROUP_MAP.keys())


class VehicleBorrowAuthController(Home):
    """Override Odoo's Home login to enforce factory-based access control."""

    @http.route('/web/login', type='http', auth='public', website=True, sitemap=False,
                methods=['GET', 'POST'])
    def web_login(self, redirect=None, **kw):
        """
        Intercept POST /web/login.
        After Odoo authenticates the user, check if their factory group
        matches the factory they selected on the login page.
        If it doesn't match → sign them out and return with an error.
        """
        # ──────────────────────────────────────────────────
        # For GET requests: pass through to the original handler.
        # ──────────────────────────────────────────────────
        if request.httprequest.method == 'GET':
            return super().web_login(redirect=redirect, **kw)

        # ──────────────────────────────────────────────────
        # POST: let Odoo handle authentication first
        # ──────────────────────────────────────────────────
        selected_factory = kw.get('factory', '').strip().upper()
        response = super().web_login(redirect=redirect, **kw)

        # If authentication failed (user still not logged in), just return.
        uid = request.session.uid
        if not uid:
            return response

        # ──────────────────────────────────────────────────
        # User is now authenticated. Validate factory.
        # ──────────────────────────────────────────────────
        if not selected_factory or selected_factory not in VALID_FACTORIES:
            # No factory selected (e.g., direct POST without JS) → allow
            _logger.debug(
                "Login: user %s – no factory selected, skipping factory check.", uid
            )
            return response

        # Check if user belongs to at least one allowed group for that factory
        user = request.env['res.users'].sudo().browse(uid)
        allowed_groups = FACTORY_GROUP_MAP.get(selected_factory, [])
        is_allowed = any(user.has_group(g) for g in allowed_groups)

        if is_allowed:
            _logger.debug(
                "Login: user %s – factory '%s' validated OK. Redirecting to /automotive", uid, selected_factory
            )
            # Store factory context in session for frontend filtering
            request.session['selected_factory'] = selected_factory
            return request.redirect('/automotive')

        # ──────────────────────────────────────────────────
        # Factory mismatch → log out and show error
        # ──────────────────────────────────────────────────
        _logger.warning(
            "Login BLOCKED: user %s (uid=%s) selected factory '%s' but is not in any allowed group for that factory.",
            user.login, uid, selected_factory
        )
        request.session.logout(keep_db=True)

        # Redirect back to login page with the error flag
        return request.redirect(
            '/web/login?factory_error=1&factory=' + selected_factory
        )
