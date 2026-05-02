from odoo import http, _, fields
from odoo.http import request

class VehicleBorrowController(http.Controller):

    def _get_repair_data(self):
        """Helper to get data needed for the Report Issue Modal"""
        env_sudo = request.env(su=True)
        models = env_sudo['fleet.vehicle.model'].search([])
        v_domain = self._build_factory_domain([('active', '=', True)])
        vehicles = env_sudo['fleet.vehicle'].search(v_domain)
        vehicle_types = sorted(list(set([m.name for m in models if m.name])))
        
        current_user = request.env.user
        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', current_user.id)], limit=1
        )
        return vehicle_types, vehicles, employee

    @http.route(['/'], type='http', auth="public", website=True)
    def vehicle_home(self, **post):
        vehicle_types, vehicles, employee = self._get_repair_data()
        return request.render("vehicle_borrow.landing_page_template", {
            'vehicle_types': vehicle_types,
            'vehicles': vehicles,
            'current_employee': employee,
        })

    @http.route(['/vehicle/booking'], type='http', auth="user", website=True)
    def vehicle_booking_form(self, **kw):
        import logging
        _logger = logging.getLogger(__name__)
        from datetime import datetime
        
        current_user = request.env.user
        _logger.info("Accessing booking form: user=%s (id=%s)", current_user.login, current_user.id)
        
        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', current_user.id)], limit=1
        )
        
        # หากยังไม่มีข้อมูลพนักงาน ให้สร้างให้อัตโนมัติ (เพื่อความสะดวก)
        if not employee and not current_user._is_public():
            _logger.info("Employee not found for user %s, creating one...", current_user.login)
            try:
                employee = request.env['hr.employee'].sudo().create({
                    'name': current_user.name,
                    'user_id': current_user.id,
                })
                _logger.info("Created employee %s (id=%s) for user %s", employee.name, employee.id, current_user.login)
            except Exception as e:
                _logger.error("Failed to create employee for user %s: %s", current_user.login, str(e))
            
        # ค้นหาพาหนะที่ว่าง (ไม่อยู่ในสถานะ request, approved, borrowed และ ต้องพร้อมใช้งาน - ไม่เสีย)
        busy_requests = request.env['vehicle.borrow.request'].sudo().search([
            ('state', 'in', ['request', 'approved', 'borrowed'])
        ])
        busy_vehicle_ids = busy_requests.mapped('vehicle_id').ids
        # กรองตามโรงงานของผู้ใช้
        v_domain = self._build_factory_domain([
            ('id', 'not in', busy_vehicle_ids),
            ('vehicle_status', '=', 'active')
        ])
        vehicles = request.env['fleet.vehicle'].sudo().search(v_domain)
        
        # รายการประเภทรถทั้งหมดสำหรับ Dropdown ตัวกรอง (ดึงจาก DB จริง)
        all_models = request.env['fleet.vehicle.model'].sudo().search([])
        vehicle_types = sorted(list(set([m.name for m in all_models if m.name])))
        
        # รายการที่ผู้ใช้กำลังยืมอยู่ (สำหรับปุ่มคืนรถ)
        my_borrows = []
        if employee:
            my_borrows = request.env['vehicle.borrow.request'].sudo().search([
                ('employee_id', '=', employee.id),
                ('state', 'in', ['approved', 'borrowed', 'request']),
            ])
        
        # วันเวลาปัจจุบัน (ส่งให้ JS ใช้ pre-fill)
        now = datetime.now().strftime('%Y-%m-%dT%H:%M')
        
        error = kw.get('error')
        
        _logger.info("Rendering booking form: employee=%s, vehicles=%d, types=%s", employee.name if employee else "NONE", len(vehicles), vehicle_types)
        
        # ดึงข้อมูลสถานะรถทั้งหมด (เพื่อใช้กับ Modal แจ้งเสีย)
        v_all_domain = self._build_factory_domain([('active', '=', True)])
        all_vehicles = request.env['fleet.vehicle'].sudo().search(v_all_domain)

        return request.render('vehicle_borrow.booking_form_template', {
            'vehicles': vehicles,
            'all_vehicles': all_vehicles,
            'current_employee': employee,
            'my_borrows': my_borrows,
            'now': now,
            'error': error,
            'post': kw,
            'vehicle_types': vehicle_types,
        })

    @http.route(['/vehicle/booking/submit'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def vehicle_booking_submit(self, **post):
        import logging
        _logger = logging.getLogger(__name__)
        from datetime import datetime
        
        current_user = request.env.user
        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', current_user.id)], limit=1
        )
        
        # หากไม่มี (เช่นเพิ่งล็อกอินเข้ามาครั้งแรก) ให้สร้างให้อัตโนมัติ
        if not employee and not current_user._is_public():
             employee = request.env['hr.employee'].sudo().create({
                'name': current_user.name,
                'user_id': current_user.id,
            })

        # ค้นหาพาหนะที่ว่าง (เตรียมไว้กรณีแสดงผลฟอร์มใหม่พร้อม Error)
        busy_requests = request.env['vehicle.borrow.request'].sudo().search([
            ('state', 'in', ['request', 'approved', 'borrowed'])
        ])
        busy_vehicle_ids = busy_requests.mapped('vehicle_id').ids
        vehicles = request.env['fleet.vehicle'].sudo().search([
            ('id', 'not in', busy_vehicle_ids),
            ('vehicle_status', '=', 'active')
        ])
        now = datetime.now().strftime('%Y-%m-%dT%H:%M')
        
        if not employee:
            _logger.error("Missing employee during submit for user %s", current_user.login)
            return request.render('vehicle_borrow.booking_form_template', {
                'error': f'ไม่สามารถผูกข้อมูลพนักงานได้ โปรดติดต่อผู้ดูแลระบบ',
                'vehicles': vehicles,
                'current_employee': employee,
                'my_borrows': [],
                'now': now,
                'post': post,
            })
        
        try:
            from odoo import fields
            # บันทึกเฉพาะ date_start อัตโนมัติ โดยไม่ต้องกำหนด date_end
            # ใช้ fields.Datetime.now() เพื่อให้ตรงกับมาตรฐาน UTC ของ Odoo
            date_start = fields.Datetime.now()
            
            vals = {
                'employee_id': employee.id,
                'vehicle_id': int(post.get('vehicle_id')),
                'date_start': date_start,
                'purpose': post.get('purpose', ''),
                'state': 'request',
            }
            request.env['vehicle.borrow.request'].sudo().create(vals)
            return request.render('vehicle_borrow.booking_success_template')
        except Exception as e:
            _logger.error("Booking failed for %s: %s", current_user.login, str(e))
            my_borrows = []
            if employee:
                my_borrows = request.env['vehicle.borrow.request'].sudo().search([
                    ('employee_id', '=', employee.id),
                    ('state', 'in', ['approved', 'borrowed', 'request']),
                ])
            return request.render('vehicle_borrow.booking_form_template', {
                'error': f'ไม่สามารถบันทึกการจองได้: {str(e)}',
                'vehicles': vehicles,
                'current_employee': employee,
                'my_borrows': my_borrows,
                'now': now,
                'post': post,
            })

    @http.route(['/vehicle/my-bookings'], type='http', auth="user", website=True)
    def my_bookings_page(self, **post):
        current_user = request.env.user
        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', current_user.id)], limit=1
        )
        
        my_borrows = []
        if employee:
            my_borrows = request.env['vehicle.borrow.request'].sudo().search([
                ('employee_id', '=', employee.id)
            ], order='create_date desc')
            
        return request.render('vehicle_borrow.my_bookings_template', {
            'my_borrows': my_borrows,
            'current_employee': employee,
        })

    @http.route(['/vehicle/return/<int:req_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def vehicle_return(self, req_id, **post):
        from odoo import fields
        current_user = request.env.user
        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', current_user.id)], limit=1
        )
        borrow = request.env['vehicle.borrow.request'].sudo().browse(req_id)
        if borrow.exists() and borrow.employee_id.id == (employee.id if employee else -1):
            borrow.sudo().write({
                'state': 'returned',
                'date_end': fields.Datetime.now(),
            })
        return request.redirect('/vehicle/booking?msg=returned')

    @http.route(['/vehicle/cancel/<int:req_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def vehicle_cancel(self, req_id, **post):
        current_user = request.env.user
        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', current_user.id)], limit=1
        )
        borrow = request.env['vehicle.borrow.request'].sudo().browse(req_id)
        # ตรวจสอบว่าเป็นเจ้าของรายการถึงจะยกเลิกได้
        if borrow.exists() and borrow.employee_id.id == (employee.id if employee else -1):
            borrow.sudo().write({'state': 'cancelled'})
        return request.redirect('/vehicle/booking?msg=cancelled')

    @http.route(['/vehicle/report-issue/submit'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def vehicle_report_issue_submit(self, **post):
        try:
            vehicle_id = post.get('vehicle_id')
            description = post.get('description')
            
            if not vehicle_id or not description:
                return request.redirect((request.httprequest.referrer or '/') + "?error=กรุณาระบุรถและรายละเอียดอาการเสีย")
                
            request.env['vehicle.repair.request'].sudo().create({
                'vehicle_id': int(vehicle_id),
                'description': description,
                'reported_by_id': request.env.user.id,
            })
            
            # กลับไปหน้าเดิมพร้อมข้อความสำเร็จ
            redirect_url = request.httprequest.referrer or '/'
            if '?' in redirect_url:
                redirect_url += "&msg=repair_added"
            else:
                redirect_url += "?msg=repair_added"
            return request.redirect(redirect_url)
        except Exception as e:
            return request.redirect((request.httprequest.referrer or '/') + "?error=" + str(e))


    # --- ADMIN FRONTEND ---

    def _get_user_factory(self):
        """คืนโรงงานที่ user มีสิทธิ์: 'TQS', 'CKR', 'TPS' หรือ None (Head Admin)"""
        # 1. Check session first (set during login)
        session_factory = request.session.get('selected_factory')
        if session_factory:
            return session_factory

        user = request.env.user
        if user._is_admin() or user.has_group('base.group_system'):
            return None  # system admin = head admin
        if user.has_group('vehicle_borrow.group_vb_head_admin'):
            return None  # head admin เห็นทุกโรงงาน
        if user.has_group('vehicle_borrow.group_vb_admin_tqs') or user.has_group('vehicle_borrow.group_vb_user_tqs'):
            return 'TQS'
        if user.has_group('vehicle_borrow.group_vb_admin_ckr') or user.has_group('vehicle_borrow.group_vb_user_ckr'):
            return 'CKR'
        if user.has_group('vehicle_borrow.group_vb_admin_tps') or user.has_group('vehicle_borrow.group_vb_user_tps'):
            return 'TPS'
        return None

    def _is_admin(self):
        """Check if the current user has administrative permissions"""
        user = request.env.user
        return (
            user._is_admin()
            or user.has_group('fleet.fleet_group_manager')
            or user.has_group('base.group_system')
            or user.has_group('vehicle_borrow.group_vb_head_admin')
            or user.has_group('vehicle_borrow.group_vb_admin_tqs')
            or user.has_group('vehicle_borrow.group_vb_admin_ckr')
            or user.has_group('vehicle_borrow.group_vb_admin_tps')
        )

    def _is_head_admin(self):
        """Head Admin มีสิทธิ์เห็นทุกโรงงาน"""
        user = request.env.user
        return (
            user._is_admin()
            or user.has_group('base.group_system')
            or user.has_group('vehicle_borrow.group_vb_head_admin')
        )

    def _build_factory_domain(self, base_domain=None):
        """สร้าง domain กรองรถตาม factory ของ user ที่ล็อกอิน"""
        domain = list(base_domain or [])
        factory_id = request.session.get('factory_id')
        
        if self._is_head_admin() and not factory_id:
            return domain
            
        if not factory_id:
            domain.append(('id', '=', 0))
        else:
            domain.append(('factory_id', '=', int(factory_id)))
        return domain

    @http.route(['/admin/vehicle/dashboard'], type='http', auth="user", website=True)
    def admin_dashboard(self, **post):
        import logging
        _logger = logging.getLogger(__name__)

        if not self._is_admin():
            _logger.warning("ADMIN DASHBOARD: Access denied for user %s", request.env.user.name)
            return request.render("http_routing.403")

        env_sudo = request.env(su=True)
        user_factory = self._get_user_factory()  # None = head admin

        # domain กรองรถตาม factory
        factory_domain = [('factory', '=', user_factory)] if user_factory else []

        # ดึงประเภทรถจากฐานข้อมูลจริง (fleet.vehicle.model) เฉพาะที่มีในโรงงานตัวเอง
        vehicles_for_types = env_sudo['fleet.vehicle'].search(factory_domain)
        vehicle_types = sorted(list(set([v.model_id.name for v in vehicles_for_types if v.model_id.name])))
        if not vehicle_types:
            # fallback หากยังไม่มีรถในโรงงาน
            all_models = env_sudo['fleet.vehicle.model'].search([])
            vehicle_types = sorted(list(set([m.name for m in all_models if m.name])))

        default_type = vehicle_types[0] if vehicle_types else ''
        selected_type = post.get('type', default_type)

        # พาหนะทั้งหมดในโรงงานตัวเอง (KPI)
        all_vehicles = env_sudo['fleet.vehicle'].search(factory_domain) or []

        # รถตามประเภทที่เลือก
        type_domain = list(factory_domain) + [('model_id.name', '=', selected_type)]
        vehicles = env_sudo['fleet.vehicle'].search(type_domain) or []

        # คำขอยืมรถ (ถ้า factory admin กรองเฉพาะรถของโรงงาน)
        req_domain = [('vehicle_id.factory', '=', user_factory)] if user_factory else []
        borrow_requests = env_sudo['vehicle.borrow.request'].search(req_domain, order='create_date desc') or []

        vehicle_models = env_sudo['fleet.vehicle.model'].search([]) or []
        # ดึงกลุ่มสิทธิ์ต่างๆ เพื่อใช้กรองและส่งไปหน้ากาก
        head_admin_group = request.env.ref('vehicle_borrow.group_vb_head_admin')
        admin_tqs_group = request.env.ref('vehicle_borrow.group_vb_admin_tqs')
        admin_ckr_group = request.env.ref('vehicle_borrow.group_vb_admin_ckr')
        admin_tps_group = request.env.ref('vehicle_borrow.group_vb_admin_tps')
        user_tqs_group = request.env.ref('vehicle_borrow.group_vb_user_tqs')
        user_ckr_group = request.env.ref('vehicle_borrow.group_vb_user_ckr')
        user_tps_group = request.env.ref('vehicle_borrow.group_vb_user_tps')
        fleet_manager_group = request.env.ref('fleet.fleet_group_manager')

        # กรองรายชื่อพนักงานตามโรงงาน (ถ้าไม่ใช่ Head Admin)
        user_search_domain = [('share', '=', False)]
        if user_factory:
            # ใช้ Domain กรองตรงๆ จาก DB: ค้นหา User ที่มีกลุ่มของโรงงานที่เลือกอย่างน้อย 1 กลุ่ม
            my_role_ids = {
                'TQS': [admin_tqs_group.id, user_tqs_group.id],
                'CKR': [admin_ckr_group.id, user_ckr_group.id],
                'TPS': [admin_tps_group.id, user_tps_group.id],
            }.get(user_factory, [])
            user_search_domain.append(('groups_id', 'in', my_role_ids))
            
        users = env_sudo['res.users'].with_context(active_test=False).search(user_search_domain, order='login')

        _logger.info(
            "ADMIN DASHBOARD: user=%s factory=%s | type=%s | all_v=%d | vehicles=%d",
            request.env.user.name, user_factory or 'ALL', selected_type, len(all_vehicles), len(vehicles)
        )

        # ดึงรายการโยกย้ายรถ (Pending Transfers - ทั้งรออนุมัติและรอตอบรับ)
        transfer_domain = [('state', 'in', ['requested', 'approved'])]
        if user_factory:
            transfer_domain = ['&', ('state', 'in', ['requested', 'approved']), '|', ('from_factory', '=', user_factory), ('to_factory', '=', user_factory)]
        pending_transfers = request.env['vehicle.transfer.request'].sudo().search(transfer_domain, order='date_requested desc')

        # ดึงประวัติการโยกย้าย (Transfer History - ที่จบรายการแล้ว)
        history_transfer_domain = [('state', 'in', ['accepted', 'cancelled'])]
        if user_factory:
            history_transfer_domain = ['&', ('state', 'in', ['accepted', 'cancelled']), '|', ('from_factory', '=', user_factory), ('to_factory', '=', user_factory)]
        transfer_history = request.env['vehicle.transfer.request'].sudo().search(history_transfer_domain, order='date_accepted desc, write_date desc', limit=50)

        return request.render("vehicle_borrow.admin_dashboard_template", {
            'all_vehicles': all_vehicles,
            'vehicles': vehicles,
            'requests': borrow_requests,
            'models': vehicle_models,
            'users': users,
            'fleet_manager_group': fleet_manager_group,
            'head_admin_group': head_admin_group,
            'admin_tqs_group': admin_tqs_group,
            'admin_ckr_group': admin_ckr_group,
            'admin_tps_group': admin_tps_group,
            'user_tqs_group': user_tqs_group,
            'user_ckr_group': user_ckr_group,
            'user_tps_group': user_tps_group,
            'vehicle_types': vehicle_types,
            'selected_type': selected_type,
            'user_factory': user_factory,
            'is_head_admin': self._is_head_admin(),
            'pending_transfers': pending_transfers,
            'transfer_history': transfer_history,
        })

    @http.route(['/admin/member/add'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_member_add(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        try:
            name = post.get('name')
            login = post.get('login')
            password = post.get('password')
            role = post.get('role')  # 'user', 'head_admin', 'admin_tqs', 'admin_ckr', 'admin_tps'
            
            # สร้าง User
            new_user = request.env['res.users'].sudo().create({
                'name': name,
                'login': login,
                'password': password,
                'groups_id': [(6, 0, [request.env.ref('base.group_user').id])]
            })
            
            # กำหนด group ตาม role ที่เลือก
            group_map = {
                'head_admin': 'vehicle_borrow.group_vb_head_admin',
                'admin_tqs': 'vehicle_borrow.group_vb_admin_tqs',
                'admin_ckr': 'vehicle_borrow.group_vb_admin_ckr',
                'admin_tps': 'vehicle_borrow.group_vb_admin_tps',
                'user_tqs': 'vehicle_borrow.group_vb_user_tqs',
                'user_ckr': 'vehicle_borrow.group_vb_user_ckr',
                'user_tps': 'vehicle_borrow.group_vb_user_tps',
            }
            if role in group_map:
                group = request.env.ref(group_map[role])
                new_user.sudo().write({'groups_id': [(4, group.id)]})
                
            # สร้าง Employee (ถ้ายังไม่มี)
            request.env['hr.employee'].sudo().create({
                'name': name,
                'user_id': new_user.id,
            })
            
            return request.redirect("/admin/vehicle/dashboard?msg=member_added")
        except Exception as e:
            return request.redirect("/admin/vehicle/dashboard?error=" + str(e))

    @http.route(['/admin/member/delete/<int:user_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_member_delete(self, user_id, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        if user_id == request.env.user.id or user_id == 1:
            return request.redirect("/admin/vehicle/dashboard?error=ไม่สามารถลบบัญชีของตัวเองหรือ Admin หลักได้")
        
        user = request.env['res.users'].sudo().browse(user_id)
        if not user.exists():
            return request.redirect("/admin/vehicle/dashboard?error=ไม่พบผู้ใช้งานนี้ในระบบ")
        
        # ลองลบก่อน หากลบไม่ได้ (มีประวัติการจองผูกอยู่) ให้ Archive แทน
        try:
            # หา Employee ที่ผูกกับ User นี้
            emp = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
            with request.env.cr.savepoint():
                if emp:
                    emp.sudo().unlink()
                user.sudo().unlink()
        except Exception:
            # ลบไม่ได้ → Archive (ปิดการใช้งาน) แทน รักษาประวัติการจองไว้
            emp = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
            if emp:
                emp.sudo().write({'active': False})
            user.sudo().write({'active': False})
        
        return request.redirect("/admin/vehicle/dashboard?msg=member_deleted")

    @http.route(['/admin/member/role/<int:user_id>/<string:role>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_member_role(self, user_id, role, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        try:
            user = request.env['res.users'].sudo().browse(user_id)
            # ลบทุก factory group ก่อน แล้วค่อยเพิ่มใหม่
            all_factory_groups = [
                request.env.ref('vehicle_borrow.group_vb_head_admin'),
                request.env.ref('vehicle_borrow.group_vb_admin_tqs'),
                request.env.ref('vehicle_borrow.group_vb_admin_ckr'),
                request.env.ref('vehicle_borrow.group_vb_admin_tps'),
                request.env.ref('vehicle_borrow.group_vb_user_tqs'),
                request.env.ref('vehicle_borrow.group_vb_user_ckr'),
                request.env.ref('vehicle_borrow.group_vb_user_tps'),
                request.env.ref('fleet.fleet_group_manager'),
            ]
            # ถอด groups เดิมออกทั้งหมด
            user.sudo().write({'groups_id': [(3, g.id) for g in all_factory_groups]})
            
            # เพิ่ม group ใหม่
            group_map = {
                'head_admin': 'vehicle_borrow.group_vb_head_admin',
                'admin_tqs': 'vehicle_borrow.group_vb_admin_tqs',
                'admin_ckr': 'vehicle_borrow.group_vb_admin_ckr',
                'admin_tps': 'vehicle_borrow.group_vb_admin_tps',
                'user_tqs': 'vehicle_borrow.group_vb_user_tqs',
                'user_ckr': 'vehicle_borrow.group_vb_user_ckr',
                'user_tps': 'vehicle_borrow.group_vb_user_tps',
            }
            if role in group_map:
                group = request.env.ref(group_map[role])
                user.sudo().write({'groups_id': [(4, group.id)]})
            # role == 'user' = ไม่มี group admin
                
            return request.redirect("/admin/vehicle/dashboard?msg=role_updated")
        except Exception as e:
            return request.redirect("/admin/vehicle/dashboard?error=" + str(e))

    @http.route(['/admin/member/status/<int:user_id>/<string:status>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_member_status(self, user_id, status, **post):
        if not self._is_admin():
            return request.render("http_routing.403")

        try:
            user = request.env['res.users'].sudo().with_context(active_test=False).browse(user_id)
            if user.exists():
                active_val = True if status == 'active' else False
                user.sudo().write({'active': active_val})
                return request.redirect("/admin/vehicle/dashboard?msg=status_updated")
        except Exception as e:
            return request.redirect("/admin/vehicle/dashboard?error=" + str(e))
        return request.redirect("/admin/vehicle/dashboard")

    @http.route(['/admin/vehicle/add'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_vehicle_add(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        try:
            model_name = post.get('model_name')
            if not model_name:
                return request.redirect("/admin/vehicle/dashboard?error=Missing model name")

            # จัดการรูปภาพ (ถ้ามี)
            image_file = request.httprequest.files.get('image')
            image_b64 = False
            if image_file:
                import base64
                image_content = image_file.read()
                if image_content:
                    image_b64 = base64.b64encode(image_content).decode('ascii')

            # ค้นหารุ่นรถตามชื่อ ถ้าไม่มีให้สร้างใหม่ (รุ่นเหล่านี้ทำหน้าที่เป็นประเภทรถตามคำแนะนำผู้ใช้)
            model = request.env['fleet.vehicle.model'].sudo().search([('name', '=', model_name)], limit=1)
            if not model:
                # ตรวจสอบหา Brand พื้นฐาน (ถ้าไม่มีให้สร้าง)
                brand = request.env['fleet.vehicle.model.brand'].sudo().search([('name', '=', 'General')], limit=1)
                if not brand:
                    brand = request.env['fleet.vehicle.model.brand'].sudo().create({'name': 'General'})
                
                model = request.env['fleet.vehicle.model'].sudo().create({
                    'name': model_name,
                    'brand_id': brand.id,
                })

            vals = {
                'model_id': model.id,
                'license_plate': post.get('license_plate'),
                'factory': post.get('factory') or self._get_user_factory() or 'TQS',
            }
            if image_b64:
                vals['image_1920'] = image_b64

            request.env['fleet.vehicle'].sudo().create(vals)
            import logging
            logging.getLogger(__name__).info("Created vehicle with image length: %s", len(image_b64) if image_b64 else 0)
            return request.redirect("/admin/vehicle/dashboard?msg=vehicle_added&type=%s" % model_name)
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error("Error adding vehicle: %s", str(e))
            return request.redirect("/admin/vehicle/dashboard?error=" + str(e))

    @http.route(['/admin/vehicle/edit'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_vehicle_edit(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        try:
            vehicle_id = post.get('vehicle_id')
            license_plate = post.get('license_plate')
            
            vehicle = request.env['fleet.vehicle'].sudo().browse(int(vehicle_id))
            if not vehicle.exists():
                return request.redirect("/admin/vehicle/dashboard?error=ไม่พบรถยนต์ที่ต้องการแก้ไข")

            vals = {
                'license_plate': license_plate,
            }

            # จัดการรูปภาพ (ถ้ามี)
            image_file = request.httprequest.files.get('image')
            if image_file:
                import base64
                image_content = image_file.read()
                if image_content:
                    image_b64 = base64.b64encode(image_content).decode('ascii')
                    vals['image_1920'] = image_b64

            vehicle.sudo().write(vals)
            return request.redirect("/admin/vehicle/dashboard?msg=vehicle_updated")
        except Exception as e:
            return request.redirect("/admin/vehicle/dashboard?error=" + str(e))

    @http.route(['/admin/vehicle/status/<int:vehicle_id>/<string:status>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_vehicle_status(self, vehicle_id, status, **post):
        if not self._is_admin():
            return request.render("http_routing.403")

        try:
            vehicle = request.env['fleet.vehicle'].sudo().browse(vehicle_id)
            if vehicle.exists():
                vehicle.sudo().write({'vehicle_status': status})
                return request.redirect("/admin/vehicle/dashboard?msg=status_updated")
        except Exception as e:
            return request.redirect("/admin/vehicle/dashboard?error=" + str(e))
        return request.redirect("/admin/vehicle/dashboard")

    @http.route(['/admin/setup/init-vehicles'], type='http', auth="user", website=True)
    def admin_init_vehicles(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        env_sudo = request.env(su=True)
        # 1. ลบรถที่มีอยู่ออกทั้งหมด
        all_vehicles = env_sudo['fleet.vehicle'].search([])
        for v in all_vehicles:
            try:
                # ลอง unlink ก่อน หากมีประวัติจะใช้ archive แทน
                v.unlink()
            except Exception:
                v.write({'active': False})
        
        # 2. ข้อมูลรถใหม่ (อัปเดตชื่อตามที่ผู้ใช้ต้องการ 2026-03-30)
        new_vehicles_data = {
            'รถตัก': [
                'หมายเลข 1 - WA380-7', 
                'หมายเลข 2 - WA380-7', 
                'หมายเลข 3 - WA380-7', 
                'หมายเลข 4 - CAT962G'
            ],
            'รถโฟล์คลิฟต์': [
                'หมายเลข 1 - TCM-1', 
                'หมายเลข 2 - TCM-1'
            ],
            'รถบรรทุก': [
                'ISUZU 83-3633 หมายเลข TR2', 
                'ISUZU หมายเลข TR2'
            ],
            'รถไถ': [
                'รถไถ ฟอร์ด TT-1', 
                'รถไถ ฟอร์ด TT-2'
            ],
            'รถไฟฟ้า': [
                'EV-1 - รถกระเช้าไฟฟ้า', 
                'EV-1 - รถดูดฝุ่นไฟฟ้า'
            ],
        }
        
        # ค้นหาหรือสร้าง Brand กลาง
        brand = env_sudo['fleet.vehicle.model.brand'].search([('name', '=', 'TNW-GROUP')], limit=1)
        if not brand:
            brand = env_sudo['fleet.vehicle.model.brand'].create({'name': 'TNW-GROUP'})
            
        for v_type, names in new_vehicles_data.items():
            # ค้นหาหรือสร้าง Model จากชื่อประเภทรถ
            model = env_sudo['fleet.vehicle.model'].search([('name', '=', v_type)], limit=1)
            if not model:
                model = env_sudo['fleet.vehicle.model'].create({
                    'name': v_type,
                    'brand_id': brand.id,
                })
            
            for name in names:
                env_sudo['fleet.vehicle'].create({
                    'model_id': model.id,
                    'license_plate': name,
                    'vehicle_status': 'active'
                })
        
        return request.redirect("/admin/vehicle/dashboard?msg=setup_completed")
        


    @http.route(['/admin/vehicle/bookings'], type='http', auth="user", website=True)
    def admin_bookings(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        env_sudo = request.env(su=True)
        user_factory = self._get_user_factory()
        
        domain = [('vehicle_id.factory', '=', user_factory)] if user_factory else []
        borrow_requests = env_sudo['vehicle.borrow.request'].search(domain, order='id desc')
        
        return request.render("vehicle_borrow.admin_bookings_template", {
            'requests': borrow_requests,
        })

    @http.route(['/admin/vehicle/delete/<int:vehicle_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_vehicle_delete(self, vehicle_id, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        try:
            vehicle = request.env['fleet.vehicle'].sudo().browse(vehicle_id)
            if vehicle.exists():
                vehicle.sudo().unlink()
            return request.redirect("/admin/vehicle/dashboard?msg=vehicle_deleted")
        except Exception as e:
            return request.redirect("/admin/vehicle/dashboard?error=" + str(e))

    @http.route(['/admin/booking/delete/<int:req_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_booking_delete(self, req_id, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        try:
            req = request.env['vehicle.borrow.request'].sudo().browse(req_id)
            if req.exists():
                req.sudo().unlink()
            return request.redirect("/admin/vehicle/bookings?msg=booking_deleted")
        except Exception as e:
            return request.redirect("/admin/vehicle/bookings?error=" + str(e))

    @http.route(['/admin/setup/list-vehicles'], type='http', auth="user", website=True)
    def admin_list_vehicles(self, **post):
        if not self._is_admin(): return request.render("http_routing.403")
        vehicles = request.env['fleet.vehicle'].sudo().search([])
        output = "Vehicle List (ID - Name - Status):<br/>"
        for v in vehicles:
            output += f"{v.id} - {v.license_plate} - {'Active' if v.active else 'Archived'} - Image: {'Yes' if v.image_128 else 'No'}<br/>"
        return output

    @http.route(['/admin/setup/delete-vehicle-by-name'], type='http', auth="user", website=True)
    def admin_delete_vehicle_by_name(self, name=None, **post):
        if not self._is_admin(): return request.render("http_routing.403")
        if not name: return "Please provide ?name=xxx"
        
        env_sudo = request.env(su=True)
        vehicles = env_sudo['fleet.vehicle'].search([('license_plate', '=', name)], limit=1)
        if not vehicles:
            return f"Vehicle with name '{name}' not found."
        
        v = vehicles[0]
        # ตรวจสอบประวัติที่มีการผูกพัน
        borrows = env_sudo['vehicle.borrow.request'].search_count([('vehicle_id', '=', v.id)])
        repairs = env_sudo['vehicle.repair.request'].search_count([('vehicle_id', '=', v.id)])
        
        reasons = []
        if borrows > 0: reasons.append(f"มีประวัติการจอง {borrows} รายการ")
        if repairs > 0: reasons.append(f"มีประวัติการซ่อม {repairs} รายการ")
        
        if reasons:
            # ถ้ามีประวัติ จะให้ลบไม่ได้ แต่เราสามารถให้ option 'archive' ได้
            # แต่ในที่นี้เราแค่แสดงเหตุผล
            return f"<b>ทำไมคุณถึงลบ {name} ไม่ได้:</b><br/>" + "<br/>".join(reasons) + "<br/><br/>" + \
                   f"ลิงก์ข้อมูลเหล่านี้ยังคงอยู่ ไม่สามารถลบรถตัวจริงทิ้งได้ " + \
                   f"แนะนำให้ใช้การปิดการใช้งาน (Archive) แทนครับ<br/><br/>" + \
                   f"<a href='/admin/setup/list-vehicles' class='btn btn-primary'>กลับไปดูรายการทั้งหมด</a>"

        try:
            v.unlink()
            return f"Successfully deleted vehicle named '{name}'."
        except Exception as e:
            return f"Error while trying to unlink: {str(e)}"

    @http.route(['/admin/setup/force-delete-vehicle'], type='http', auth="user", website=True)
    def admin_force_delete_vehicle(self, name=None, **post):
        if not self._is_admin(): return request.render("http_routing.403")
        if not name: return "Please provide ?name=xxx"
        
        env_sudo = request.env(su=True)
        vehicle = env_sudo['fleet.vehicle'].search([('license_plate', '=', name)], limit=1)
        if not vehicle:
            return f"Vehicle with name '{name}' not found."
            
        # 1. ลบประวัติการซ่อมทั้งหมดของรถคันนี้
        repairs = env_sudo['vehicle.repair.request'].search([('vehicle_id', '=', vehicle.id)])
        repair_count = len(repairs)
        repairs.unlink()
        
        # 2. ลบประวัติการยืมทั้งหมดของรถคันนี้
        borrows = env_sudo['vehicle.borrow.request'].search([('vehicle_id', '=', vehicle.id)])
        borrow_count = len(borrows)
        borrows.unlink()
        
        # 3. ลบตัวรถออก
        vehicle.unlink()
        
        return f"Successfully cleaned all data and deleted vehicle '{name}'.<br/>" \
               f"- Deleted {repair_count} repair requests.<br/>" \
               f"- Deleted {borrow_count} borrowing requests.<br/><br/>" \
               f"<a href='/admin/vehicle/dashboard' class='btn btn-success'>กลับสู่ Dashboard</a>"

    @http.route(['/admin/vehicle/repair'], type='http', auth="user", website=True)
    def admin_repair_page(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
            
        current_user = request.env.user
        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', current_user.id)], limit=1
        )
        
        env_sudo = request.env(su=True)
        user_factory = self._get_user_factory()
        factory_domain = [('factory', '=', user_factory)] if user_factory else []
        repair_factory_domain = [('vehicle_id.factory', '=', user_factory)] if user_factory else []

        # Fetch all vehicle models and vehicles for the form
        models = env_sudo['fleet.vehicle.model'].search([])
        # กรองรถเฉพาะในโรงงาน
        vehicles = env_sudo['fleet.vehicle'].search(list(factory_domain) + [('active', '=', True)])
        vehicle_types = sorted(list(set([m.name for m in models if m.name])))
        
        # Recent repairs (those currently repairing or recently added)
        # กรองเฉพาะในโรงงาน
        recent_repairs = env_sudo['vehicle.repair.request'].search(list(repair_factory_domain) + [('state', '=', 'repairing')], limit=10, order='create_date desc')
        
        # --- Full Repair History Logic ---
        history_domain = list(repair_factory_domain) + [('state', '=', 'done')]
        
        # Extract filters from post
        f_vehicle_id = post.get('f_vehicle_id')
        f_type = post.get('f_type')
        f_report_start = post.get('f_report_start')
        f_report_end = post.get('f_report_end')
        f_finish_start = post.get('f_finish_start')
        f_finish_end = post.get('f_finish_end')
        
        if f_vehicle_id:
            history_domain.append(('vehicle_id', '=', int(f_vehicle_id)))
        
        if f_type:
            history_domain.append(('vehicle_id.model_id.name', '=', f_type))
        
        if f_report_start:
            history_domain.append(('report_date', '>=', f_report_start))
        if f_report_end:
            history_domain.append(('report_date', '<=', f_report_end + ' 23:59:59'))
            
        if f_finish_start:
            history_domain.append(('finish_date', '>=', f_finish_start))
        if f_finish_end:
            history_domain.append(('finish_date', '<=', f_finish_end + ' 23:59:59'))
            
        repair_history = env_sudo['vehicle.repair.request'].search(history_domain, order='finish_date desc')
        
        # All vehicles for the history filter (filtered by factory)
        all_vehicles_history = env_sudo['fleet.vehicle'].search(factory_domain)
        
        # ดึงกลุ่มสิทธิ์สำหรับแสดง Badge ใน Template
        head_admin_group = request.env.ref('vehicle_borrow.group_vb_head_admin')
        admin_tqs_group = request.env.ref('vehicle_borrow.group_vb_admin_tqs')
        admin_ckr_group = request.env.ref('vehicle_borrow.group_vb_admin_ckr')
        admin_tps_group = request.env.ref('vehicle_borrow.group_vb_admin_tps')
        user_tqs_group = request.env.ref('vehicle_borrow.group_vb_user_tqs')
        user_ckr_group = request.env.ref('vehicle_borrow.group_vb_user_ckr')
        user_tps_group = request.env.ref('vehicle_borrow.group_vb_user_tps')

        return request.render("vehicle_borrow.admin_repair_template", {
            'vehicle_types': vehicle_types,
            'vehicles': vehicles,
            'current_employee': employee,
            'recent_repairs': recent_repairs,
            'repair_history': repair_history,
            'all_vehicles_history': all_vehicles_history,
            'filters': post, # Pass back to maintain states
            'msg': post.get('msg'),
            'error': post.get('error'),
            'user_factory': user_factory,
            'is_head_admin': self._is_head_admin(),
            'head_admin_group': head_admin_group,
            'admin_tqs_group': admin_tqs_group,
            'admin_ckr_group': admin_ckr_group,
            'admin_tps_group': admin_tps_group,
            'user_tqs_group': user_tqs_group,
            'user_ckr_group': user_ckr_group,
            'user_tps_group': user_tps_group,
        })

    @http.route(['/admin/vehicle/repair/submit'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_repair_submit(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
            
        try:
            vehicle_id = post.get('vehicle_id')
            description = post.get('description')
            
            if not vehicle_id or not description:
                return request.redirect("/admin/vehicle/repair?error=กรุณาระบุรถและรายละเอียดอาการเสีย")
                
            request.env['vehicle.repair.request'].sudo().create({
                'vehicle_id': int(vehicle_id),
                'description': description,
                'reported_by_id': request.env.user.id,
            })
            
            return request.redirect("/admin/vehicle/repair?msg=repair_added")
        except Exception as e:
            return request.redirect("/admin/vehicle/repair?error=" + str(e))
            
    @http.route(['/admin/setup/rename-vehicles'], type='http', auth="user", website=True)
    def admin_rename_vehicles(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        env_sudo = request.env(su=True)
        mappings = {
            'WA380-7 หมายเลข 1': 'หมายเลข 1 - WA380-7',
            'WA380-7 หมายเลข 2': 'หมายเลข 2 - WA380-7',
            'WA380-7 หมายเลข 3': 'หมายเลข 3 - WA380-7',
            'CAT962G หมายเลข 4': 'หมายเลข 4 - CAT962G',
            'TCM-1 หมายเลข 1': 'หมายเลข 1 - TCM-1',
            'TCM-1 หมายเลข 2': 'หมายเลข 2 - TCM-1',
            'รถกระเช้าไฟฟ้า EV-1': 'EV-1 - รถกระเช้าไฟฟ้า',
            'รถกระเช๊าไฟฟ้า EV-1': 'EV-1 - รถกระเช้าไฟฟ้า',
            'รถดูดฝุ่นไฟฟ้า EV-1': 'EV-1 - รถดูดฝุ่นไฟฟ้า',
            'รถดูดฝุ่นไฟฟ้า EV-2': 'EV-1 - รถดูดฝุ่นไฟฟ้า',
        }
        
        updated_count = 0
        for old_name, new_name in mappings.items():
            vehicles = env_sudo['fleet.vehicle'].search([('license_plate', '=', old_name)])
            for vehicle in vehicles:
                vehicle.write({'license_plate': new_name})
                updated_count += 1
        
        return request.redirect(f"/admin/vehicle/dashboard?msg=rename_completed&count={updated_count}")

    @http.route(['/admin/setup/assign-tqs'], type='http', auth="user", website=True)
    def admin_assign_tqs(self, **post):
        """กำหนดรถที่ยังไม่มี factory ทั้งหมดให้เป็น TQS"""
        if not self._is_admin():
            return request.render("http_routing.403")

        env_sudo = request.env(su=True)
        # กำหนด TQS ให้รถที่ยังไม่มีค่า factory หรือมีค่าว่าง
        vehicles = env_sudo['fleet.vehicle'].search(['|', ('factory', '=', False), ('factory', '=', '')])
        count = len(vehicles)
        vehicles.write({'factory': 'TQS'})
        return request.redirect(f"/admin/vehicle/dashboard?msg=assign_tqs_done&count={count}")


    @http.route(['/admin/vehicle/repair/done'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_repair_done(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        repair_id = post.get('repair_id')
        repair = request.env['vehicle.repair.request'].sudo().browse(int(repair_id))
        
        if repair.exists():
            vals = {
                'repair_details': post.get('repair_details'),
                'parts_used': post.get('parts_used'),
                'repair_cost': float(post.get('repair_cost') or 0),
            }
            repair.action_done(vals)
        return request.redirect("/admin/vehicle/repair?msg=status_updated")


    # --- SPARE PARTS FRONTEND ---

    @http.route(['/admin/spare-parts'], type='http', auth="user", website=True)
    def admin_spare_parts_dashboard(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        env_sudo = request.env(su=True)
        selected_factory = request.session.get('selected_factory')
        user = request.env.user
        is_head_admin = user.has_group('vehicle_borrow.group_vb_head_admin')
        user_factory = self._get_user_factory()
        
        # กรองข้อมูลเฉพาะโมเดลที่มี field 'factory'
        if is_head_admin and not selected_factory:
            vehicle_domain = [('active', '=', True)]
            repair_domain = [('state', '=', 'repairing')]
            repair_factory_domain = []
        elif not selected_factory:
            # ถ้าไม่มีโรงงานใน session และไม่ใช่ Head Admin ให้ล็อกไว้ (ไม่เห็นอะไรเลย)
            vehicle_domain = [('id', '=', 0)]
            repair_domain = [('id', '=', 0)]
            repair_factory_domain = []
        else:
            vehicle_domain = [('factory', '=', selected_factory), ('active', '=', True)]
            repair_domain = [('vehicle_id.factory', '=', selected_factory), ('state', '=', 'repairing')]
            repair_factory_domain = [('vehicle_id.factory', '=', selected_factory)]
            
        categories = env_sudo['vehicle.spare.part.category'].search([], order='name')
        vehicles = env_sudo['fleet.vehicle'].search(vehicle_domain)
        repairs = env_sudo['vehicle.repair.request'].search(repair_domain)
        
        # ดึงประเภทรถจากฐานข้อมูล
        all_models = env_sudo['fleet.vehicle.model'].search([])
        vehicle_types = sorted(list(set([m.name for m in all_models if m.name])))
        
        # Filtering logic for Inventory
        domain = []
        
        # Search Filter (Name or Code)
        search = post.get('search')
        if search:
            domain += ['|', ('name', 'ilike', search), ('code', 'ilike', search)]
            
        # Category Filter
        selected_category_id = post.get('category_id') or 'all'
        if selected_category_id != 'all':
            domain.append(('category_id', '=', int(selected_category_id)))
            
        # Stock Status Filter (Mutually Exclusive)
        stock_status = post.get('stock_status') or 'all'
        if stock_status == 'out':
            domain.append(('qty_on_hand', '=', 0))
        elif stock_status == 'low':
            domain += [('qty_on_hand', '>', 0), ('qty_on_hand', '<=', 2)]
        elif stock_status == 'normal':
            domain.append(('qty_on_hand', '>', 2))
            
        # อะไหล่กรองตามโรงงานของ user ที่ล็อกอิน
        # Head Admin + ไม่ได้เลือกโรงงาน → เห็นทุกโรงงาน
        # Admin โรงงาน → เห็นเฉพาะโรงงานตัวเอง
        if user_factory:
            domain.append(('factory', '=', user_factory))
        # แสดงรายการทั้งหมดรวมถึงที่ปิดการใช้งาน (Inactive) เพื่อให้แอดมินเปิดกลับมาได้
        parts = env_sudo['vehicle.spare.part'].with_context(active_test=False).search(domain, order='name')
        
        # ดึงประวัติทั้งหมดของอะไหล่เหล่านี้เพื่อคำนวณสต็อกแยกตามล็อต 
        # ใช้ sudo เพื่อให้เห็นรายการ In (รับเข้า) ทั้งหมดสำหรับคำนวณล็อตราคา
        all_movements = env_sudo['vehicle.spare.part.movement'].search([
            ('part_id', 'in', parts.ids)
        ], order='date asc') if parts else env_sudo['vehicle.spare.part.movement'].browse()

        lot_details = {}  # { "2750": { "Lot A": {"qty": 10, "price": 500} } }
        for move in all_movements:
            if not move.part_id: continue
            
            p_id = str(move.part_id.id)
            lot = move.lot_number or 'ไม่มีระบุล็อต'
            
            if p_id not in lot_details:
                lot_details[p_id] = {}
            if lot not in lot_details[p_id]:
                lot_details[p_id][lot] = {'qty': 0, 'price': 0.0}
            
            if move.move_type == 'in':
                lot_details[p_id][lot]['qty'] += move.qty
                if move.unit_price > 0:
                    lot_details[p_id][lot]['price'] = move.unit_price
            else:
                lot_details[p_id][lot]['qty'] -= move.qty

        # แปลงเป็นเซตของอินรายการเพื่อใช้เลือกล็อตใน Modal เบิก (เฉพาะที่มีของ)
        in_movements = all_movements.filtered(lambda m: m.move_type == 'in' and m.lot_number)

        history_limit = 10
        # กรองประวัติการใช้อะไหล่ เฉพาะของรถในโรงงานตัวเอง (ถ้ามีการระบุรถ)
        if repair_factory_domain:
            movement_domain = ['|', ('vehicle_id', '=', False)] + list(repair_factory_domain)
        else:
            movement_domain = []
        recent_history = env_sudo['vehicle.spare.part.movement'].search(movement_domain, limit=history_limit, order='date desc, id desc')

        # ดึงกลุ่มสิทธิ์สำหรับ Badge
        head_admin_group = request.env.ref('vehicle_borrow.group_vb_head_admin')
        admin_tqs_group = request.env.ref('vehicle_borrow.group_vb_admin_tqs')
        admin_ckr_group = request.env.ref('vehicle_borrow.group_vb_admin_ckr')
        admin_tps_group = request.env.ref('vehicle_borrow.group_vb_admin_tps')
        user_tqs_group = request.env.ref('vehicle_borrow.group_vb_user_tqs')
        user_ckr_group = request.env.ref('vehicle_borrow.group_vb_user_ckr')
        user_tps_group = request.env.ref('vehicle_borrow.group_vb_user_tps')

        import json
        # แปลง lot_details เป็น JSON String สำหรับ JavaScript
        # สำคัญ: Odoo QWeb จะ escape เครื่องหมาย " เป็น &quot; 
        # เราจะส่งไปเป็น String ธรรมดา แล้วใช้ t-out ใน XML เพื่อปลดล็อก
        lot_details_json = json.dumps(lot_details, ensure_ascii=False)

        return request.render("vehicle_borrow.admin_spare_parts_template", {
            'parts': parts,
            'categories': categories,
            'vehicles': vehicles,
            'vehicle_types': vehicle_types,
            'repairs': repairs,
            'recent_history': recent_history,
            'in_movements': in_movements,
            'lot_details': lot_details,
            'lot_details_json': lot_details_json,
            'filters': {
                'search': search,
                'category_id': selected_category_id,
                'stock_status': stock_status,
            },
            'error': post.get('error'),
            'msg': post.get('msg'),
            'user_factory': user_factory,
            'is_head_admin': self._is_head_admin(),
            'head_admin_group': head_admin_group,
            'admin_tqs_group': admin_tqs_group,
            'admin_ckr_group': admin_ckr_group,
            'admin_tps_group': admin_tps_group,
            'user_tqs_group': user_tqs_group,
            'user_ckr_group': user_ckr_group,
            'user_tps_group': user_tps_group,
        })

    @http.route(['/admin/spare-parts/move'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_spare_parts_move_submit(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        try:
            part_id = int(post.get('part_id'))
            move_type = post.get('move_type') # 'in' or 'out'
            qty = float(post.get('qty') or 0)
            
            vals = {
                'part_id': part_id,
                'move_type': move_type,
                'qty': qty,
                'reference': post.get('reference'),
                'date': fields.Datetime.now(),
            }
            
            if move_type == 'out':
                if post.get('vehicle_id'):
                    vals['vehicle_id'] = int(post.get('vehicle_id'))
                if post.get('repair_id'):
                    vals['repair_id'] = int(post.get('repair_id'))
            
            # บันทึกล็อตและราคาสำหรับทุกประเภทรายการ (ถ้ามี)
            if post.get('lot_number'):
                vals['lot_number'] = post.get('lot_number')
            if post.get('unit_price'):
                try:
                    vals['unit_price'] = float(post.get('unit_price'))
                except: pass

            request.env['vehicle.spare.part.movement'].sudo().create(vals)
            return request.redirect("/admin/spare-parts?msg=move_success")
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Spare Parts Move Error: %s", str(e))
            return request.redirect("/admin/spare-parts?error=" + str(e))

    @http.route(['/admin/spare-parts/history'], type='http', auth="user", website=True)
    def admin_spare_parts_history(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        env_sudo = request.env(su=True)
        user_factory = self._get_user_factory()
        factory_domain = [('factory', '=', user_factory)] if user_factory else []
        repair_factory_domain = [('vehicle_id.factory', '=', user_factory)] if user_factory else []

        domain = []
        if user_factory:
            # เห็นเฉพาะประวัติที่ไม่ระบุรถ หรือระบุรถในโรงงานตัวเอง
            domain += ['|', ('vehicle_id', '=', False)] + list(repair_factory_domain)
        
        # Filtering logic
        f_date_start = post.get('f_date_start')
        f_date_end = post.get('f_date_end')
        f_part_id = post.get('f_part_id')
        f_vehicle_type = post.get('f_vehicle_type')
        f_vehicle_id = post.get('f_vehicle_id')
        f_move_type = post.get('f_move_type')
        
        if f_date_start:
            domain.append(('date', '>=', f_date_start + ' 00:00:00'))
        if f_date_end:
            domain.append(('date', '<=', f_date_end + ' 23:59:59'))
        if f_part_id and f_part_id != 'all':
            domain.append(('part_id', '=', int(f_part_id)))
        if f_vehicle_type and f_vehicle_type != 'all':
            domain.append(('vehicle_id.model_id.name', '=', f_vehicle_type))
        if f_vehicle_id and f_vehicle_id != 'all':
            domain.append(('vehicle_id', '=', int(f_vehicle_id)))
        if f_move_type and f_move_type != 'all':
            domain.append(('move_type', '=', f_move_type))
            
        history = env_sudo['vehicle.spare.part.movement'].search(domain, order='date desc, id desc')
        
        # Fetch data for filter dropdowns
        all_parts = env_sudo['vehicle.spare.part'].search([], order='name')
        # กรองรถใน dropdown ให้เห็นเฉพาะโรงงานตัวเอง
        all_vehicles = env_sudo['fleet.vehicle'].search(list(factory_domain) + [('active', '=', True)])
        
        # ดึงประเภทรถจากฐานข้อมูล
        all_models = env_sudo['fleet.vehicle.model'].search([])
        vehicle_types = sorted(list(set([m.name for m in all_models if m.name])))
        
        # ดึงกลุ่มสิทธิ์สำหรับ Badge
        head_admin_group = request.env.ref('vehicle_borrow.group_vb_head_admin')
        admin_tqs_group = request.env.ref('vehicle_borrow.group_vb_admin_tqs')
        admin_ckr_group = request.env.ref('vehicle_borrow.group_vb_admin_ckr')
        admin_tps_group = request.env.ref('vehicle_borrow.group_vb_admin_tps')
        user_tqs_group = request.env.ref('vehicle_borrow.group_vb_user_tqs')
        user_ckr_group = request.env.ref('vehicle_borrow.group_vb_user_ckr')
        user_tps_group = request.env.ref('vehicle_borrow.group_vb_user_tps')

        return request.render("vehicle_borrow.admin_spare_parts_history_template", {
            'history': history,
            'parts': all_parts,
            'vehicles': all_vehicles,
            'vehicle_types': vehicle_types,
            'filters': {
                'f_date_start': f_date_start,
                'f_date_end': f_date_end,
                'f_part_id': f_part_id,
                'f_vehicle_type': f_vehicle_type,
                'f_vehicle_id': f_vehicle_id,
                'f_move_type': f_move_type,
            },
            'user_factory': user_factory,
            'is_head_admin': self._is_head_admin(),
            'head_admin_group': head_admin_group,
            'admin_tqs_group': admin_tqs_group,
            'admin_ckr_group': admin_ckr_group,
            'admin_tps_group': admin_tps_group,
            'user_tqs_group': user_tqs_group,
            'user_ckr_group': user_ckr_group,
            'user_tps_group': user_tps_group,
        })

    @http.route(['/admin/spare-parts/add'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_spare_parts_add(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        try:
            user_factory = self._get_user_factory()  # None = Head Admin
            vals = {
                'name': post.get('name'),
                'code': post.get('code'),
                'uom': post.get('uom', 'ชิ้น'),
                'min_qty': float(post.get('min_qty') or 1.0),
                'description': post.get('description'),
                'factory': user_factory or 'TQS',  # กำหนด factory อัตโนมัติตาม role
            }
            
            if post.get('category_id'):
                vals['category_id'] = int(post.get('category_id'))
                
            # Image handling
            image_file = request.httprequest.files.get('image')
            if image_file:
                import base64
                image_content = image_file.read()
                if image_content:
                    vals['image'] = base64.b64encode(image_content).decode('ascii')

            request.env['vehicle.spare.part'].sudo().create(vals)
            return request.redirect("/admin/spare-parts?msg=part_added")
        except Exception as e:
            return request.redirect("/admin/spare-parts?error=" + str(e))

    @http.route(['/admin/spare-parts/edit'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_spare_parts_edit(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        try:
            part_id = int(post.get('part_id'))
            part = request.env['vehicle.spare.part'].sudo().browse(part_id)
            if not part.exists():
                return request.redirect("/admin/spare-parts?error=ไม่พบรายการอะไหล่")
                
            vals = {
                'name': post.get('name'),
                'code': post.get('code'),
                'uom': post.get('uom', 'ชิ้น'),
                'min_qty': float(post.get('min_qty') or 1.0),
                'description': post.get('description'),
            }
            
            # Image handling
            image_file = request.httprequest.files.get('image')
            if image_file:
                import base64
                image_content = image_file.read()
                if image_content:
                    vals['image'] = base64.b64encode(image_content).decode('ascii')

            part.write(vals)
            return request.redirect("/admin/spare-parts?msg=part_updated")
        except Exception as e:
            return request.redirect("/admin/spare-parts?error=" + str(e))

    @http.route(['/admin/spare-parts/toggle-active/<int:part_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_spare_parts_toggle_active(self, part_id, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        try:
            part = request.env['vehicle.spare.part'].sudo().with_context(active_test=False).browse(part_id)
            if part.exists():
                new_state = not part.active
                part.write({'active': new_state})
                msg = "part_activated" if new_state else "part_deactivated"
                return request.redirect("/admin/spare-parts?msg=" + msg)
            return request.redirect("/admin/spare-parts?error=ไม่พบรายการอะไหล่")
        except Exception as e:
            return request.redirect("/admin/spare-parts?error=" + str(e))

    @http.route(['/admin/spare-parts/delete/<int:part_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_spare_parts_delete(self, part_id, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        try:
            part = request.env['vehicle.spare.part'].sudo().with_context(active_test=False).browse(part_id)
            if part.exists():
                # ตรวจสอบก่อนว่ามีการใช้งานหรือไม่
                movements = request.env['vehicle.spare.part.movement'].sudo().search_count([('part_id', '=', part_id)])
                if movements > 0:
                    # หากมีประวัติ ให้ปิดการใช้งานแทนการลบ
                    part.write({'active': False})
                    return request.redirect("/admin/spare-parts?msg=part_deactivated")
                
                part.unlink()
                return request.redirect("/admin/spare-parts?msg=part_deleted")
            return request.redirect("/admin/spare-parts?error=ไม่พบรายการอะไหล่")
        except Exception as e:
            return request.redirect("/admin/spare-parts?error=" + str(e))

    # --- Vehicle Transfer System ---
    
    @http.route(['/admin/vehicle/transfer/submit'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_vehicle_transfer_submit(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        try:
            vehicle_id = int(post.get('vehicle_id'))
            to_factory = post.get('to_factory')
            reason = post.get('reason')
            
            request.env['vehicle.transfer.request'].sudo().create({
                'vehicle_id': vehicle_id,
                'to_factory': to_factory,
                'reason': reason,
                'state': 'requested'
            })
            return request.redirect('/admin/vehicle/dashboard?msg=transfer_requested')
        except Exception as e:
            return request.redirect('/admin/vehicle/dashboard?error=' + str(e))

    @http.route(['/admin/vehicle/transfer/approve/<int:req_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_vehicle_transfer_approve(self, req_id, **post):
        if not self._is_head_admin():
            return request.render("http_routing.403")
        
        transfer = request.env['vehicle.transfer.request'].sudo().browse(req_id)
        if transfer.exists():
            transfer.action_approve()
            return request.redirect('/admin/vehicle/dashboard?msg=transfer_approved')
        return request.redirect('/admin/vehicle/dashboard')

    @http.route(['/admin/vehicle/transfer/cancel/<int:req_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_vehicle_transfer_cancel(self, req_id, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        transfer = request.env['vehicle.transfer.request'].sudo().browse(req_id)
        if transfer.exists():
            transfer.action_cancel()
            return request.redirect('/admin/vehicle/dashboard?msg=transfer_cancelled')
        return request.redirect('/admin/vehicle/dashboard')

    @http.route(['/admin/vehicle/transfer/accept/<int:req_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_vehicle_transfer_accept(self, req_id, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        transfer = request.env['vehicle.transfer.request'].sudo().browse(req_id)
        if transfer.exists():
            # ตรวจสอบว่าผู้กด อยู่ในโรงงานปลายทางหรือไม่ (ยกเว้น Head Admin)
            user_factory = self._get_user_factory()
            if not self._is_head_admin() and transfer.to_factory != user_factory:
                return request.redirect('/admin/vehicle/dashboard?error=ไม่ใช่โรงงานปลายทาง')
                
            transfer.action_accept()
            return request.redirect('/admin/vehicle/dashboard?msg=transfer_accepted')
        return request.redirect('/admin/vehicle/dashboard')



