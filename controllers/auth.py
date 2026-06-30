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
        # POST: ให้ Odoo จัดการการตรวจสอบสิทธิ์การล็อกอินก่อน (ภาษาไทย)
        # ──────────────────────────────────────────────────
        response = super().web_login(redirect=redirect, **kw)

        # หากล็อกอินไม่สำเร็จ (ผู้ใช้ยังไม่เข้าสู่ระบบ) ให้ส่งคืนตามปกติ (ภาษาไทย)
        uid = request.session.uid
        if not uid:
            return response

        # ──────────────────────────────────────────────────
        # ผู้ใช้ล็อกอินสำเร็จแล้ว -> วิเคราะห์โรงงานที่สังกัดอัตโนมัติตามกลุ่มสิทธิ์ (ภาษาไทย)
        # ──────────────────────────────────────────────────
        user = request.env['res.users'].sudo().browse(uid)
        
        # 1. เช็กว่าผู้ใช้เป็น Head Admin หรือไม่
        is_head_admin = (
            user._is_admin()
            or user.has_group('base.group_system')
            or user.has_group('vehicle_borrow.group_vb_head_admin')
        )
        if is_head_admin:
            # ดีฟอลต์เป็น TQS ตามความต้องการสำหรับ Head Admin (ภาษาไทย)
            request.session['selected_factory'] = 'TQS'
            _logger.info("Login (Head Admin): User %s automatically assigned to TQS.", user.login)
            return response

        # 2. เช็กหาโรงงานอื่นสำหรับแอดมินธรรมดาและผู้ใช้งานทั่วไป (ภาษาไทย)
        assigned_factory = None
        if user.has_group('vehicle_borrow.group_vb_admin_tqs') or user.has_group('vehicle_borrow.group_vb_user_tqs'):
            assigned_factory = 'TQS'
        elif user.has_group('vehicle_borrow.group_vb_admin_ckr') or user.has_group('vehicle_borrow.group_vb_user_ckr'):
            assigned_factory = 'CKR'
        elif user.has_group('vehicle_borrow.group_vb_admin_tps') or user.has_group('vehicle_borrow.group_vb_user_tps'):
            assigned_factory = 'TPS'

        if assigned_factory:
            request.session['selected_factory'] = assigned_factory
            _logger.info("Login: User %s automatically assigned to factory '%s' based on groups.", user.login, assigned_factory)
        else:
            # หากไม่พบโรงงาน ให้แสดงทั้งหมดเป็นค่าเริ่มต้น หรือเป็น 'ALL' (ภาษาไทย)
            request.session['selected_factory'] = 'ALL'
            _logger.info("Login: User %s has no specific factory groups, defaulting to ALL.", user.login)

        return response
