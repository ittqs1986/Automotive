from odoo import http, _, fields
from odoo.http import request
import math # นำเข้าโมดูล math สำหรับใช้งานปัดเศษในการแบ่งหน้า (Pagination)
from urllib.parse import urlencode # นำเข้าฟังก์ชัน urlencode สำหรับจัดรูปแบบพารามิเตอร์ URL ในระบบแบ่งหน้า (Pagination)

class VehicleBorrowController(http.Controller):

    def _get_repair_data(self):
        """Helper to get data needed for the Report Issue Modal"""
        env_sudo = request.env(su=True)
        # ดึงประเภทรถเฉพาะที่มีตัวรถจริงและสถานะ Active ในระบบตามสิทธิ์โรงงาน
        v_domain = self._build_factory_domain([('active', '=', True)])
        vehicles = env_sudo['fleet.vehicle'].search(v_domain)
        vehicle_types = sorted(list(set([v.model_id.name for v in vehicles if v.model_id and v.model_id.name])))
        
        current_user = request.env.user
        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', current_user.id)], limit=1
        )
        return vehicle_types, vehicles, employee

    @http.route(['/automotive'], type='http', auth="public", website=True)
    def vehicle_home(self, **post):
        scan_vehicle_id = post.get('scan_vehicle_id')
        if scan_vehicle_id:
            # หากตรวจพบว่ามีการสแกน QR Code และส่งรหัสรถมา ให้เปลี่ยนเส้นทางไปยังหน้าจองรถทันที
            return request.redirect(f'/automotive/booking?vehicle_id={scan_vehicle_id}')
        vehicle_types, vehicles, employee = self._get_repair_data()
        return request.render("vehicle_borrow.landing_page_template", {
            'vehicle_types': vehicle_types,
            'vehicles': vehicles,
            'current_employee': employee,
        })

    @http.route(['/automotive/booking'], type='http', auth="user", website=True)
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
        
        # ดึงข้อมูลสถานะรถทั้งหมด (เพื่อใช้กับ Dropdown ตัวกรองประเภทรถ และ Modal แจ้งเสีย)
        v_all_domain = self._build_factory_domain([('active', '=', True)])
        all_vehicles = request.env['fleet.vehicle'].sudo().search(v_all_domain)

        # รายการประเภทรถทั้งหมดสำหรับ Dropdown (ดึงเฉพาะรุ่นรถที่มีอยู่จริงตามสิทธิ์โรงงาน)
        vehicle_types = sorted(list(set([v.model_id.name for v in all_vehicles if v.model_id and v.model_id.name])))
        
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

    @http.route(['/automotive/booking/submit'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
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

    @http.route(['/automotive/my-bookings'], type='http', auth="user", website=True)
    def my_bookings_page(self, **post):
        current_user = request.env.user
        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', current_user.id)], limit=1
        )
        
        # [แก้ไข] ระบบแบ่งหน้า (Pagination) 20 รายการต่อหน้า สำหรับหน้าประวัติการใช้งานของฉัน
        import math
        from urllib.parse import urlencode

        # รับหมายเลขหน้าปัจจุบันจากตัวแปร query parameter
        try:
            page = int(post.get('page', 1))
        except (ValueError, TypeError):
            page = 1
        if page < 1:
            page = 1

        limit = 20
        offset = (page - 1) * limit

        my_borrows = []
        total_count = 0
        total_pages = 1
        
        if employee:
            # ดึงยอดรวมรายการทั้งหมดของผู้ใช้เพื่อนำไปใช้คำนวณจำนวนหน้า
            total_count = request.env['vehicle.borrow.request'].sudo().search_count([
                ('employee_id', '=', employee.id)
            ])
            total_pages = math.ceil(total_count / limit) or 1
            if page > total_pages:
                page = total_pages
                offset = (page - 1) * limit

            # ค้นหารายการการใช้งานของฉัน โดยจำกัดหน้าละ 20 รายการ ( limit=20 )
            my_borrows = request.env['vehicle.borrow.request'].sudo().search([
                ('employee_id', '=', employee.id)
            ], order='create_date desc', limit=limit, offset=offset)
            
        # สร้างรายการหน้าทั้งหมดเพื่อแสดงเป็นแถบปุ่มกดตัวเลข
        pages_list = []
        for p in range(1, total_pages + 1):
            params = post.copy()
            params['page'] = p
            params = {k: v for k, v in params.items() if v}
            pages_list.append({
                'num': p,
                'url': '/automotive/my-bookings?' + urlencode(params),
                'is_current': p == page
            })

        # URL สำหรับปุ่มย้อนกลับไปหน้าก่อนหน้า (Previous Page)
        prev_page_url = None
        if page > 1:
            params = post.copy()
            params['page'] = page - 1
            params = {k: v for k, v in params.items() if v}
            prev_page_url = '/automotive/my-bookings?' + urlencode(params)

        # URL สำหรับปุ่มเปิดไปยังหน้าถัดไป (Next Page)
        next_page_url = None
        if page < total_pages:
            params = post.copy()
            params['page'] = page + 1
            params = {k: v for k, v in params.items() if v}
            next_page_url = '/automotive/my-bookings?' + urlencode(params)

        return request.render('vehicle_borrow.my_bookings_template', {
            'my_borrows': my_borrows,
            'current_employee': employee,
            'page': page,
            'total_pages': total_pages,
            'total_count': total_count,
            'pages_list': pages_list,
            'prev_page_url': prev_page_url,
            'next_page_url': next_page_url,
        })

    @http.route(['/automotive/return/<int:req_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
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
        return request.redirect('/automotive/booking?msg=returned')

    @http.route(['/automotive/cancel/<int:req_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def vehicle_cancel(self, req_id, **post):
        current_user = request.env.user
        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', current_user.id)], limit=1
        )
        borrow = request.env['vehicle.borrow.request'].sudo().browse(req_id)
        # ตรวจสอบว่าเป็นเจ้าของรายการถึงจะยกเลิกได้
        if borrow.exists() and borrow.employee_id.id == (employee.id if employee else -1):
            borrow.sudo().write({'state': 'cancelled'})
        return request.redirect('/automotive/booking?msg=cancelled')

    @http.route(['/automotive/report-issue/submit'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
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
        """สร้าง domain กรองรถตาม factory ของ user ที่ล็อกอิน (ปรับปรุงแก้ไขให้ใช้ selected_factory จาก session)"""
        domain = list(base_domain or [])
        user_factory = self._get_user_factory()
        
        if self._is_head_admin() and not user_factory:
            return domain
            
        if not user_factory:
            domain.append(('id', '=', 0))
        else:
            domain.append(('factory', '=', user_factory))
        return domain

    @http.route(['/automotive/admin/kpi'], type='http', auth="user", website=True)
    def admin_kpi_dashboard(self, **post):
        """
        หน้าแดชบอร์ดสรุปสถิติและตัวชี้วัดผลงานหลัก (KPI Dashboard) สำหรับ Head Admin และ Admin
        """
        if not self._is_admin():
            return request.render("http_routing.403")

        env_sudo = request.env(su=True)
        user_factory = self._get_user_factory()

        # --- 1. สถิติตัวรถ (Vehicles Stats) ---
        # กรองข้อมูลยานพาหนะตามโรงงานของผู้ใช้ (หากมีสิทธิ์เฉพาะโรงงาน)
        v_domain = [('factory', '=', user_factory)] if user_factory else []
        vehicles = env_sudo['fleet.vehicle'].search(v_domain)
        total_vehicles = len(vehicles)
        active_vehicles = len(vehicles.filtered(lambda v: v.vehicle_status == 'active'))
        repairing_vehicles = len(vehicles.filtered(lambda v: v.vehicle_status == 'repairing'))
        broken_vehicles = len(vehicles.filtered(lambda v: v.vehicle_status == 'broken'))
        retired_vehicles = len(vehicles.filtered(lambda v: v.vehicle_status == 'retired'))

        # --- 2. สถิติการยืมรถ (Borrowing Stats) ---
        # กรองข้อมูลใบขอจองยืมรถตามโรงงานต้นสังกัดของตัวรถ
        b_domain = [('vehicle_id.factory', '=', user_factory)] if user_factory else []
        borrows = env_sudo['vehicle.borrow.request'].search(b_domain)
        total_borrows = len(borrows)
        pending_borrows = len(borrows.filtered(lambda b: b.state == 'request'))
        approved_borrows = len(borrows.filtered(lambda b: b.state == 'approved'))
        borrowed_borrows = len(borrows.filtered(lambda b: b.state == 'borrowed'))
        returned_borrows = len(borrows.filtered(lambda b: b.state == 'returned'))

        # --- 3. สถิติการแจ้งซ่อม (Repairing Stats) ---
        # กรองข้อมูลประวัติใบแจ้งซ่อมตามโรงงานของรถยนต์ที่ส่งซ่อม
        r_domain = [('vehicle_id.factory', '=', user_factory)] if user_factory else []
        repairs = env_sudo['vehicle.repair.request'].search(r_domain)
        total_repairs = len(repairs)
        ongoing_repairs = len(repairs.filtered(lambda r: r.state == 'repairing'))
        done_repairs = len(repairs.filtered(lambda r: r.state == 'done'))
        total_repair_cost = sum(repairs.mapped('repair_cost'))

        # --- 4. สถิติคลังอะไหล่ (Spare Parts Stats) ---
        # กรองคลังอะไหล่และสถิติอะไหล่ตามโรงงานที่เก็บ
        p_domain = [('factory', '=', user_factory)] if user_factory else []
        parts = env_sudo['vehicle.spare.part'].search(p_domain)
        total_parts = len(parts)
        total_qty_on_hand = sum(parts.mapped('qty_on_hand'))
        low_stock_parts = parts.filtered(lambda p: p.qty_on_hand <= p.min_qty)

        # --- 5. สถิติการส่งย้ายรถยนต์ข้ามโรงงาน (Transfer Stats) ---
        # กรองใบคำขอส่งย้ายยานพาหนะตามสิทธิ์โรงงาน
        t_domain = [('vehicle_id.factory', '=', user_factory)] if user_factory else []
        transfers = env_sudo['vehicle.transfer.request'].search(t_domain)
        total_transfers = len(transfers)
        pending_transfers = len(transfers.filtered(lambda t: t.state in ('requested', 'approved')))
        accepted_transfers = len(transfers.filtered(lambda t: t.state == 'accepted'))

        # --- 6. อันดับความนิยมและค่าใช้จ่ายสูงสุด (Rankings & Top Lists) ---
        # หา 5 อันดับรถยนต์ที่ถูกยืมใช้งานบ่อยที่สุด
        from collections import Counter
        borrow_vehicle_ids = borrows.mapped('vehicle_id.id')
        borrow_counts = Counter(borrow_vehicle_ids)
        top_borrowed = []
        for vehicle_id, count in borrow_counts.most_common(5):
            vehicle = env_sudo['fleet.vehicle'].browse(vehicle_id)
            if vehicle.exists():
                # ปรับแก้ให้ใช้หมายเลขทะเบียน/ชื่อรถยนต์สั้นกระชับ เพื่อป้องกัน UI ตกหล่นในแดชบอร์ด KPI
                top_borrowed.append({
                    'name': vehicle.license_plate or vehicle.name,
                    'factory': vehicle.factory,
                    'count': count
                })

        # ดึง 5 รายการซ่อมที่มีค่าใช้จ่ายสูงที่สุด
        expensive_repairs = repairs.filtered(lambda r: r.repair_cost > 0).sorted(key=lambda r: r.repair_cost, reverse=True)[:5]

        # จัดเตรียม Context เพื่อส่งไปแสดงผลที่ View QWeb
        context = {
            'total_vehicles': total_vehicles,
            'active_vehicles': active_vehicles,
            'repairing_vehicles': repairing_vehicles,
            'broken_vehicles': broken_vehicles,
            'retired_vehicles': retired_vehicles,
            'total_borrows': total_borrows,
            'pending_borrows': pending_borrows,
            'approved_borrows': approved_borrows,
            'borrowed_borrows': borrowed_borrows,
            'returned_borrows': returned_borrows,
            'total_repairs': total_repairs,
            'ongoing_repairs': ongoing_repairs,
            'done_repairs': done_repairs,
            'total_repair_cost': total_repair_cost,
            'total_parts': total_parts,
            'total_qty_on_hand': total_qty_on_hand,
            'low_stock_parts': low_stock_parts,
            'total_transfers': total_transfers,
            'pending_transfers': pending_transfers,
            'accepted_transfers': accepted_transfers,
            'top_borrowed': top_borrowed,
            'expensive_repairs': expensive_repairs,
            'user_factory': user_factory or 'ทั้งหมด',
        }
        return request.render('vehicle_borrow.admin_kpi_dashboard_template', context)

    @http.route(['/automotive/dashboard'], type='http', auth="user", website=True)
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

        # ดึงประเภทรถจากฐานข้อมูลจริง (fleet.vehicle.model) เฉพาะที่มีในโรงงานตัวเอง (ภาษาไทยคอมเมนต์)
        vehicles_for_types = env_sudo['fleet.vehicle'].search(factory_domain)
        vehicle_types = sorted(list(set([v.model_id.name for v in vehicles_for_types if v.model_id.name])))
        if not vehicle_types:
            # fallback หากยังไม่มีรถในโรงงาน (ภาษาไทยคอมเมนต์)
            all_models = env_sudo['fleet.vehicle.model'].search([])
            vehicle_types = sorted(list(set([m.name for m in all_models if m.name])))

        default_type = vehicle_types[0] if vehicle_types else ''
        selected_type = post.get('type', default_type)

        # พาหนะทั้งหมดในโรงงานตัวเอง (สำหรับ KPI และส่วนหัว) ไม่ต้องจำกัด pagination (ภาษาไทยคอมเมนต์)
        all_vehicles = env_sudo['fleet.vehicle'].search(factory_domain) or []

        # นำเข้า math และ urlencode สำหรับคำนวณแบ่งหน้าและสร้าง query parameter (ภาษาไทยคอมเมนต์)
        import math
        from urllib.parse import urlencode

        # --- ระบบแบ่งหน้า (Pagination) สำหรับตาราง "จัดการคลังรถยนต์" (แสดงครั้งละ 10 รายการ) ---
        try:
            v_page = int(post.get('v_page', 1))
        except (ValueError, TypeError):
            v_page = 1
        if v_page < 1:
            v_page = 1

        v_limit = 10
        v_offset = (v_page - 1) * v_limit

        # ดึงรถตามประเภทที่เลือก (ภาษาไทยคอมเมนต์)
        type_domain = list(factory_domain) + [('model_id.name', '=', selected_type)]
        
        # นับจำนวนรถยนต์ทั้งหมดตามประเภทที่เลือกเพื่อคำนวณจำนวนหน้า (ภาษาไทยคอมเมนต์)
        v_total_count = env_sudo['fleet.vehicle'].search_count(type_domain)
        v_total_pages = math.ceil(v_total_count / v_limit) or 1
        if v_page > v_total_pages:
            v_page = v_total_pages
            v_offset = (v_page - 1) * v_limit

        # ดึงรายการรถยนต์เฉพาะหน้านั้นๆ (จำกัด 10 รายการ) (ภาษาไทยคอมเมนต์)
        vehicles = env_sudo['fleet.vehicle'].search(type_domain, limit=v_limit, offset=v_offset) or []

        # สร้างรายการปุ่มลิงก์ Pagination รถยนต์โดยรักษาพารามิเตอร์อื่นๆ ไว้ (ภาษาไทยคอมเมนต์)
        v_pages_list = []
        for p in range(1, v_total_pages + 1):
            params = post.copy()
            params['v_page'] = p
            params = {k: v for k, v in params.items() if v}
            v_pages_list.append({
                'num': p,
                'url': '/automotive/dashboard?' + urlencode(params),
                'is_current': p == v_page
            })

        v_prev_page_url = None
        if v_page > 1:
            params = post.copy()
            params['v_page'] = v_page - 1
            params = {k: v for k, v in params.items() if v}
            v_prev_page_url = '/automotive/dashboard?' + urlencode(params)

        v_next_page_url = None
        if v_page < v_total_pages:
            params = post.copy()
            params['v_page'] = v_page + 1
            params = {k: v for k, v in params.items() if v}
            v_next_page_url = '/automotive/dashboard?' + urlencode(params)


        # --- ระบบแบ่งหน้า (Pagination) สำหรับตาราง "จัดการพนักงาน/สิทธิ์" (แสดงครั้งละ 10 รายการ) ---
        try:
            u_page = int(post.get('u_page', 1))
        except (ValueError, TypeError):
            u_page = 1
        if u_page < 1:
            u_page = 1

        u_limit = 10
        u_offset = (u_page - 1) * u_limit

        # คำขอยืมรถ (สำหรับ KPI แดชบอร์ด ไม่ระบุ pagination) (ภาษาไทยคอมเมนต์)
        req_domain = [('vehicle_id.factory', '=', user_factory)] if user_factory else []
        borrow_requests = env_sudo['vehicle.borrow.request'].search(req_domain, order='create_date desc') or []

        vehicle_models = env_sudo['fleet.vehicle.model'].search([]) or []
        
        # ดึงกลุ่มสิทธิ์ต่างๆ เพื่อใช้กรองและส่งไปหน้ากาก (ภาษาไทยคอมเมนต์)
        head_admin_group = request.env.ref('vehicle_borrow.group_vb_head_admin')
        admin_tqs_group = request.env.ref('vehicle_borrow.group_vb_admin_tqs')
        admin_ckr_group = request.env.ref('vehicle_borrow.group_vb_admin_ckr')
        admin_tps_group = request.env.ref('vehicle_borrow.group_vb_admin_tps')
        user_tqs_group = request.env.ref('vehicle_borrow.group_vb_user_tqs')
        user_ckr_group = request.env.ref('vehicle_borrow.group_vb_user_ckr')
        user_tps_group = request.env.ref('vehicle_borrow.group_vb_user_tps')
        fleet_manager_group = request.env.ref('fleet.fleet_group_manager')

        # กรองรายชื่อพนักงานตามโรงงาน (กรองไม่เอาผู้ใช้งาน ID 1 ออกเพื่อไม่ให้กระทบกับการแบ่งหน้า) (ภาษาไทยคอมเมนต์)
        user_search_domain = [('share', '=', False), ('id', '!=', 1)]
        if user_factory:
            # ใช้ Domain แบบ OR '|' เพื่อให้แอดมิน TQS, CKR, TPS เห็น Head Admin ในตารางจัดการสิทธิ์ด้วย (ภาษาไทยคอมเมนต์)
            my_role_ids = {
                'TQS': [admin_tqs_group.id, user_tqs_group.id],
                'CKR': [admin_ckr_group.id, user_ckr_group.id],
                'TPS': [admin_tps_group.id, user_tps_group.id],
            }.get(user_factory, [])
            user_search_domain += [
                '|',
                ('group_ids', 'in', my_role_ids),
                ('group_ids', 'in', [head_admin_group.id])
            ]
            
        # นับจำนวนพนักงานทั้งหมดที่ตรงตามเงื่อนไขเพื่อคำนวณจำนวนหน้า (ภาษาไทยคอมเมนต์)
        u_total_count = env_sudo['res.users'].with_context(active_test=False).search_count(user_search_domain)
        u_total_pages = math.ceil(u_total_count / u_limit) or 1
        if u_page > u_total_pages:
            u_page = u_total_pages
            u_offset = (u_page - 1) * u_limit

        # ดึงรายชื่อพนักงานเฉพาะหน้านั้นๆ (จำกัด 10 รายการ) (ภาษาไทยคอมเมนต์)
        users = env_sudo['res.users'].with_context(active_test=False).search(
            user_search_domain, order='login', limit=u_limit, offset=u_offset
        )

        # สร้างรายการปุ่มลิงก์ Pagination พนักงานโดยรักษาพารามิเตอร์อื่นๆ ไว้ (ภาษาไทยคอมเมนต์)
        u_pages_list = []
        for p in range(1, u_total_pages + 1):
            params = post.copy()
            params['u_page'] = p
            params = {k: v for k, v in params.items() if v}
            u_pages_list.append({
                'num': p,
                'url': '/automotive/dashboard?' + urlencode(params),
                'is_current': p == u_page
            })

        u_prev_page_url = None
        if u_page > 1:
            params = post.copy()
            params['u_page'] = u_page - 1
            params = {k: v for k, v in params.items() if v}
            u_prev_page_url = '/automotive/dashboard?' + urlencode(params)

        u_next_page_url = None
        if u_page < u_total_pages:
            params = post.copy()
            params['u_page'] = u_page + 1
            params = {k: v for k, v in params.items() if v}
            u_next_page_url = '/automotive/dashboard?' + urlencode(params)

        _logger.info(
            "ADMIN DASHBOARD: user=%s factory=%s | type=%s | all_v=%d | vehicles=%d",
            request.env.user.name, user_factory or 'ALL', selected_type, len(all_vehicles), len(vehicles)
        )

        # ดึงรายการโยกย้ายรถ (Pending Transfers - ทั้งรออนุมัติและรอตอบรับ) (ภาษาไทยคอมเมนต์)
        transfer_domain = [('state', 'in', ['requested', 'approved'])]
        if user_factory:
            transfer_domain = ['&', ('state', 'in', ['requested', 'approved']), '|', ('from_factory', '=', user_factory), ('to_factory', '=', user_factory)]
        pending_transfers = request.env['vehicle.transfer.request'].sudo().search(transfer_domain, order='date_requested desc')

        # --- ระบบแบ่งหน้า (Pagination) สำหรับตาราง "ประวัติการโยกย้ายรถ" (แสดงครั้งละ 10 รายการ) ---
        try:
            t_page = int(post.get('t_page', 1))
        except (ValueError, TypeError):
            t_page = 1
        if t_page < 1:
            t_page = 1

        t_limit = 10
        t_offset = (t_page - 1) * t_limit

        # ดึงประวัติการโยกย้าย (Transfer History - ที่จบรายการแล้ว) (ภาษาไทยคอมเมนต์)
        history_transfer_domain = [('state', 'in', ['accepted', 'cancelled'])]
        if user_factory:
            history_transfer_domain = ['&', ('state', 'in', ['accepted', 'cancelled']), '|', ('from_factory', '=', user_factory), ('to_factory', '=', user_factory)]
        
        # นับจำนวนประวัติการโยกย้ายทั้งหมดเพื่อคำนวณจำนวนหน้า (ภาษาไทยคอมเมนต์)
        t_total_count = request.env['vehicle.transfer.request'].sudo().search_count(history_transfer_domain)
        t_total_pages = math.ceil(t_total_count / t_limit) or 1
        if t_page > t_total_pages:
            t_page = t_total_pages
            t_offset = (t_page - 1) * t_limit

        transfer_history = request.env['vehicle.transfer.request'].sudo().search(
            history_transfer_domain, order='date_accepted desc, write_date desc', limit=t_limit, offset=t_offset
        )

        # สร้างรายการปุ่มลิงก์ Pagination ประวัติการโยกย้ายโดยรักษาพารามิเตอร์อื่นๆ ไว้ (ภาษาไทยคอมเมนต์)
        t_pages_list = []
        for p in range(1, t_total_pages + 1):
            params = post.copy()
            params['t_page'] = p
            params = {k: v for k, v in params.items() if v}
            t_pages_list.append({
                'num': p,
                'url': '/automotive/dashboard?' + urlencode(params),
                'is_current': p == t_page
            })

        t_prev_page_url = None
        if t_page > 1:
            params = post.copy()
            params['t_page'] = t_page - 1
            params = {k: v for k, v in params.items() if v}
            t_prev_page_url = '/automotive/dashboard?' + urlencode(params)

        t_next_page_url = None
        if t_page < t_total_pages:
            params = post.copy()
            params['t_page'] = t_page + 1
            params = {k: v for k, v in params.items() if v}
            t_next_page_url = '/automotive/dashboard?' + urlencode(params)

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
            # ส่งตัวแปรสำหรับแบ่งหน้ารถยนต์ไปยังหน้ากาก (ภาษาไทยคอมเมนต์)
            'v_page': v_page,
            'v_total_pages': v_total_pages,
            'v_total_count': v_total_count,
            'v_pages_list': v_pages_list,
            'v_prev_page_url': v_prev_page_url,
            'v_next_page_url': v_next_page_url,
            # ส่งตัวแปรสำหรับแบ่งหน้าพนักงานไปยังหน้ากาก (ภาษาไทยคอมเมนต์)
            'u_page': u_page,
            'u_total_pages': u_total_pages,
            'u_total_count': u_total_count,
            'u_pages_list': u_pages_list,
            'u_prev_page_url': u_prev_page_url,
            'u_next_page_url': u_next_page_url,
            # ส่งตัวแปรสำหรับแบ่งหน้าประวัติการโยกย้ายไปยังหน้ากาก (ภาษาไทยคอมเมนต์)
            't_page': t_page,
            't_total_pages': t_total_pages,
            't_total_count': t_total_count,
            't_pages_list': t_pages_list,
            't_prev_page_url': t_prev_page_url,
            't_next_page_url': t_next_page_url,
        })

    @http.route(['/automotive/member/add'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_member_add(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        try:
            name = post.get('name')
            login = post.get('login')
            password = post.get('password')
            role = post.get('role')  # 'user', 'head_admin', 'admin_tqs', 'admin_ckr', 'admin_tps'
            
            # สร้าง User (เปลี่ยนเป็น group_ids เพื่อความเข้ากันได้กับ Odoo 19)
            new_user = request.env['res.users'].sudo().create({
                'name': name,
                'login': login,
                'password': password,
                'group_ids': [(6, 0, [request.env.ref('base.group_user').id])]
            })
            
            # กำหนด group ตาม role ที่เลือก (รองรับบทบาท 'user' ที่ต้องเข้าถึงได้ทุกโรงงานโดยการเพิ่มเข้าไปในทุกกลุ่มของพนักงาน)
            group_map = {
                'head_admin': ['vehicle_borrow.group_vb_head_admin'],
                'admin_tqs': ['vehicle_borrow.group_vb_admin_tqs'],
                'admin_ckr': ['vehicle_borrow.group_vb_admin_ckr'],
                'admin_tps': ['vehicle_borrow.group_vb_admin_tps'],
                'user_tqs': ['vehicle_borrow.group_vb_user_tqs'],
                'user_ckr': ['vehicle_borrow.group_vb_user_ckr'],
                'user_tps': ['vehicle_borrow.group_vb_user_tps'],
                'user': [
                    'vehicle_borrow.group_vb_user_tqs',
                    'vehicle_borrow.group_vb_user_ckr',
                    'vehicle_borrow.group_vb_user_tps'
                ],
            }
            if role in group_map:
                for group_xmlid in group_map[role]:
                    group = request.env.ref(group_xmlid)
                    # อัปเดตกลุ่มสิทธิ์ผู้ใช้เป็น group_ids ตามมาตรฐาน Odoo 19
                    new_user.sudo().write({'group_ids': [(4, group.id)]})
                
            # วิเคราะห์โรงงานของพนักงานตามสิทธิ์ที่เลือก
            emp_factory = False
            if role:
                if 'tqs' in role:
                    emp_factory = 'TQS'
                elif 'ckr' in role:
                    emp_factory = 'CKR'
                elif 'tps' in role:
                    emp_factory = 'TPS'

            # สร้าง Employee (ถ้ายังไม่มี) พร้อมส่งค่าสิทธิ์และโรงงาน เพื่อให้ Odoo ซิงค์ข้อมูลเข้ากลุ่ม res.users อัตโนมัติ
            request.env['hr.employee'].sudo().create({
                'name': name,
                'user_id': new_user.id,
                'vehicle_borrow_role': role or 'none',
                'factory': emp_factory,
            })
            
            return request.redirect('/automotive/dashboard?msg=member_added')
        except Exception as e:
            return request.redirect("/automotive/dashboard?error=" + str(e))

    @http.route(['/automotive/member/delete/<int:user_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_member_delete(self, user_id, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        if user_id == request.env.user.id or user_id == 1:
            return request.redirect('/automotive/dashboard?error=ไม่สามารถลบบัญชีของตัวเองหรือ Admin หลักได้')
        
        user = request.env['res.users'].sudo().browse(user_id)
        if not user.exists():
            return request.redirect('/automotive/dashboard?error=ไม่พบผู้ใช้งานนี้ในระบบ')
        
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
        
        return request.redirect('/automotive/dashboard?msg=member_deleted')

    # รองรับทั้ง URL /automotive และ /admin เพื่อป้องกันปัญหา Error 404
    @http.route([
        '/automotive/member/role/<int:user_id>/<string:role>',
        '/admin/member/role/<int:user_id>/<string:role>'
    ], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_member_role(self, user_id, role, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        try:
            # ค้นหาพนักงานที่ผูกกับ User ID นี้เพื่อเปลี่ยนสิทธิ์และโรงงาน
            employee = request.env['hr.employee'].sudo().search([('user_id', '=', user_id)], limit=1)
            
            # วิเคราะห์โรงงานของพนักงานตามสิทธิ์ที่ต้องการเปลี่ยน
            emp_factory = False
            if role:
                if 'tqs' in role:
                    emp_factory = 'TQS'
                elif 'ckr' in role:
                    emp_factory = 'CKR'
                elif 'tps' in role:
                    emp_factory = 'TPS'

            if employee:
                # เขียนค่าสิทธิ์และโรงงานลงใน Employee ซึ่งจะทริกเกอร์ _sync_user_groups() เพื่อซิงค์ไป res.users อัตโนมัติ
                employee.sudo().write({
                    'vehicle_borrow_role': role,
                    'factory': emp_factory
                })
            else:
                # กรณีฉุกเฉินถ้าไม่มี Employee ผูกอยู่ ให้ทำการสร้าง Employee ใหม่พร้อมระบุสิทธิ์และโรงงาน
                user = request.env['res.users'].sudo().browse(user_id)
                if user.exists():
                    request.env['hr.employee'].sudo().create({
                        'name': user.name,
                        'user_id': user.id,
                        'vehicle_borrow_role': role,
                        'factory': emp_factory
                    })
                
            return request.redirect('/automotive/dashboard?msg=role_updated')
        except Exception as e:
            return request.redirect("/automotive/dashboard?error=" + str(e))

    # รองรับทั้ง URL /automotive และ /admin เพื่อป้องกันปัญหา Error 404
    @http.route([
        '/automotive/member/status/<int:user_id>/<string:status>',
        '/admin/member/status/<int:user_id>/<string:status>'
    ], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_member_status(self, user_id, status, **post):
        if not self._is_admin():
            return request.render("http_routing.403")

        try:
            user = request.env['res.users'].sudo().with_context(active_test=False).browse(user_id)
            if user.exists():
                active_val = True if status == 'active' else False
                user.sudo().write({'active': active_val})
                return request.redirect('/automotive/dashboard?msg=status_updated')
        except Exception as e:
            return request.redirect("/automotive/dashboard?error=" + str(e))
        return request.redirect('/automotive/dashboard')

    @http.route(['/automotive/add'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_vehicle_add(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        try:
            model_name = post.get('model_name')
            if not model_name:
                return request.redirect('/automotive/dashboard?error=Missing model name')

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
            return request.redirect('/automotive/dashboard?msg=vehicle_added&type=%s' % model_name)
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error("Error adding vehicle: %s", str(e))
            return request.redirect("/automotive/dashboard?error=" + str(e))

    @http.route(['/automotive/edit'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_vehicle_edit(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        try:
            vehicle_id = post.get('vehicle_id')
            license_plate = post.get('license_plate')
            
            vehicle = request.env['fleet.vehicle'].sudo().browse(int(vehicle_id))
            if not vehicle.exists():
                return request.redirect('/automotive/dashboard?error=ไม่พบรถยนต์ที่ต้องการแก้ไข')

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
            return request.redirect('/automotive/dashboard?msg=vehicle_updated')
        except Exception as e:
            return request.redirect("/automotive/dashboard?error=" + str(e))

    # รองรับทั้ง URL /automotive และ /admin เพื่อป้องกันปัญหา Error 404
    @http.route([
        '/automotive/status/<int:vehicle_id>/<string:status>',
        '/admin/vehicle/status/<int:vehicle_id>/<string:status>'
    ], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_vehicle_status(self, vehicle_id, status, **post):
        if not self._is_admin():
            return request.render("http_routing.403")

        try:
            vehicle = request.env['fleet.vehicle'].sudo().browse(vehicle_id)
            if vehicle.exists():
                vehicle.sudo().write({'vehicle_status': status})
                return request.redirect('/automotive/dashboard?msg=status_updated')
        except Exception as e:
            return request.redirect("/automotive/dashboard?error=" + str(e))
        return request.redirect('/automotive/dashboard')

    @http.route(['/automotive/setup/init-vehicles'], type='http', auth="user", website=True)
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
        
        return request.redirect('/automotive/dashboard?msg=setup_completed')
        


    @http.route(['/automotive/bookings'], type='http', auth="user", website=True)
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

    def _get_usages_domain(self, user_factory, **post):
        """
        ฟังก์ชันผู้ช่วยสำหรับสร้าง Domain กรองข้อมูลประวัติการจองและใช้งานรถยนต์แบบละเอียด
        """
        domain = []
        
        # 1. กรองสิทธิ์ตามโรงงานที่แอดมินดูแล
        if user_factory:
            domain.append(('vehicle_id.factory', '=', user_factory))
        elif post.get('filter_factory') and post.get('filter_factory') != 'all':
            domain.append(('vehicle_id.factory', '=', post.get('filter_factory')))
            
        # 2. ค้นหาคำสำคัญ (เลขที่คำขอ, พนักงาน, ยานพาหนะ, ทะเบียน)
        search_text = post.get('search_text', '').strip()
        if search_text:
            domain.extend(['|', '|', '|',
                           ('name', 'ilike', search_text),
                           ('employee_id.name', 'ilike', search_text),
                           ('vehicle_id.name', 'ilike', search_text),
                           ('vehicle_id.license_plate', 'ilike', search_text)])
            
        # 3. ตัวกรองสถานะ
        filter_state = post.get('filter_state', 'all')
        if filter_state == 'active':
            # รายการที่กำลังใช้งานอยู่ (จองใหม่, อนุมัติแล้ว, ยืมแล้ว)
            domain.append(('state', 'in', ['request', 'approved', 'borrowed']))
        elif filter_state and filter_state != 'all':
            domain.append(('state', '=', filter_state))
            
        # 4. ตัวกรองประเภทรถยนต์ (f_type)
        filter_type = post.get('f_type')
        if filter_type:
            domain.append(('vehicle_id.model_id.name', '=', filter_type))
            
        # 5. ตัวกรองยานพาหนะรายคัน (f_vehicle_id)
        filter_vehicle_id = post.get('f_vehicle_id')
        if filter_vehicle_id:
            try:
                domain.append(('vehicle_id', '=', int(filter_vehicle_id)))
            except ValueError:
                pass

        # 6. ตัวกรองช่วงวันที่เริ่มยืม (f_start_date - f_start_date_end)
        f_start_date = post.get('f_start_date')
        if f_start_date:
            domain.append(('date_start', '>=', f_start_date + ' 00:00:00'))
        f_start_date_end = post.get('f_start_date_end')
        if f_start_date_end:
            domain.append(('date_start', '<=', f_start_date_end + ' 23:59:59'))
            
        # 7. ตัวกรองช่วงวันที่คืนรถ (f_end_date - f_end_date_end)
        f_end_date = post.get('f_end_date')
        if f_end_date:
            domain.append(('date_end', '>=', f_end_date + ' 00:00:00'))
        f_end_date_end = post.get('f_end_date_end')
        if f_end_date_end:
            domain.append(('date_end', '<=', f_end_date_end + ' 23:59:59'))
            
        return domain

    @http.route(['/automotive/admin/usages'], type='http', auth="user", website=True)
    def admin_active_usages(self, **post):
        """
        หน้าจอผู้ดูแลระบบสำหรับตรวจสอบประวัติและการใช้งานรถยนต์ทั้งหมดในระบบ (All Usages & History)
        แสดงทั้งรายการที่กำลังใช้งานอยู่ในปัจจุบัน และรายการจองย้อนหลังทั้งหมดในอดีต พร้อมระบบตัวกรองแบบสอดคล้องกับระบบแจ้งซ่อม
        """
        if not self._is_admin():
            return request.render("http_routing.403")
        
        env_sudo = request.env(su=True)
        user_factory = self._get_user_factory() # ตรวจหาโรงงานที่สังกัดของแอดมินคนนี้
        
        # นำเข้าไลบรารีคณิตศาสตร์และการเข้ารหัส URL สำหรับทำ Pagination (ภาษาไทยคอมเมนต์)
        import math
        from urllib.parse import urlencode

        # ดึงหน้าปัจจุบันและตรวจสอบความถูกต้องของค่าหน้า (ภาษาไทยคอมเมนต์)
        try:
            page = int(post.get('page', 1))
        except (ValueError, TypeError):
            page = 1
        if page < 1:
            page = 1

        # กำหนดจำนวนแสดงผลสูงสุด 20 รายการต่อหน้า (ภาษาไทยคอมเมนต์)
        limit = 20
        offset = (page - 1) * limit

        # ดึงข้อมูลประวัติการจองยืมรถยนต์ทั้งหมดตามสาขาโรงงานที่แอดมินดูแลพร้อมฟิลเตอร์ (ภาษาไทยคอมเมนต์)
        domain = self._get_usages_domain(user_factory, **post)
        
        # นับจำนวนรายการทั้งหมดตามเงื่อนไขตัวกรองเพื่อคำนวณจำนวนหน้า (ภาษาไทยคอมเมนต์)
        total_count = env_sudo['vehicle.borrow.request'].search_count(domain)
        total_pages = math.ceil(total_count / limit) or 1

        # ป้องกันกรณีระบุหน้าเกินหน้าสูงสุดที่มีจริง (ภาษาไทยคอมเมนต์)
        if page > total_pages:
            page = total_pages
            offset = (page - 1) * limit

        # ดึงข้อมูลรายการเฉพาะหน้านั้นๆ (จำกัด 20 รายการ) (ภาษาไทยคอมเมนต์)
        borrow_requests = env_sudo['vehicle.borrow.request'].search(
            domain, order='date_start desc', limit=limit, offset=offset
        )
        
        # สร้างลิงก์สำหรับแต่ละหน้า โดยคัดลอกพารามิเตอร์ของตัวกรองเดิมเพื่อรักษาฟิลเตอร์ไว้ (ภาษาไทยคอมเมนต์)
        pages_list = []
        for p in range(1, total_pages + 1):
            params = post.copy()
            params['page'] = p
            # ตัดฟิลด์ที่ค่าว่างเปล่าออกเพื่อลดความยาวของ URL query string (ภาษาไทยคอมเมนต์)
            params = {k: v for k, v in params.items() if v}
            pages_list.append({
                'num': p,
                'url': '/automotive/admin/usages?' + urlencode(params),
                'is_current': p == page
            })

        # ลิงก์สำหรับปุ่มหน้าก่อนหน้า (Previous Page) (ภาษาไทยคอมเมนต์)
        prev_page_url = None
        if page > 1:
            params = post.copy()
            params['page'] = page - 1
            params = {k: v for k, v in params.items() if v}
            prev_page_url = '/automotive/admin/usages?' + urlencode(params)

        # ลิงก์สำหรับปุ่มหน้าถัดไป (Next Page) (ภาษาไทยคอมเมนต์)
        next_page_url = None
        if page < total_pages:
            params = post.copy()
            params['page'] = page + 1
            params = {k: v for k, v in params.items() if v}
            next_page_url = '/automotive/admin/usages?' + urlencode(params)

        # ดึงรายชื่อรถยนต์และประเภทรถยนต์สำหรับแสดงผลในตัวเลือก Filter Dropdown (ภาษาไทยคอมเมนต์)
        v_domain = [('factory', '=', user_factory)] if user_factory else []
        vehicles = env_sudo['fleet.vehicle'].search(v_domain, order='name asc')
        vehicle_types = sorted(list(set([v.model_id.name for v in vehicles if v.model_id and v.model_id.name])))
        
        return request.render("vehicle_borrow.admin_active_usages_template", {
            'requests': borrow_requests,
            'user_factory': user_factory or 'ทั้งหมด',
            'is_super_admin': not user_factory,
            'vehicles': vehicles,
            'vehicle_types': vehicle_types,
            'search_text': post.get('search_text', ''),
            'filter_state': post.get('filter_state', 'all'),
            'filter_factory': post.get('filter_factory', 'all'),
            'filter_type': post.get('f_type', ''),
            'filter_vehicle_id': post.get('f_vehicle_id', ''),
            'filter_start_date': post.get('f_start_date', ''),
            'filter_start_date_end': post.get('f_start_date_end', ''),
            'filter_end_date': post.get('f_end_date', ''),
            'filter_end_date_end': post.get('f_end_date_end', ''),
            # ส่งตัวแปร Pagination ไปยัง QWeb Template (ภาษาไทยคอมเมนต์)
            'page': page,
            'total_pages': total_pages,
            'total_count': total_count,
            'pages_list': pages_list,
            'prev_page_url': prev_page_url,
            'next_page_url': next_page_url,
        })

    @http.route(['/automotive/admin/usages/export'], type='http', auth="user", methods=['POST', 'GET'], website=True, csrf=False)
    def admin_active_usages_export(self, **post):
        """
        เมธอดสำหรับส่งออกประวัติการยืมรถยนต์ออกมาเป็นไฟล์ Excel (.xlsx) ตามตัวกรองที่มีความปลอดภัยและสวยงาม
        """
        if not self._is_admin():
            return request.render("http_routing.403")
            
        env_sudo = request.env(su=True)
        user_factory = self._get_user_factory()
        
        # ดึงข้อมูลตามฟิลเตอร์เดียวกัน
        domain = self._get_usages_domain(user_factory, **post)
        borrow_requests = env_sudo['vehicle.borrow.request'].search(domain, order='date_start desc')
        
        import io
        import xlsxwriter
        from odoo import fields
        
        # สร้าง Workbook ในหน่วยความจำ
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('ประวัติการใช้งานรถยนต์')
        
        # กำหนดสไตล์ความสวยงามระดับพรีเมียม (สีน้ำเงินเข้มตาม Odoo/Bootstrap)
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'align': 'center',
            'valign': 'vcenter',
            'font_name': 'Tahoma'
        })
        header_format = workbook.add_format({
            'bold': True,
            'font_size': 10,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#1e293b',
            'font_color': '#ffffff',
            'border': 1,
            'border_color': '#cbd5e1',
            'font_name': 'Tahoma'
        })
        cell_format = workbook.add_format({
            'font_size': 10,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'border_color': '#e2e8f0',
            'font_name': 'Tahoma'
        })
        cell_center_format = workbook.add_format({
            'font_size': 10,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'border_color': '#e2e8f0',
            'font_name': 'Tahoma'
        })
        
        # กำหนดความกว้างคอลัมน์ให้สมมาตรอ่านง่าย
        worksheet.set_column('A:A', 22) # เลขที่คำขอ
        worksheet.set_column('B:B', 20) # ผู้ยืมรถ
        worksheet.set_column('C:C', 18) # แผนก/ตำแหน่ง
        worksheet.set_column('D:D', 30) # ยานพาหนะ
        worksheet.set_column('E:E', 15) # ทะเบียน
        worksheet.set_column('F:F', 12) # โรงงาน
        worksheet.set_column('G:G', 25) # จุดประสงค์
        worksheet.set_column('H:H', 20) # วันที่เริ่มยืม
        worksheet.set_column('I:I', 20) # วันที่คืนรถ
        worksheet.set_column('J:J', 15) # สถานะ
        
        # ตั้งความสูงแถวหัวเรื่อง
        worksheet.set_row(0, 40)
        worksheet.set_row(1, 28)
        
        # เขียนหัวข้อรายงาน
        factory_title = f" ({user_factory})" if user_factory else " (ทั้งหมด)"
        worksheet.merge_range('A1:J1', f'รายงานประวัติการจองและใช้งานรถยนต์ทั้งหมด{factory_title}', title_format)
        
        # เขียนคอลัมน์หัวตาราง
        headers = [
            'เลขที่คำขอ', 'ผู้ยืมรถ', 'แผนก/ตำแหน่ง', 'ยานพาหนะ', 
            'ทะเบียน', 'โรงงาน', 'จุดประสงค์การใช้งาน', 'วันที่เริ่มยืม', 
            'วันที่คืนรถ', 'สถานะ'
        ]
        for col_num, header in enumerate(headers):
            worksheet.write(1, col_num, header, header_format)
            
        # วนลูปบันทึกแถวข้อมูลดิบ
        row_num = 2
        state_mapping = {
            'draft': 'ฉบับร่าง',
            'request': 'กำลังใช้งาน',
            'approved': 'อนุมัติแล้ว',
            'borrowed': 'กำลังใช้งาน',
            'returned': 'คืนรถแล้ว',
            'cancelled': 'ยกเลิก'
        }
        
        for req in borrow_requests:
            worksheet.set_row(row_num, 22)
            
            date_start_str = str(req.date_start)[:16] if req.date_start else '-'
            date_end_str = str(req.date_end)[:16] if req.date_end else 'ยังไม่คืน'
            state_label = state_mapping.get(req.state, req.state or '-')
            
            worksheet.write(row_num, 0, req.name or '-', cell_center_format)
            worksheet.write(row_num, 1, req.employee_id.name or '-', cell_format)
            worksheet.write(row_num, 2, req.employee_id.department_id.name if req.employee_id.department_id else 'พนักงาน', cell_format)
            worksheet.write(row_num, 3, req.vehicle_id.name or '-', cell_format)
            worksheet.write(row_num, 4, req.vehicle_id.license_plate or '-', cell_center_format)
            worksheet.write(row_num, 5, req.vehicle_id.factory or 'ทั่วไป', cell_center_format)
            worksheet.write(row_num, 6, req.purpose or '-', cell_format)
            worksheet.write(row_num, 7, date_start_str, cell_center_format)
            worksheet.write(row_num, 8, date_end_str, cell_center_format)
            worksheet.write(row_num, 9, state_label, cell_center_format)
            
            row_num += 1
            
        workbook.close()
        output.seek(0)
        
        # สร้าง HTTP Response ส่งกลับพร้อมแนบไฟล์ Excel
        filename = f"vehicle_usages_report_{fields.Date.today()}.xlsx"
        response = request.make_response(
            output.getvalue(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', f'attachment; filename={filename}')
            ]
        )
        return response

    @http.route(['/automotive/admin/return/<int:req_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_vehicle_return(self, req_id, **post):
        """
        ปุ่มสำหรับผู้ดูแลระบบ (Admin) กดคืนรถแทนผู้ใช้งานในกรณีที่ผู้ใช้งานลืมกดคืนในระบบ
        """
        if not self._is_admin():
            return request.render("http_routing.403")
        
        from odoo import fields
        borrow = request.env['vehicle.borrow.request'].sudo().browse(req_id)
        # ปรับปรุงให้รองรับการกดคืนรถแทนพนักงานในสถานะ request (กำลังใช้งาน) นอกเหนือจาก approved และ borrowed
        if borrow.exists() and borrow.state in ['request', 'approved', 'borrowed']:
            borrow.sudo().write({
                'state': 'returned',
                'date_end': fields.Datetime.now(),
            })
            
        return request.redirect('/automotive/admin/usages?msg=returned')

    @http.route(['/automotive/delete/<int:vehicle_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_vehicle_delete(self, vehicle_id, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        try:
            vehicle = request.env['fleet.vehicle'].sudo().browse(vehicle_id)
            if vehicle.exists():
                vehicle.sudo().unlink()
            return request.redirect('/automotive/dashboard?msg=vehicle_deleted')
        except Exception as e:
            return request.redirect("/automotive/dashboard?error=" + str(e))

    @http.route(['/automotive/booking/delete/<int:req_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_booking_delete(self, req_id, **post):
        """
        เมธอดสำหรับลบประวัติการจองและใช้งานรถยนต์โดยผู้ดูแลระบบ (ภาษาไทยคอมเมนต์)
        """
        if not self._is_admin():
            return request.render("http_routing.403")
        
        # ดึงลิงก์ปลายทางในการ Redirect หากไม่มีให้กลับไปยังหน้าประวัติหลัก (ภาษาไทยคอมเมนต์)
        redirect_url = post.get('redirect_url', '/automotive/admin/usages')
        try:
            req = request.env['vehicle.borrow.request'].sudo().browse(req_id)
            if req.exists():
                req.sudo().unlink()
            return request.redirect(f'{redirect_url}?msg=booking_deleted')
        except Exception as e:
            return request.redirect(f'{redirect_url}?error=' + str(e))

    @http.route(['/automotive/setup/list-vehicles'], type='http', auth="user", website=True)
    def admin_list_vehicles(self, **post):
        if not self._is_admin(): return request.render("http_routing.403")
        vehicles = request.env['fleet.vehicle'].sudo().search([])
        output = "Vehicle List (ID - Name - Status):<br/>"
        for v in vehicles:
            output += f"{v.id} - {v.license_plate} - {'Active' if v.active else 'Archived'} - Image: {'Yes' if v.image_128 else 'No'}<br/>"
        return output

    @http.route(['/automotive/setup/delete-vehicle-by-name'], type='http', auth="user", website=True)
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
                   f"<a href='/automotive/setup/list-vehicles' class='btn btn-primary'>กลับไปดูรายการทั้งหมด</a>"

        try:
            v.unlink()
            return f"Successfully deleted vehicle named '{name}'."
        except Exception as e:
            return f"Error while trying to unlink: {str(e)}"

    @http.route(['/automotive/setup/force-delete-vehicle'], type='http', auth="user", website=True)
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
               f"<a href='/automotive/dashboard' class='btn btn-success'>กลับสู่ Dashboard</a>"

    @http.route(['/automotive/repair'], type='http', auth="user", website=True)
    def admin_repair_page(self, **post):
        # หน้าหลักสำหรับจัดการการแจ้งซ่อมและใบงานที่กำลังดำเนินการ (รายการแจ้งซ่อม)
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

        # ดึงข้อมูลรายการรถและประเภทรถ โดยแสดงเฉพาะประเภทที่มีตัวรถจริงและสถานะ Active ในโรงงาน
        vehicles = env_sudo['fleet.vehicle'].search(list(factory_domain) + [('active', '=', True)])
        vehicle_types = sorted(list(set([v.model_id.name for v in vehicles if v.model_id and v.model_id.name])))
        
        # รายการแจ้งซ่อมที่ส่งเข้ามาใหม่และอยู่ระหว่างรอตรวจสอบ (รอช่างตรวจเช็ค)
        pending_repairs = env_sudo['vehicle.repair.request'].search(
            list(repair_factory_domain) + [('state', '=', 'reported')], 
            limit=50, 
            order='create_date desc'
        )
        
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
            'pending_repairs': pending_repairs,
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

    @http.route(['/automotive/repair/latest'], type='http', auth="user", website=True)
    def admin_repair_latest_page(self, **post):
        # หน้าสำหรับจัดการการแจ้งซ่อมล่าสุด (10 รายการ) ที่กำลังดำเนินการซ่อม
        if not self._is_admin():
            return request.render("http_routing.403")
            
        current_user = request.env.user
        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', current_user.id)], limit=1
        )
        
        env_sudo = request.env(su=True)
        user_factory = self._get_user_factory()
        repair_factory_domain = [('vehicle_id.factory', '=', user_factory)] if user_factory else []

        # ดึงรายการซ่อมที่ได้รับอนุมัติและกำลังดำเนินการซ่อมอยู่ (state = 'repairing') จำกัดการแสดงผลไว้ที่ 10 รายการล่าสุด
        recent_repairs = env_sudo['vehicle.repair.request'].search(
            list(repair_factory_domain) + [('state', '=', 'repairing')], 
            limit=10, 
            order='create_date desc'
        )
        
        # ดึงกลุ่มสิทธิ์ระดับต่างๆ เพื่อส่งไปจัดการสิทธิ์และแสดงผล Badge บนหน้าต่าง Template
        head_admin_group = request.env.ref('vehicle_borrow.group_vb_head_admin')
        admin_tqs_group = request.env.ref('vehicle_borrow.group_vb_admin_tqs')
        admin_ckr_group = request.env.ref('vehicle_borrow.group_vb_admin_ckr')
        admin_tps_group = request.env.ref('vehicle_borrow.group_vb_admin_tps')
        user_tqs_group = request.env.ref('vehicle_borrow.group_vb_user_tqs')
        user_ckr_group = request.env.ref('vehicle_borrow.group_vb_user_ckr')
        user_tps_group = request.env.ref('vehicle_borrow.group_vb_user_tps')

        return request.render("vehicle_borrow.admin_repair_latest_template", {
            'current_employee': employee,
            'recent_repairs': recent_repairs,
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

    @http.route(['/automotive/repair/approve/<int:repair_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_repair_approve(self, repair_id, **post):
        # ฟังก์ชันสำหรับอนุมัติซ่อมและเปลี่ยนสถานะรถยนต์เป็นกำลังซ่อม (ล็อกการจอง)
        if not self._is_admin():
            return request.render("http_routing.403")
            
        repair = request.env['vehicle.repair.request'].sudo().browse(repair_id)
        if repair.exists():
            # เรียกใช้ฟังก์ชันอนุมัติซ่อมในโมเดลเพื่อล็อกรถยนต์และปรับเป็นสถานะกำลังซ่อม
            repair.action_approve()
            # ส่งผู้ใช้งานกลับไปที่หน้าเดิมพร้อมส่งข้อความแจ้งเตือนผลลัพธ์
            redirect_url = request.httprequest.referrer or '/automotive/repair/latest'
            if '?' in redirect_url:
                redirect_url += "&msg=repair_approved"
            else:
                redirect_url += "?msg=repair_approved"
            return request.redirect(redirect_url)
        return request.redirect('/automotive/repair/latest?error=ไม่พบรายการแจ้งซ่อม')

    @http.route(['/automotive/repair/cancel/<int:repair_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_repair_cancel(self, repair_id, **post):
        # ฟังก์ชันสำหรับยกเลิกใบแจ้งซ่อม
        if not self._is_admin():
            return request.render("http_routing.403")
            
        repair = request.env['vehicle.repair.request'].sudo().browse(repair_id)
        if repair.exists():
            # เรียกใช้ฟังก์ชันยกเลิกในโมเดลเพื่อเปลี่ยนสถานะเป็นยกเลิก (และคืนสถานะรถเป็น active หากมี)
            repair.action_cancel()
            redirect_url = request.httprequest.referrer or '/automotive/repair/latest'
            if '?' in redirect_url:
                redirect_url += "&msg=repair_cancelled"
            else:
                redirect_url += "?msg=repair_cancelled"
            return request.redirect(redirect_url)
        return request.redirect('/automotive/repair/latest?error=ไม่พบรายการแจ้งซ่อม')

    @http.route(['/automotive/repair/history'], type='http', auth="user", website=True)
    def admin_repair_history_page(self, **post):
        # หน้าแสดงประวัติการซ่อมบำรุงรถยนต์ทั้งหมดที่เสร็จสิ้นหรือยกเลิกแล้ว (ประวัติการซ่อม)
        if not self._is_admin():
            return request.render("http_routing.403")
            
        env_sudo = request.env(su=True)
        user_factory = self._get_user_factory()
        factory_domain = [('factory', '=', user_factory)] if user_factory else []
        repair_factory_domain = [('vehicle_id.factory', '=', user_factory)] if user_factory else []

        # ประวัติการซ่อมที่มีสถานะเสร็จสิ้น (done) หรือยกเลิก (cancelled)
        history_domain = list(repair_factory_domain) + [('state', 'in', ['done', 'cancelled'])]
        
        # คัดกรองข้อมูลประวัติตามฟิลเตอร์
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
            
        # คำนวณแบ่งหน้า (Pagination) หน้าละ 20 รายการ (คอมเมนต์ภาษาไทย)
        import math
        from urllib.parse import urlencode

        limit = 20
        page = int(post.get('page', 1))
        if page < 1:
            page = 1

        total_count = env_sudo['vehicle.repair.request'].search_count(history_domain)
        total_pages = math.ceil(total_count / limit) if total_count > 0 else 1

        if page > total_pages:
            page = total_pages

        offset = (page - 1) * limit
        repair_history = env_sudo['vehicle.repair.request'].search(
            history_domain, 
            order='finish_date desc, id desc',
            limit=limit,
            offset=offset
        )

        # สร้างรายการลิงก์สลับหน้า (Pagination Links) โดยรักษาฟิลเตอร์เดิมไว้ (คอมเมนต์ภาษาไทย)
        params = {k: v for k, v in post.items() if k != 'page'}
        pages_list = []
        for p in range(max(1, page - 3), min(total_pages, page + 3) + 1):
            params['page'] = p
            pages_list.append({
                'num': p,
                'url': '/automotive/repair/history?' + urlencode(params),
                'is_current': p == page
            })

        prev_page_url = None
        if page > 1:
            params['page'] = page - 1
            prev_page_url = '/automotive/repair/history?' + urlencode(params)

        next_page_url = None
        if page < total_pages:
            params['page'] = page + 1
            next_page_url = '/automotive/repair/history?' + urlencode(params)

        # รายการรถทั้งหมดในโรงงานสำหรับฟิลเตอร์
        all_vehicles_history = env_sudo['fleet.vehicle'].search(factory_domain)
        
        # ประเภทรถทั้งหมดสำหรับตัวกรอง (กรองให้แสดงเฉพาะประเภทที่มีรถจริงตามสิทธิ์โรงงาน)
        vehicle_types = sorted(list(set([v.model_id.name for v in all_vehicles_history if v.model_id and v.model_id.name])))
        
        # ดึงกลุ่มสิทธิ์สำหรับแสดง Badge ใน Template
        head_admin_group = request.env.ref('vehicle_borrow.group_vb_head_admin')
        admin_tqs_group = request.env.ref('vehicle_borrow.group_vb_admin_tqs')
        admin_ckr_group = request.env.ref('vehicle_borrow.group_vb_admin_ckr')
        admin_tps_group = request.env.ref('vehicle_borrow.group_vb_admin_tps')
        user_tqs_group = request.env.ref('vehicle_borrow.group_vb_user_tqs')
        user_ckr_group = request.env.ref('vehicle_borrow.group_vb_user_ckr')
        user_tps_group = request.env.ref('vehicle_borrow.group_vb_user_tps')

        return request.render("vehicle_borrow.admin_repair_history_list_template", {
            'repair_history': repair_history,
            'page': page,
            'total_pages': total_pages,
            'total_count': total_count,
            'pages_list': pages_list,
            'prev_page_url': prev_page_url,
            'next_page_url': next_page_url,
            'all_vehicles_history': all_vehicles_history,
            'vehicle_types': vehicle_types,
            'filters': post, # รักษาฟิลเตอร์ที่ผู้ใช้กรองไว้
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

    @http.route(['/automotive/repair/history/export'], type='http', auth="user", website=True)
    def admin_repair_history_export(self, **post):
        # ฟังก์ชันตรวจสอบสิทธิ์แอดมิน
        if not self._is_admin():
            return request.render("http_routing.403")
            
        env_sudo = request.env(su=True)
        user_factory = self._get_user_factory()
        
        # คัดกรองข้อมูลประวัติตามสิทธิ์ของโรงงาน
        repair_factory_domain = [('vehicle_id.factory', '=', user_factory)] if user_factory else []
        history_domain = list(repair_factory_domain) + [('state', 'in', ['done', 'cancelled'])]
        
        # คัดกรองข้อมูลเพิ่มเติมตามตัวกรองที่ส่งมาจาก Form ค้นหา
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
            
        repair_history = env_sudo['vehicle.repair.request'].search(history_domain, order='finish_date desc, id desc')
        
        import io
        import xlsxwriter
        from datetime import datetime
        
        # เตรียม Buffer เขียนข้อมูลตาราง Excel
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('ประวัติการซ่อมบำรุง')
        
        worksheet.hide_gridlines(0)
        
        # กำหนดสไตล์และรูปแบบสีตารางให้สวยงาม
        title_format = workbook.add_format({
            'bold': True, 'font_size': 16, 'font_name': 'Cordia New', 'font_color': '#1F4E79', 'align': 'left', 'valign': 'vcenter'
        })
        meta_format = workbook.add_format({
            'font_size': 11, 'font_name': 'Cordia New', 'font_color': '#595959', 'align': 'left'
        })
        header_format = workbook.add_format({
            'bold': True, 'font_size': 12, 'font_name': 'Cordia New', 'font_color': '#FFFFFF', 'bg_color': '#1F4E79',
            'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#D9D9D9'
        })
        
        cell_white = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'border': 1, 'border_color': '#E0E0E0', 'valign': 'vcenter'})
        cell_zebra = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'bg_color': '#F9FBFD', 'border': 1, 'border_color': '#E0E0E0', 'valign': 'vcenter'})
        
        align_center_white = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#E0E0E0'})
        align_center_zebra = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'align': 'center', 'valign': 'vcenter', 'bg_color': '#F9FBFD', 'border': 1, 'border_color': '#E0E0E0'})
        
        price_right_white = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'align': 'right', 'valign': 'vcenter', 'border': 1, 'border_color': '#E0E0E0', 'num_format': '฿#,##0.00'})
        price_right_zebra = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'align': 'right', 'valign': 'vcenter', 'bg_color': '#F9FBFD', 'border': 1, 'border_color': '#E0E0E0', 'num_format': '฿#,##0.00'})
        
        state_done = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'font_color': '#1E4620', 'bg_color': '#D1E7DD', 'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#E0E0E0'})
        state_cancel = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'font_color': '#842029', 'bg_color': '#F8D7DA', 'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#E0E0E0'})
        
        total_format = workbook.add_format({'bold': True, 'font_size': 12, 'font_name': 'Cordia New', 'bg_color': '#EAEAEA', 'border': 1, 'border_color': '#A6A6A6', 'align': 'right', 'valign': 'vcenter', 'num_format': '฿#,##0.00'})
        total_label_format = workbook.add_format({'bold': True, 'font_size': 12, 'font_name': 'Cordia New', 'bg_color': '#EAEAEA', 'border': 1, 'border_color': '#A6A6A6', 'align': 'center', 'valign': 'vcenter'})
        
        # เขียนหัวข้อหลักรายงาน
        worksheet.write('A1', 'รายงานประวัติการซ่อมบำรุงรถยนต์ทั้งหมด', title_format)
        worksheet.set_row(0, 35)
        
        # แสดงเงื่อนไขการกรอง
        factory_text = user_factory if user_factory else "ทุกโรงงาน (Head Admin)"
        export_date = datetime.now().strftime('%d/%m/%Y %H:%M')
        filter_text = f"โรงงาน: {factory_text} | วันเวลาที่ส่งออก: {export_date}"
        
        if f_type:
            filter_text += f" | ประเภทรถ: {f_type}"
        if f_vehicle_id:
            vehicle = env_sudo['fleet.vehicle'].browse(int(f_vehicle_id))
            if vehicle.exists():
                filter_text += f" | รถยนต์: {vehicle.license_plate}"
                
        worksheet.write('A2', filter_text, meta_format)
        worksheet.set_row(1, 20)
        
        headers = [
            'เลขที่แจ้งซ่อม', 'ทะเบียนรถ', 'ประเภทรถ', 'โรงงาน', 
            'วันที่แจ้งซ่อม', 'วันที่ซ่อมเสร็จ', 'ระยะเวลาซ่อม', 'ผู้แจ้งซ่อม', 
            'อาการเสีย', 'รายละเอียดการซ่อม', 'อะไหล่เบิกคลัง', 'อะไหล่นอกสต็อก', 
            'ค่าอะไหล่เบิกคลัง', 'ค่าใช้จ่ายเพิ่มเติม', 'ค่าใช้จ่ายรวม', 'สถานะ'
        ]
        col_widths = {i: len(headers[i]) + 5 for i in range(len(headers))}
        
        for col_num, header_title in enumerate(headers):
            worksheet.write(3, col_num, header_title, header_format)
        worksheet.set_row(3, 26)
        
        row_idx = 4
        sum_parts_cost = 0.0
        sum_additional_cost = 0.0
        sum_total_cost = 0.0
        
        for rep in repair_history:
            is_zebra = (row_idx % 2 == 1)
            fmt_cell = cell_zebra if is_zebra else cell_white
            fmt_center = align_center_zebra if is_zebra else align_center_white
            fmt_price = price_right_zebra if is_zebra else price_right_white
            
            # การแปลงค่าฟิลด์
            ref_val = rep.name or '-'
            plate_val = rep.vehicle_id.license_plate or '-'
            model_val = rep.vehicle_id.model_id.name or '-'
            fac_val = rep.vehicle_id.factory or '-'
            report_val = rep.report_date.strftime('%Y-%m-%d %H:%M') if rep.report_date else '-'
            finish_val = rep.finish_date.strftime('%Y-%m-%d %H:%M') if rep.finish_date else '-'
            duration_val = rep.repair_duration or '-'
            reporter_val = rep.reported_by_id.name or 'ระบบอัตโนมัติ'
            desc_val = rep.description or '-'
            details_val = rep.repair_details or '-'
            
            # ดึงรายการอะไหล่ที่ใช้
            auto_parts_val = rep.auto_parts_used or '-'
            non_stock_val = rep.non_stock_parts or '-'
            
            cost_parts = rep.auto_parts_cost
            cost_add = rep.additional_cost
            cost_total = rep.repair_cost
            
            state_val = 'ซ่อมเสร็จแล้ว' if rep.state == 'done' else 'ยกเลิก' if rep.state == 'cancelled' else rep.state
            
            worksheet.write(row_idx, 0, ref_val, fmt_center)
            worksheet.write(row_idx, 1, plate_val, fmt_center)
            worksheet.write(row_idx, 2, model_val, fmt_cell)
            worksheet.write(row_idx, 3, fac_val, fmt_center)
            worksheet.write(row_idx, 4, report_val, fmt_center)
            worksheet.write(row_idx, 5, finish_val, fmt_center)
            worksheet.write(row_idx, 6, duration_val, fmt_center)
            worksheet.write(row_idx, 7, reporter_val, fmt_cell)
            worksheet.write(row_idx, 8, desc_val, fmt_cell)
            worksheet.write(row_idx, 9, details_val, fmt_cell)
            worksheet.write(row_idx, 10, auto_parts_val, fmt_cell)
            worksheet.write(row_idx, 11, non_stock_val, fmt_cell)
            worksheet.write(row_idx, 12, cost_parts, fmt_price)
            worksheet.write(row_idx, 13, cost_add, fmt_price)
            worksheet.write(row_idx, 14, cost_total, fmt_price)
            
            if rep.state == 'done':
                worksheet.write(row_idx, 15, state_val, state_done)
            else:
                worksheet.write(row_idx, 15, state_val, state_cancel)
                
            sum_parts_cost += cost_parts
            sum_additional_cost += cost_add
            sum_total_cost += cost_total
            
            # วัดขนาดคอลัมน์อัตโนมัติ โดยจำกัดขอบเขตคอลัมน์รายละเอียดตัวอักษรยาวไม่ให้กว้างเกินไป
            for col_num, val in enumerate([
                ref_val, plate_val, model_val, fac_val, report_val, finish_val, duration_val, reporter_val,
                desc_val[:30] if desc_val else '', details_val[:30] if details_val else '',
                auto_parts_val[:30] if auto_parts_val else '', non_stock_val[:30] if non_stock_val else '',
                f"฿{cost_parts:.2f}", f"฿{cost_add:.2f}", f"฿{cost_total:.2f}", state_val
            ]):
                val_len = len(val) * 2 + 3 if any(ord(char) > 127 for char in val) else len(val) + 3
                col_widths[col_num] = max(col_widths[col_num], val_len)
                
            worksheet.set_row(row_idx, 22)
            row_idx += 1
            
        # เขียนแถวสรุปรวมผลรวมค่าใช้จ่ายทั้งหมด
        worksheet.merge_range(row_idx, 0, row_idx, 11, 'ยอดรวมค่าใช้จ่ายทั้งหมด', total_label_format)
        worksheet.write(row_idx, 12, sum_parts_cost, total_format)
        worksheet.write(row_idx, 13, sum_additional_cost, total_format)
        worksheet.write(row_idx, 14, sum_total_cost, total_format)
        worksheet.write(row_idx, 15, '', total_label_format)
        worksheet.set_row(row_idx, 24)
        
        # ปรับขนาดคอลัมน์ตามที่วัดไว้ (จำกัดสูงสุด 35)
        for col_num, width in col_widths.items():
            worksheet.set_column(col_num, col_num, min(max(width, 11), 35))
            
        workbook.close()
        output.seek(0)
        
        filename = f"Vehicle_Repair_History_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return request.make_response(
            output.getvalue(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', f'attachment; filename="{filename}"')
            ]
        )

    @http.route(['/automotive/repair/submit'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_repair_submit(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
            
        try:
            vehicle_id = post.get('vehicle_id')
            description = post.get('description')
            
            if not vehicle_id or not description:
                return request.redirect('/automotive/repair?error=กรุณาระบุรถและรายละเอียดอาการเสีย')
                
            request.env['vehicle.repair.request'].sudo().create({
                'vehicle_id': int(vehicle_id),
                'description': description,
                'reported_by_id': request.env.user.id,
            })
            
            return request.redirect('/automotive/repair?msg=repair_added')
        except Exception as e:
            return request.redirect("/automotive/repair?error=" + str(e))
            
    @http.route(['/automotive/setup/rename-vehicles'], type='http', auth="user", website=True)
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
        
        return request.redirect('/automotive/dashboard?msg=rename_completed&count={updated_count}')

    @http.route(['/automotive/setup/assign-tqs'], type='http', auth="user", website=True)
    def admin_assign_tqs(self, **post):
        """กำหนดรถที่ยังไม่มี factory ทั้งหมดให้เป็น TQS"""
        if not self._is_admin():
            return request.render("http_routing.403")

        env_sudo = request.env(su=True)
        # กำหนด TQS ให้รถที่ยังไม่มีค่า factory หรือมีค่าว่าง
        vehicles = env_sudo['fleet.vehicle'].search(['|', ('factory', '=', False), ('factory', '=', '')])
        count = len(vehicles)
        vehicles.write({'factory': 'TQS'})
        return request.redirect('/automotive/dashboard?msg=assign_tqs_done&count={count}')


    @http.route(['/automotive/repair/done'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_repair_done(self, **post):
        # ตรวจสอบสิทธิ์แอดมินก่อนดำเนินการ
        if not self._is_admin():
            return request.render("http_routing.403")
        
        repair_id = post.get('repair_id')
        repair = request.env['vehicle.repair.request'].sudo().browse(int(repair_id))
        
        if repair.exists():
            # ดึงรายการไอดีการเบิกอะไหล่คลังที่ต้องการลบ (คืนสต็อก) จากหน้า Modal
            deleted_moves_str = post.get('deleted_movement_ids', '')
            if deleted_moves_str:
                move_ids = [int(m_id) for m_id in deleted_moves_str.split(',') if m_id.strip()]
                if move_ids:
                    moves_to_delete = request.env['vehicle.spare.part.movement'].sudo().browse(move_ids)
                    # ตรวจสอบเอาเฉพาะอันที่ยังคงอยู่ในระบบ (exists) เพื่อป้องกัน error ในกรณีที่ถูกลบทันทีผ่าน AJAX ไปก่อนหน้าแล้ว
                    existing_moves = moves_to_delete.exists()
                    if existing_moves:
                        existing_moves.unlink()

            vals = {
                'repair_details': post.get('repair_details'),
                'parts_used': post.get('parts_used'),
                # รับค่าข้อมูลอะไหล่นอกสต็อกและค่าใช้จ่ายเพิ่มเติมที่กรอกจากหน้าฟอร์มเพื่อบันทึกลงในระบบ
                'non_stock_parts': post.get('non_stock_parts'),
                'repair_cost': float(post.get('repair_cost') or 0),
                'additional_cost': float(post.get('additional_cost') or 0),
            }
            repair.action_done(vals)
        return request.redirect('/automotive/repair?msg=status_updated')

    @http.route(['/automotive/repair/parts/delete_item'], type='json', auth="user", methods=['POST'], website=True, csrf=False)
    def admin_repair_parts_delete_item(self, movement_id, **post):
        """
        ยกเลิกการเบิกใช้อะไหล่รายชิ้นทันทีเมื่อกดยืนยัน (AJAX)
        และเพิ่มจำนวนอะไหล่กลับเข้าคลังสต็อกในระบบ (Real-time Stock Return)
        """
        # ตรวจสอบสิทธิ์ผู้ดูแลระบบ
        if not self._is_admin():
            return {'success': False, 'error': 'คุณไม่มีสิทธิ์เข้าถึงระบบนี้'}
        
        try:
            # ค้นหารายการเบิกอะไหล่ในระบบ
            movement = request.env['vehicle.spare.part.movement'].sudo().browse(int(movement_id))
            if not movement.exists():
                return {'success': False, 'error': 'ไม่พบรายการเบิกอะไหล่ในระบบ'}
            
            repair = movement.repair_id
            
            # ลบรายการเคลื่อนไหวซึ่งจะเพิ่มจำนวนคงเหลือในคลังกลับคืนโดย compute อัตโนมัติ
            movement.unlink()
            
            # ล้างแคชเพื่อให้ Odoo ทำการคำนวณราคารวมและรายการอะไหล่ล่าสุด
            repair.invalidate_recordset()
            
            return {
                'success': True,
                'auto_parts_cost': repair.auto_parts_cost,
                'auto_parts_json': repair.auto_parts_json,
                'auto_parts_used': repair.auto_parts_used,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


    # --- SPARE PARTS FRONTEND ---

    @http.route(['/automotive/spare-parts'], type='http', auth="user", website=True)
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
        
        # ดึงประเภทรถจากฐานข้อมูล (กรองเฉพาะประเภทที่มีตัวรถจริงตามสิทธิ์โรงงาน)
        vehicle_types = sorted(list(set([v.model_id.name for v in vehicles if v.model_id and v.model_id.name])))
        
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
        
        # --- ระบบแบ่งหน้า (Pagination) สำหรับสต็อกอะไหล่ (แสดงครั้งละ 20 รายการ) ---
        try:
            page = int(post.get('page', 1))
        except (ValueError, TypeError):
            page = 1
        if page < 1:
            page = 1

        limit = 20
        offset = (page - 1) * limit

        # นับจำนวนอะไหล่ทั้งหมดที่ตรงตามเงื่อนไขเพื่อคำนวณจำนวนหน้า (ภาษาไทยคอมเมนต์)
        total_count = env_sudo['vehicle.spare.part'].with_context(active_test=False).search_count(domain)
        total_pages = math.ceil(total_count / limit) or 1
        if page > total_pages:
            page = total_pages
            offset = (page - 1) * limit

        # แสดงรายการเฉพาะหน้านั้นๆ รวมถึงที่ปิดการใช้งาน (Inactive) (ภาษาไทยคอมเมนต์)
        parts = env_sudo['vehicle.spare.part'].with_context(active_test=False).search(
            domain, order='name', limit=limit, offset=offset
        )

        # สร้างรายการปุ่มลิงก์ Pagination โดยรักษาพารามิเตอร์ของหน้าสต็อกอะไหล่อื่นๆ ไว้ (ภาษาไทยคอมเมนต์)
        pages_list = []
        for p in range(1, total_pages + 1):
            params = post.copy()
            params['page'] = p
            params = {k: v for k, v in params.items() if v}
            pages_list.append({
                'num': p,
                'url': '/automotive/spare-parts?' + urlencode(params),
                'is_current': p == page
            })

        prev_page_url = None
        if page > 1:
            params = post.copy()
            params['page'] = page - 1
            params = {k: v for k, v in params.items() if v}
            prev_page_url = '/automotive/spare-parts?' + urlencode(params)

        next_page_url = None
        if page < total_pages:
            params = post.copy()
            params['page'] = page + 1
            params = {k: v for k, v in params.items() if v}
            next_page_url = '/automotive/spare-parts?' + urlencode(params)
        
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
                # เพิ่มฟิลด์ in_date เริ่มต้นเพื่อบันทึกวันที่นำเข้าของล็อต
                lot_details[p_id][lot] = {'qty': 0, 'price': 0.0, 'in_date': '-'}
            
            if move.move_type == 'in':
                lot_details[p_id][lot]['qty'] += move.qty
                if move.unit_price > 0:
                    lot_details[p_id][lot]['price'] = move.unit_price
                # เก็บข้อมูลวันที่นำเข้าของล็อตการผลิตนี้ (เมื่อวนลูป date asc จะได้วันล่าสุดของการนำเข้า)
                if move.date:
                    lot_details[p_id][lot]['in_date'] = move.date.strftime('%d/%m/%Y')
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
            # ส่งตัวแปรสำหรับแบ่งหน้าข้อมูลสต็อกอะไหล่ไปยังหน้ากาก (ภาษาไทยคอมเมนต์)
            'page': page,
            'total_pages': total_pages,
            'total_count': total_count,
            'pages_list': pages_list,
            'prev_page_url': prev_page_url,
            'next_page_url': next_page_url,
        })

    @http.route(['/automotive/spare-parts/move'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
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
            return request.redirect('/automotive/spare-parts?msg=move_success')
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Spare Parts Move Error: %s", str(e))
            return request.redirect("/automotive/spare-parts?error=" + str(e))

    @http.route(['/automotive/spare-parts/history'], type='http', auth="user", website=True)
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
            
        # --- ระบบแบ่งหน้า (Pagination) สำหรับประวัติอะไหล่ (แสดงครั้งละ 20 รายการ) ---
        try:
            page = int(post.get('page', 1))
        except (ValueError, TypeError):
            page = 1
        if page < 1:
            page = 1

        limit = 20
        offset = (page - 1) * limit

        # นับจำนวนประวัติทั้งหมดเพื่อคำนวณจำนวนหน้า (ภาษาไทยคอมเมนต์)
        total_count = env_sudo['vehicle.spare.part.movement'].search_count(domain)
        total_pages = math.ceil(total_count / limit) or 1
        if page > total_pages:
            page = total_pages
            offset = (page - 1) * limit

        history = env_sudo['vehicle.spare.part.movement'].search(
            domain, order='date desc, id desc', limit=limit, offset=offset
        )

        # สร้างรายการปุ่มลิงก์ Pagination โดยรักษาพารามิเตอร์ตัวกรองเดิมไว้ (ภาษาไทยคอมเมนต์)
        pages_list = []
        for p in range(1, total_pages + 1):
            params = post.copy()
            params['page'] = p
            params = {k: v for k, v in params.items() if v}
            pages_list.append({
                'num': p,
                'url': '/automotive/spare-parts/history?' + urlencode(params),
                'is_current': p == page
            })

        prev_page_url = None
        if page > 1:
            params = post.copy()
            params['page'] = page - 1
            params = {k: v for k, v in params.items() if v}
            prev_page_url = '/automotive/spare-parts/history?' + urlencode(params)

        next_page_url = None
        if page < total_pages:
            params = post.copy()
            params['page'] = page + 1
            params = {k: v for k, v in params.items() if v}
            next_page_url = '/automotive/spare-parts/history?' + urlencode(params)
        
        # Fetch data for filter dropdowns
        all_parts = env_sudo['vehicle.spare.part'].search([], order='name')
        # กรองรถใน dropdown ให้เห็นเฉพาะโรงงานตัวเอง
        all_vehicles = env_sudo['fleet.vehicle'].search(list(factory_domain) + [('active', '=', True)])
        
        # ดึงประเภทรถจากฐานข้อมูล (กรองเฉพาะที่มีรถจริงตามสิทธิ์โรงงาน)
        vehicle_types = sorted(list(set([v.model_id.name for v in all_vehicles if v.model_id and v.model_id.name])))
        
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
            # ส่งตัวแปรสำหรับแบ่งหน้าข้อมูลประวัติอะไหล่ไปยังหน้ากาก (ภาษาไทยคอมเมนต์)
            'page': page,
            'total_pages': total_pages,
            'total_count': total_count,
            'pages_list': pages_list,
            'prev_page_url': prev_page_url,
            'next_page_url': next_page_url,
        })

    @http.route(['/automotive/spare-parts/export'], type='http', auth="user", website=True)
    def admin_spare_parts_export(self, **post):
        # ฟังก์ชันตรวจสอบสิทธิ์ผู้ใช้
        if not self._is_admin():
            return request.render("http_routing.403")
        
        env_sudo = request.env(su=True)
        user_factory = self._get_user_factory()
        
        # กรองข้อมูลตามฟิลเตอร์แบบเดียวกับหน้าแดชบอร์ดหลัก
        domain = []
        search = post.get('search')
        if search:
            domain += ['|', ('name', 'ilike', search), ('code', 'ilike', search)]
            
        selected_category_id = post.get('category_id') or 'all'
        if selected_category_id != 'all':
            domain.append(('category_id', '=', int(selected_category_id)))
            
        stock_status = post.get('stock_status') or 'all'
        if stock_status == 'out':
            domain.append(('qty_on_hand', '=', 0))
        elif stock_status == 'low':
            domain += [('qty_on_hand', '>', 0), ('qty_on_hand', '<=', 2)]
        elif stock_status == 'normal':
            domain.append(('qty_on_hand', '>', 2))
            
        if user_factory:
            domain.append(('factory', '=', user_factory))
            
        parts = env_sudo['vehicle.spare.part'].with_context(active_test=False).search(domain, order='name')
        
        import io
        import xlsxwriter
        from datetime import datetime
        
        # สร้าง Buffer ในหน่วยความจำเพื่อเขียนไฟล์ Excel
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('คลังอะไหล่คงเหลือ')
        
        # แสดงเส้น Gridlines ปกติ
        worksheet.hide_gridlines(0)
        
        # จัดรูปแบบตัวอักษรและสีตารางสไตล์พรีเมียม
        title_format = workbook.add_format({
            'bold': True, 'font_size': 16, 'font_name': 'Cordia New', 'font_color': '#1F4E79', 'align': 'left', 'valign': 'vcenter'
        })
        meta_format = workbook.add_format({
            'font_size': 11, 'font_name': 'Cordia New', 'font_color': '#595959', 'align': 'left'
        })
        header_format = workbook.add_format({
            'bold': True, 'font_size': 12, 'font_name': 'Cordia New', 'font_color': '#FFFFFF', 'bg_color': '#1F4E79',
            'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#D9D9D9'
        })
        
        # รูปแบบสำหรับแถวสลับสี (Zebra Striping)
        cell_white = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'border': 1, 'border_color': '#E0E0E0', 'valign': 'vcenter'})
        cell_zebra = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'bg_color': '#F9FBFD', 'border': 1, 'border_color': '#E0E0E0', 'valign': 'vcenter'})
        
        align_center_white = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#E0E0E0'})
        align_center_zebra = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'align': 'center', 'valign': 'vcenter', 'bg_color': '#F9FBFD', 'border': 1, 'border_color': '#E0E0E0'})
        
        number_right_white = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'align': 'right', 'valign': 'vcenter', 'border': 1, 'border_color': '#E0E0E0', 'num_format': '#,##0'})
        number_right_zebra = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'align': 'right', 'valign': 'vcenter', 'bg_color': '#F9FBFD', 'border': 1, 'border_color': '#E0E0E0', 'num_format': '#,##0'})
        
        # สไตล์แสดงผลสัญลักษณ์สีสำหรับสถานะสต็อก
        status_normal = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'font_color': '#1E4620', 'bg_color': '#D1E7DD', 'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#E0E0E0'})
        status_low = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'font_color': '#842029', 'bg_color': '#F8D7DA', 'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#E0E0E0'})
        status_inactive = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'font_color': '#41464B', 'bg_color': '#E2E3E5', 'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#E0E0E0'})
        
        total_format = workbook.add_format({'bold': True, 'font_size': 12, 'font_name': 'Cordia New', 'bg_color': '#EAEAEA', 'border': 1, 'border_color': '#A6A6A6', 'align': 'right', 'valign': 'vcenter', 'num_format': '#,##0'})
        total_label_format = workbook.add_format({'bold': True, 'font_size': 12, 'font_name': 'Cordia New', 'bg_color': '#EAEAEA', 'border': 1, 'border_color': '#A6A6A6', 'align': 'center', 'valign': 'vcenter'})
        
        # เขียนชื่อหัวข้อหลักรายงาน
        worksheet.write('A1', 'รายงานรายการอะไหล่และยอดคงเหลือในคลัง', title_format)
        worksheet.set_row(0, 35)
        
        # แสดงเงื่อนไขที่เลือกกรองข้อมูล
        factory_text = user_factory if user_factory else "ทุกโรงงาน (Head Admin)"
        export_date = datetime.now().strftime('%d/%m/%Y %H:%M')
        filter_text = f"โรงงาน: {factory_text} | วันเวลาที่ส่งออก: {export_date}"
        if search:
            filter_text += f" | คำค้นหา: {search}"
        if stock_status != 'all':
            status_map = {'out': 'หมด', 'low': 'สต็อกต่ำ', 'normal': 'ปกติ'}
            filter_text += f" | สถานะสต็อก: {status_map.get(stock_status, stock_status)}"
        worksheet.write('A2', filter_text, meta_format)
        worksheet.set_row(1, 20)
        
        # กำหนดชื่อหัวคอลัมน์ตาราง
        headers = ['รหัสอะไหล่', 'ชื่ออะไหล่', 'หมวดหมู่', 'โรงงาน', 'จำนวนคงเหลือ', 'หน่วยนับ', 'ระดับสั่งซื้อขั้นต่ำ', 'สถานะ', 'รายละเอียดเพิ่มเติม']
        col_widths = {i: len(headers[i]) + 5 for i in range(len(headers))}
        
        for col_num, header_title in enumerate(headers):
            worksheet.write(3, col_num, header_title, header_format)
        worksheet.set_row(3, 26)
        
        # วนลูปกรอกข้อมูลลงแถวตาราง
        row_idx = 4
        total_qty = 0.0
        for p in parts:
            is_zebra = (row_idx % 2 == 1)
            fmt_cell = cell_zebra if is_zebra else cell_white
            fmt_center = align_center_zebra if is_zebra else align_center_white
            fmt_number = number_right_zebra if is_zebra else number_right_white
            
            # ดึงค่าเพื่อเตรียมเขียน
            code_val = p.code or '-'
            name_val = p.name or ''
            cat_val = p.category_id.name or '-'
            fac_val = p.factory or '-'
            qty_val = p.qty_on_hand
            uom_val = p.uom or 'ชิ้น'
            min_val = p.min_qty
            desc_val = p.description or '-'
            
            worksheet.write(row_idx, 0, code_val, fmt_center)
            worksheet.write(row_idx, 1, name_val, fmt_cell)
            worksheet.write(row_idx, 2, cat_val, fmt_cell)
            worksheet.write(row_idx, 3, fac_val, fmt_center)
            worksheet.write(row_idx, 4, qty_val, fmt_number)
            worksheet.write(row_idx, 5, uom_val, fmt_center)
            worksheet.write(row_idx, 6, min_val, fmt_number)
            
            # กำหนดสถานะสต็อกอย่างละเอียดตามข้อมูลจริง
            if 'active' in p._fields and not p.active:
                worksheet.write(row_idx, 7, 'ปิดใช้งาน', status_inactive)
                status_val = 'ปิดใช้งาน'
            elif p.qty_on_hand == 0:
                worksheet.write(row_idx, 7, 'หมด', status_low)
                status_val = 'หมด'
            elif p.qty_on_hand <= p.min_qty:
                worksheet.write(row_idx, 7, 'สต็อกต่ำ', status_low)
                status_val = 'สต็อกต่ำ'
            else:
                worksheet.write(row_idx, 7, 'ปกติ', status_normal)
                status_val = 'ปกติ'
                
            worksheet.write(row_idx, 8, desc_val, fmt_cell)
            total_qty += qty_val
            
            # วัดขนาดคอลัมน์เพื่อความสวยงาม
            for col_num, val in enumerate([code_val, name_val, cat_val, fac_val, str(int(qty_val)), uom_val, str(int(min_val)), status_val, desc_val]):
                val_len = len(val) * 2 + 3 if any(ord(char) > 127 for char in val) else len(val) + 3
                col_widths[col_num] = max(col_widths[col_num], val_len)
                
            worksheet.set_row(row_idx, 22)
            row_idx += 1
            
        # เขียนแถวสรุปรวมผลยอดคงเหลือ
        worksheet.merge_range(row_idx, 0, row_idx, 3, 'รวมยอดคงคลังทั้งหมด', total_label_format)
        worksheet.write(row_idx, 4, total_qty, total_format)
        worksheet.merge_range(row_idx, 5, row_idx, 8, '', total_label_format)
        worksheet.set_row(row_idx, 24)
        
        # ปรับขนาดความกว้างตามที่วัดไว้
        for col_num, width in col_widths.items():
            # กำหนดขอบเขตขั้นต่ำไม่ให้คอลัมน์แคบเกินไป
            worksheet.set_column(col_num, col_num, max(width, 11))
            
        workbook.close()
        output.seek(0)
        
        filename = f"Spare_Parts_Inventory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return request.make_response(
            output.getvalue(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', f'attachment; filename="{filename}"')
            ]
        )

    @http.route(['/automotive/spare-parts/history/export'], type='http', auth="user", website=True)
    def admin_spare_parts_history_export(self, **post):
        # ฟังก์ชันตรวจสอบสิทธิ์แอดมินในการทำรายการ
        if not self._is_admin():
            return request.render("http_routing.403")
        
        env_sudo = request.env(su=True)
        user_factory = self._get_user_factory()
        
        # กำหนด Domain กรองข้อมูลตามสิทธิ์ของโรงงาน
        domain = []
        if user_factory:
            repair_factory_domain = [('vehicle_id.factory', '=', user_factory)]
            domain += ['|', ('vehicle_id', '=', False)] + list(repair_factory_domain)
            
        # กรองข้อมูลเพิ่มเติมตามตัวกรองที่ส่งมาจาก Form ค้นหา
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
        
        import io
        import xlsxwriter
        from datetime import datetime
        
        # เตรียม Buffer เขียนข้อมูลตาราง Excel
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('ประวัติการรับ-จ่ายอะไหล่')
        
        worksheet.hide_gridlines(0)
        
        # จัดสไตล์รูปแบบและสีสำหรับหัวรายงานและหัวข้อคอลัมน์
        title_format = workbook.add_format({
            'bold': True, 'font_size': 16, 'font_name': 'Cordia New', 'font_color': '#1F4E79', 'align': 'left', 'valign': 'vcenter'
        })
        meta_format = workbook.add_format({
            'font_size': 11, 'font_name': 'Cordia New', 'font_color': '#595959', 'align': 'left'
        })
        header_format = workbook.add_format({
            'bold': True, 'font_size': 12, 'font_name': 'Cordia New', 'font_color': '#FFFFFF', 'bg_color': '#1F4E79',
            'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#D9D9D9'
        })
        
        cell_white = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'border': 1, 'border_color': '#E0E0E0', 'valign': 'vcenter'})
        cell_zebra = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'bg_color': '#F9FBFD', 'border': 1, 'border_color': '#E0E0E0', 'valign': 'vcenter'})
        
        align_center_white = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#E0E0E0'})
        align_center_zebra = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'align': 'center', 'valign': 'vcenter', 'bg_color': '#F9FBFD', 'border': 1, 'border_color': '#E0E0E0'})
        
        number_right_white = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'align': 'right', 'valign': 'vcenter', 'border': 1, 'border_color': '#E0E0E0', 'num_format': '#,##0'})
        number_right_zebra = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'align': 'right', 'valign': 'vcenter', 'bg_color': '#F9FBFD', 'border': 1, 'border_color': '#E0E0E0', 'num_format': '#,##0'})
        
        price_right_white = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'align': 'right', 'valign': 'vcenter', 'border': 1, 'border_color': '#E0E0E0', 'num_format': '฿#,##0.00'})
        price_right_zebra = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'align': 'right', 'valign': 'vcenter', 'bg_color': '#F9FBFD', 'border': 1, 'border_color': '#E0E0E0', 'num_format': '฿#,##0.00'})
        
        # รูปแบบสีสันของสัญลักษณ์ประเภทรับเข้า-เบิกออก
        type_in = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'font_color': '#1E4620', 'bg_color': '#D1E7DD', 'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#E0E0E0'})
        type_out = workbook.add_format({'font_size': 11, 'font_name': 'Cordia New', 'font_color': '#842029', 'bg_color': '#F8D7DA', 'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#E0E0E0'})
        
        total_format = workbook.add_format({'bold': True, 'font_size': 12, 'font_name': 'Cordia New', 'bg_color': '#EAEAEA', 'border': 1, 'border_color': '#A6A6A6', 'align': 'right', 'valign': 'vcenter', 'num_format': '฿#,##0.00'})
        total_qty_format = workbook.add_format({'bold': True, 'font_size': 12, 'font_name': 'Cordia New', 'bg_color': '#EAEAEA', 'border': 1, 'border_color': '#A6A6A6', 'align': 'right', 'valign': 'vcenter', 'num_format': '#,##0'})
        total_label_format = workbook.add_format({'bold': True, 'font_size': 12, 'font_name': 'Cordia New', 'bg_color': '#EAEAEA', 'border': 1, 'border_color': '#A6A6A6', 'align': 'center', 'valign': 'vcenter'})
        
        # เขียนหัวรายงานหลักและช่วงวิเคราะห์ผลลัพธ์
        worksheet.write('A1', 'รายงานประวัติการรับเข้าและเบิกใช้อะไหล่', title_format)
        worksheet.set_row(0, 35)
        
        factory_text = user_factory if user_factory else "ทุกโรงงาน (Head Admin)"
        export_date = datetime.now().strftime('%d/%m/%Y %H:%M')
        filter_text = f"โรงงาน: {factory_text} | วันเวลาที่ส่งออก: {export_date}"
        
        if f_date_start and f_date_end:
            filter_text += f" | ช่วงวันที่: {f_date_start} ถึง {f_date_end}"
        elif f_date_start:
            filter_text += f" | ตั้งแต่วันที่: {f_date_start}"
        elif f_date_end:
            filter_text += f" | จนถึงวันที่: {f_date_end}"
            
        if f_move_type and f_move_type != 'all':
            type_map = {'in': 'รับเข้า (IN)', 'out': 'เบิกออก (OUT)'}
            filter_text += f" | ประเภทรายการ: {type_map.get(f_move_type)}"
            
        worksheet.write('A2', filter_text, meta_format)
        worksheet.set_row(1, 20)
        
        # รายการคอลัมน์ประวัติเคลื่อนไหว
        headers = ['วันเวลา', 'รหัสอะไหล่', 'ชื่ออะไหล่', 'ประเภท', 'จำนวน', 'หน่วย', 'ล็อตผลิต', 'ราคา/หน่วย', 'ราคารวม', 'อ้างอิง/รถที่ใช้', 'ผู้บันทึก']
        col_widths = {i: len(headers[i]) + 5 for i in range(len(headers))}
        
        for col_num, header_title in enumerate(headers):
            worksheet.write(3, col_num, header_title, header_format)
        worksheet.set_row(3, 26)
        
        row_idx = 4
        sum_qty_in = 0.0
        sum_qty_out = 0.0
        sum_value = 0.0
        
        for h in history:
            is_zebra = (row_idx % 2 == 1)
            fmt_cell = cell_zebra if is_zebra else cell_white
            fmt_center = align_center_zebra if is_zebra else align_center_white
            fmt_number = number_right_zebra if is_zebra else number_right_white
            fmt_price = price_right_zebra if is_zebra else price_right_white
            
            # การแปลงค่าฟิลด์
            date_val = h.date.strftime('%Y-%m-%d %H:%M') if h.date else '-'
            code_val = h.part_id.code or '-'
            name_val = h.part_id.name or ''
            type_str = 'รับเข้า (IN)' if h.move_type == 'in' else 'เบิกจ่าย (OUT)'
            qty_val = h.qty
            uom_val = h.part_id.uom or 'ชิ้น'
            lot_val = h.lot_number or '-'
            price_val = h.unit_price
            val_total = qty_val * price_val if price_val > 0 else 0.0
            
            # ข้อมูลรถยนต์อ้างอิง
            ref_val = '-'
            if h.vehicle_id:
                ref_val = f"{h.vehicle_id.license_plate} ({h.vehicle_id.factory})"
            elif h.reference:
                ref_val = h.reference
                
            user_val = h.user_id.name or '-'
            
            # เขียนลงเซลล์
            worksheet.write(row_idx, 0, date_val, fmt_center)
            worksheet.write(row_idx, 1, code_val, fmt_center)
            worksheet.write(row_idx, 2, name_val, fmt_cell)
            
            # ระบุประเภทรายการ
            if h.move_type == 'in':
                worksheet.write(row_idx, 3, type_str, type_in)
                sum_qty_in += qty_val
            else:
                worksheet.write(row_idx, 3, type_str, type_out)
                sum_qty_out += qty_val
                
            worksheet.write(row_idx, 4, qty_val, fmt_number)
            worksheet.write(row_idx, 5, uom_val, fmt_center)
            worksheet.write(row_idx, 6, lot_val, fmt_center)
            worksheet.write(row_idx, 7, price_val, fmt_price)
            worksheet.write(row_idx, 8, val_total, fmt_price)
            worksheet.write(row_idx, 9, ref_val, fmt_cell)
            worksheet.write(row_idx, 10, user_val, fmt_cell)
            
            sum_value += val_total
            
            # วัดขนาดคอลัมน์อัตโนมัติ
            for col_num, val in enumerate([date_val, code_val, name_val, type_str, str(int(qty_val)), uom_val, lot_val, f"฿{price_val:.2f}", f"฿{val_total:.2f}", ref_val, user_val]):
                val_len = len(val) * 2 + 3 if any(ord(char) > 127 for char in val) else len(val) + 3
                col_widths[col_num] = max(col_widths[col_num], val_len)
                
            worksheet.set_row(row_idx, 22)
            row_idx += 1
            
        # เขียนสรุปรวมผลลัพธ์
        worksheet.merge_range(row_idx, 0, row_idx, 3, 'ยอดรวมรับเข้าทั้งหมด', total_label_format)
        worksheet.write(row_idx, 4, sum_qty_in, total_qty_format)
        worksheet.merge_range(row_idx, 5, row_idx, 10, '', total_label_format)
        worksheet.set_row(row_idx, 24)
        row_idx += 1
        
        worksheet.merge_range(row_idx, 0, row_idx, 3, 'ยอดรวมเบิกจ่ายทั้งหมด', total_label_format)
        worksheet.write(row_idx, 4, sum_qty_out, total_qty_format)
        worksheet.merge_range(row_idx, 5, row_idx, 7, '', total_label_format)
        worksheet.write(row_idx, 8, sum_value, total_format)
        worksheet.merge_range(row_idx, 9, row_idx, 10, '', total_label_format)
        worksheet.set_row(row_idx, 24)
        
        # ปรับความกว้างคอลัมน์ตามขนาดจริง
        for col_num, width in col_widths.items():
            worksheet.set_column(col_num, col_num, max(width, 11))
            
        workbook.close()
        output.seek(0)
        
        filename = f"Spare_Parts_History_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return request.make_response(
            output.getvalue(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', f'attachment; filename="{filename}"')
            ]
        )

    @http.route(['/automotive/spare-parts/add'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
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
            return request.redirect('/automotive/spare-parts?msg=part_added')
        except Exception as e:
            return request.redirect("/automotive/spare-parts?error=" + str(e))

    @http.route(['/automotive/spare-parts/edit'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_spare_parts_edit(self, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        try:
            part_id = int(post.get('part_id'))
            part = request.env['vehicle.spare.part'].sudo().browse(part_id)
            if not part.exists():
                return request.redirect('/automotive/spare-parts?error=ไม่พบรายการอะไหล่')
                
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
            return request.redirect('/automotive/spare-parts?msg=part_updated')
        except Exception as e:
            return request.redirect("/automotive/spare-parts?error=" + str(e))

    @http.route(['/automotive/spare-parts/toggle-active/<int:part_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_spare_parts_toggle_active(self, part_id, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        try:
            part = request.env['vehicle.spare.part'].sudo().with_context(active_test=False).browse(part_id)
            if part.exists():
                new_state = not part.active
                part.write({'active': new_state})
                msg = "part_activated" if new_state else "part_deactivated"
                return request.redirect('/automotive/spare-parts?msg=' + msg)
            return request.redirect('/automotive/spare-parts?error=ไม่พบรายการอะไหล่')
        except Exception as e:
            return request.redirect("/automotive/spare-parts?error=" + str(e))

    @http.route(['/automotive/spare-parts/delete/<int:part_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
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
                    return request.redirect('/automotive/spare-parts?msg=part_deactivated')
                
                part.unlink()
                return request.redirect('/automotive/spare-parts?msg=part_deleted')
            return request.redirect('/automotive/spare-parts?error=ไม่พบรายการอะไหล่')
        except Exception as e:
            return request.redirect("/automotive/spare-parts?error=" + str(e))

    # --- Vehicle Transfer System ---
    
    @http.route(['/automotive/transfer/submit'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
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
            return request.redirect('/automotive/dashboard?msg=transfer_requested')
        except Exception as e:
            return request.redirect('/automotive/dashboard?error=' + str(e))

    @http.route(['/automotive/transfer/approve/<int:req_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_vehicle_transfer_approve(self, req_id, **post):
        if not self._is_head_admin():
            return request.render("http_routing.403")
        
        transfer = request.env['vehicle.transfer.request'].sudo().browse(req_id)
        if transfer.exists():
            transfer.action_approve()
            return request.redirect('/automotive/dashboard?msg=transfer_approved')
        return request.redirect('/automotive/dashboard')

    @http.route(['/automotive/transfer/cancel/<int:req_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_vehicle_transfer_cancel(self, req_id, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        transfer = request.env['vehicle.transfer.request'].sudo().browse(req_id)
        if transfer.exists():
            transfer.action_cancel()
            return request.redirect('/automotive/dashboard?msg=transfer_cancelled')
        return request.redirect('/automotive/dashboard')

    @http.route(['/automotive/transfer/accept/<int:req_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def admin_vehicle_transfer_accept(self, req_id, **post):
        if not self._is_admin():
            return request.render("http_routing.403")
        
        transfer = request.env['vehicle.transfer.request'].sudo().browse(req_id)
        if transfer.exists():
            # ตรวจสอบว่าผู้กด อยู่ในโรงงานปลายทางหรือไม่ (ยกเว้น Head Admin)
            user_factory = self._get_user_factory()
            if not self._is_head_admin() and transfer.to_factory != user_factory:
                return request.redirect('/automotive/dashboard?error=ไม่ใช่โรงงานปลายทาง')
                
            transfer.action_accept()
            return request.redirect('/automotive/dashboard?msg=transfer_accepted')
        return request.redirect('/automotive/dashboard')

    # === หน้าข้อเสนอแนะ (Suggestion Feature) ===

    @http.route(['/automotive/suggestion'], type='http', auth="user", website=True)
    def vehicle_suggestion_form(self, **post):
        """
        แสดงหน้าฟอร์มกรอกข้อเสนอแนะของพนักงาน
        """
        current_user = request.env.user
        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', current_user.id)], limit=1
        )
        return request.render("vehicle_borrow.suggestion_form_template", {
            'current_employee': employee,
        })

    @http.route(['/automotive/suggestion/submit'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def vehicle_suggestion_submit(self, **post):
        """
        บันทึกข้อเสนอแนะแบบไม่ระบุตัวตน (Anonymous) ลงในฐานข้อมูล
        โดยจะตรวจสอบและแยกประเภท Role/โรงงาน สังกัดของผู้ส่ง
        และใช้ sudo() ในการสร้างเพื่อป้องกันการเก็บบันทึกรหัสผู้ใช้ (create_uid)
        """
        try:
            content = post.get('content')
            if not content:
                return request.redirect('/automotive/suggestion?error=กรุณากรอกข้อความข้อเสนอแนะ')

            current_user = request.env.user
            employee = request.env['hr.employee'].sudo().search(
                [('user_id', '=', current_user.id)], limit=1
            )
            
            # ตรวจสอบสังกัดโรงงานของพนักงานเพื่อแยกประเภท Role
            factory_val = 'other'
            if employee and employee.factory:
                # แปลงค่าให้ตรงกับ Selection ในฟิลด์ factory ของโมเดล vehicle.suggestion
                factory_val = employee.factory

            # บันทึกข้อมูลแบบ Anonymous (ใช้ sudo().create เพื่อบายพาส create_uid และ write_uid ให้เป็นระบบ ID: 1)
            request.env['vehicle.suggestion'].sudo().create({
                'content': content,
                'factory': factory_val,
            })
            return request.redirect('/automotive/suggestion?msg=suggestion_added')
        except Exception as e:
            return request.redirect('/automotive/suggestion?error=' + str(e))

    @http.route(['/automotive/admin/suggestions'], type='http', auth="user", website=True)
    def admin_suggestions(self, **post):
        """
        หน้าแสดงรายการข้อเสนอแนะสำหรับผู้ดูแลระบบ
        โดยจะแยกคัดกรองตามกลุ่มโรงงาน (Role) ของ Admin คนนั้นๆ
        - Admin TQS: เห็นข้อเสนอแนะของ TQS
        - Admin CKR: เห็นข้อเสนอแนะของ CKR
        - Admin TPS: เห็นข้อเสนอแนะของ TPS
        - Head Admin: เห็นข้อเสนอแนะทั้งหมด
        """
        if not self._is_admin():
            return request.render("http_routing.403")

        env_sudo = request.env(su=True)
        user_factory = self._get_user_factory()

        # สร้าง domain กรองตามกลุ่มโรงงานของผู้ใช้ปัจจุบัน
        domain = []
        if not self._is_head_admin() and user_factory:
            domain.append(('factory', '=', user_factory))

        # --- ระบบแบ่งหน้า (Pagination) สำหรับข้อเสนอแนะ (แสดงครั้งละ 20 รายการ) ---
        try:
            page = int(post.get('page', 1))
        except (ValueError, TypeError):
            page = 1
        if page < 1:
            page = 1

        limit = 20
        offset = (page - 1) * limit

        # นับจำนวนข้อเสนอแนะทั้งหมดเพื่อคำนวณจำนวนหน้า (ภาษาไทยคอมเมนต์)
        total_count = env_sudo['vehicle.suggestion'].search_count(domain)
        total_pages = math.ceil(total_count / limit) or 1
        if page > total_pages:
            page = total_pages
            offset = (page - 1) * limit

        # ดึงข้อเสนอแนะตามเงื่อนไข (เรียงจากล่าสุดไปหาเก่าสุด) จำกัดรายการละ 20 แถว (ภาษาไทยคอมเมนต์)
        suggestions = env_sudo['vehicle.suggestion'].search(
            domain, order='date desc', limit=limit, offset=offset
        )

        # สร้างรายการหน้าทั้งหมดเพื่อแสดงเป็นปุ่มลิงก์ (ภาษาไทยคอมเมนต์)
        pages_list = []
        for p in range(1, total_pages + 1):
            params = post.copy()
            params['page'] = p
            params = {k: v for k, v in params.items() if v}
            pages_list.append({
                'num': p,
                'url': '/automotive/admin/suggestions?' + urlencode(params),
                'is_current': p == page
            })

        prev_page_url = None
        if page > 1:
            params = post.copy()
            params['page'] = page - 1
            params = {k: v for k, v in params.items() if v}
            prev_page_url = '/automotive/admin/suggestions?' + urlencode(params)

        next_page_url = None
        if page < total_pages:
            params = post.copy()
            params['page'] = page + 1
            params = {k: v for k, v in params.items() if v}
            next_page_url = '/automotive/admin/suggestions?' + urlencode(params)

        return request.render("vehicle_borrow.admin_suggestions_template", {
            'suggestions': suggestions,
            'user_factory': user_factory or 'ทั้งหมด',
            # ส่งตัวแปรสำหรับการแบ่งหน้าไปประมวลผลที่ QWeb Template (ภาษาไทยคอมเมนต์)
            'page': page,
            'total_pages': total_pages,
            'total_count': total_count,
            'pages_list': pages_list,
            'prev_page_url': prev_page_url,
            'next_page_url': next_page_url,
        })




