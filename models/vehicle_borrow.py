# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

FACTORY_SELECTION = [
    ('TQS', 'TQS'),
    ('CKR', 'CKR'),
    ('TPS', 'TPS'),
]

class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    current_borrow_id = fields.Many2one('vehicle.borrow.request', string='รายการยืมปัจจุบัน', 
                                         compute='_compute_current_borrow', store=False)
    is_available = fields.Boolean(string='ว่าง', compute='_compute_current_borrow', store=False)
    vehicle_status = fields.Selection([
        ('active', 'ใช้งานได้'),
        ('repairing', 'กำลังซ่อม'),
        ('broken', 'เสีย'),
        ('retired', 'ยกเลิกใช้งาน')
    ], string='สถานะรถ', default='active', tracking=True)

    factory = fields.Selection(
        FACTORY_SELECTION,
        string='โรงงาน',
        default='TQS',
        index=True,
        tracking=True,
    )

    # เพิ่มฟิลด์สำหรับระบบ QR Code ประจำตัวรถยนต์
    qr_code_image = fields.Binary(string='QR Code สแกนยืมรถ', compute='_compute_qr_code_image', store=False)
    qr_code_link = fields.Char(string='ลิงก์สแกนยืมรถ', compute='_compute_qr_code_image', store=False)

    def _compute_qr_code_image(self):
        """
        ฟังก์ชันสำหรับสร้างภาพ QR Code และลิงก์สำหรับสแกนยืมรถยนต์แบบอัตโนมัติ
        โดยจะแปลง URL ของระบบรวมถึง ID ของรถยนต์เป็นรหัส QR Code
        และวาดป้ายทะเบียนและป้ายกำกับเตือนความปลอดภัยลงบนรูปภาพผลลัพธ์ที่จะถูกดาวน์โหลดด้วย (ภาษาไทยคอมเมนต์)
        """
        # ดึง base_url ของ Odoo (เช่น http://localhost:8069 หรือโดเมนเนมใช้งานจริง)
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            # ลิงก์ปลายทางสำหรับการสแกนเลือกรถยนต์ทันที
            link = f"{base_url}/automotive?scan_vehicle_id={record.id}"
            record.qr_code_link = link
            
            try:
                import qrcode
                import io
                import base64
                import os
                from PIL import Image, ImageDraw, ImageFont
                
                # ตั้งค่าไลบรารี qrcode
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4,
                )
                qr.add_data(link)
                qr.make(fit=True)
                
                # แปลงรหัส QR เป็นรูปภาพ PIL
                img = qr.make_image(fill_color="black", back_color="white")
                qr_img = img.convert("RGB")
                qr_w, qr_h = qr_img.size
                
                # ขนาดภาพการ์ดใหม่ (เว้นขอบบนสำหรับแถบเมนูกรมท่าและด้านล่างสำหรับการ์ดที่สวยงาม ปรับความสูงเป็น qr_h + 225 เพื่อให้ครอบคลุมขอบ Alert Box) (ภาษาไทยคอมเมนต์)
                canvas_w = qr_w + 40
                canvas_h = qr_h + 225  # ความสูงทั้งหมดปรับเป็น 515px เพื่อสัดส่วนและระยะขอบที่สมบูรณ์แบบไม่ล้นขอบ
                
                # สร้างรูปภาพเปล่าสีขาว
                canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
                draw = ImageDraw.Draw(canvas)
                
                # 1. วาดแถบหัวข้อสีน้ำเงินกรมท่าด้านบนของการ์ด (ภาษาไทยคอมเมนต์)
                draw.rectangle([0, 0, canvas_w - 1, 45], fill="#1e293b")
                
                # 2. วาดเส้นขอบสีสีกรมท่าล้อมรอบการ์ดทั้งหมดเพื่อความพรีเมียม (ภาษาไทยคอมเมนต์)
                draw.rectangle([0, 0, canvas_w - 1, canvas_h - 1], outline="#1e293b", width=3)
                
                # แปะ QR Code ลงบนการ์ด (เลื่อนลงมา 65px เพื่อหลบแถบหัวข้อด้านบน) (ภาษาไทยคอมเมนต์)
                canvas.paste(qr_img, (20, 65))
                
                # กำหนดพาธไปยังฟอนต์ Sarabun เพื่อรองรับภาษาไทยใน Pillow (ภาษาไทยคอมเมนต์)
                current_dir = os.path.dirname(os.path.abspath(__file__))
                font_dir = os.path.join(current_dir, "..", "static", "src", "fonts")
                font_regular = os.path.join(font_dir, "Sarabun-Regular.ttf")
                font_bold = os.path.join(font_dir, "Sarabun-Bold.ttf")
                
                # โหลดฟอนต์หากไฟล์มีอยู่จริง หากไม่มีให้ใช้ฟอนต์ดีฟอลต์ของระบบ
                try:
                    font_header = ImageFont.truetype(font_bold, 12)
                    font_plate = ImageFont.truetype(font_bold, 20)
                    font_warn = ImageFont.truetype(font_bold, 20)
                except Exception:
                    font_header = ImageFont.load_default()
                    font_plate = ImageFont.load_default()
                    font_warn = ImageFont.load_default()
                
                # ฟังก์ชันภายในสำหรับคำนวณและวาดข้อความกึ่งกลาง (ภาษาไทยคอมเมนต์)
                def draw_centered_text(draw_obj, y_offset, text, font_obj, color_str, width_limit):
                    try:
                        bbox = draw_obj.textbbox((0, 0), text, font=font_obj)
                        text_w = bbox[2] - bbox[0]
                    except AttributeError:
                        text_w, _ = draw_obj.textsize(text, font=font_obj)
                    x = (width_limit - text_w) // 2
                    draw_obj.text((x, y_offset), text, font=font_obj, fill=color_str)
                
                # วาดข้อความหัวข้อบนแถบน้ำเงินกรมท่า (ภาษาไทยคอมเมนต์)
                draw_centered_text(draw, 14, "TQS VEHICLE SYSTEM", font_header, "#ffffff", canvas_w)
                
                # 3. วาดป้ายทะเบียนรถในกล่อง Badge สีเทาอ่อนขอบบางเรียบร้อยสวยงาม (ภาษาไทยคอมเมนต์)
                draw.rectangle([40, qr_h + 80, canvas_w - 40, qr_h + 115], fill="#f1f5f9", outline="#cbd5e1", width=1)
                plate_text = record.license_plate or "-"
                draw_centered_text(draw, qr_h + 85, plate_text, font_plate, "#1e293b", canvas_w)
                
                # 4. วาดกรอบ Alert Box สีแดงเตือนภัยขอบสีแดงสด สำหรับใส่ข้อความเตือนความปลอดภัยสีแดงให้สวยงามเด่นชัด (ภาษาไทยคอมเมนต์)
                draw.rectangle([15, qr_h + 130, canvas_w - 15, qr_h + 205], fill="#fef2f2", outline="#ef4444", width=2)
                
                # วาดป้ายเตือนการบันทึกรายการก่อน/หลังใช้งานรถแบบกึ่งกลางและใช้ฟอนต์ตัวหนาขนาด 20 สีแดงสด (#dc2626) (ภาษาไทยคอมเมนต์)
                warn_line1 = "กรุณาทำรายการในระบบ"
                warn_line2 = "ก่อนใช้งานและหลังใช้งานรถ"
                draw_centered_text(draw, qr_h + 143, warn_line1, font_warn, "#dc2626", canvas_w)
                draw_centered_text(draw, qr_h + 169, warn_line2, font_warn, "#dc2626", canvas_w)
                
                # บันทึกรูปภาพการ์ด QR เป็น PNG
                temp = io.BytesIO()
                canvas.save(temp, format="PNG")
                qr_image = base64.b64encode(temp.getvalue())
                record.qr_code_image = qr_image
            except Exception:
                # ป้องกันข้อผิดพลาดกรณีเกิดความล้มเหลวในการโหลด qrcode
                record.qr_code_image = False

    def _compute_current_borrow(self):
        for record in self:
            # ถ้ารถ "เสีย" ให้ถือว่าไม่ว่างทันที
            if record.vehicle_status in ('broken', 'repairing', 'retired'):
                record.current_borrow_id = False
                record.is_available = False
                continue

            borrow = self.env['vehicle.borrow.request'].search([
                ('vehicle_id', '=', record.id),
                ('state', 'in', ['request', 'approved', 'borrowed'])
            ], limit=1, order='create_date desc')
            record.current_borrow_id = borrow
            record.is_available = not borrow

class VehicleBorrowRequest(models.Model):
    """
    โมดูลจัดการการยืมรถ (Vehicle Borrowing Request)
    ใช้สำหรับบันทึกข้อมูลและสถานะการขอใช้งานยานพาหนะ
    """
    _name = 'vehicle.borrow.request'
    _description = 'Vehicle Borrowing Request'
    _inherit = ['mail.thread', 'mail.activity.mixin'] # รองรับระบบบันทึกประวัติและกิจกรรม (Chatter)
    _order = 'id desc'

    # ฟิลด์ข้อมูลพื้นฐาน
    name = fields.Char(string='เลขที่คำขอ', required=True, copy=False, readonly=True, index=True, default=lambda self: _('New'))
    employee_id = fields.Many2one('hr.employee', string='พนักงานผู้ยืม', required=True, tracking=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='ยานพาหนะ', required=True, tracking=True)
    date_start = fields.Datetime(string='วันที่เริ่มยืม', required=True, tracking=True)
    date_end = fields.Datetime(string='วันที่คืน', required=False, tracking=True)
    purpose = fields.Text(string='จุดประสงค์การยืม', required=True)
    
    # สถานะของคำขอจองรถ (ปรับเปลี่ยนคำแสดงผลของ request จาก "รออนุมัติ" เป็น "กำลังใช้งาน" ตามต้องการ)
    state = fields.Selection([
        ('draft', 'ฉบับร่าง'),
        ('request', 'กำลังใช้งาน'),
        ('approved', 'อนุมัติแล้ว'),
        ('borrowed', 'กำลังใช้งาน'),
        ('returned', 'คืนรถแล้ว'),
        ('cancelled', 'ยกเลิก')
    ], string='สถานะ', default='draft', tracking=True)
    active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        # ปรับปรุงให้รองรับ Odoo 19 ในรูปแบบ Multi-record (vals_list) เพื่อหลีกเลี่ยงข้อผิดพลาด 'list' object has no attribute 'get'
        # โดยทำการวนลูปประมวลผลข้อมูลแต่ละรายการใน list พร้อมค้นหา Sequence ตามโรงงาน (TQS, CKR, TPS)
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                seq_code = 'vehicle.borrow.request'
                vehicle_id = vals.get('vehicle_id')
                if vehicle_id:
                    vehicle = self.env['fleet.vehicle'].browse(vehicle_id)
                    if vehicle.exists() and vehicle.factory:
                        seq_code = f'vehicle.borrow.request.{vehicle.factory.lower()}'
                
                try:
                    vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')
                except Exception:
                    # ป้องกันการ Error หาก sequence ย่อยไม่มีอยู่จริง ให้ถอยกลับมาใช้ Sequence หลัก
                    vals['name'] = self.env['ir.sequence'].next_by_code('vehicle.borrow.request') or _('New')
        return super(VehicleBorrowRequest, self).create(vals_list)

    # ฟังก์ชันปุ่มกดเปลี่ยนสถานะงาน
    def action_request(self): self.write({'state': 'request'})   # ส่งคำขอ
    def action_approve(self): self.write({'state': 'approved'})  # อนุมัติ
    def action_borrow(self):  self.write({'state': 'borrowed'})  # รับรถ
    def action_return(self):
        self.write({
            'state': 'returned',
            'date_end': fields.Datetime.now(),
        })# คืนรถ
    def action_cancel(self):  self.write({'state': 'cancelled'}) # ยกเลิก

    @api.constrains('vehicle_id', 'state')
    def _check_vehicle_availability(self):
        """ 
        ฟังก์ชันตรวจสอบความว่างของรถ (Availability Check)
        ป้องกันการจองรถคันเดิมทับซ้อน หากรถคันนั้นยังไม่ถูกคืนหรือยกเลิก
        """
        for record in self:
            if record.vehicle_id.vehicle_status in ('broken', 'repairing', 'retired'):
                status_label = dict(record.vehicle_id._fields['vehicle_status'].selection).get(record.vehicle_id.vehicle_status, 'ไม่พร้อม')
                raise ValidationError(_('ขออภัย! รถคันนี้ไม่พร้อมใช้งาน (สถานะ: %s) กรุณาโปรดเลือกคันอื่น') % status_label)

            if record.state in ['request', 'approved', 'borrowed']:
                # ตรวจสอบว่ามีรายการอื่นที่ใช้รถคันนี้และยังไม่คืนหรือไม่
                domain = [
                    ('id', '!=', record.id),
                    ('vehicle_id', '=', record.vehicle_id.id),
                    ('state', 'in', ['request', 'approved', 'borrowed'])
                ]
                existing_request = self.search(domain, limit=1)
                if existing_request:
                    raise ValidationError(_('ขออภัย! รถคันนี้ถูกจองหรือกำลังใช้งานอยู่ (เลขที่คำขอ: %s) ไม่สามารถจองซ้ำได้จนกว่ารายการเดิมจะมีการคืนรถ') % existing_request.name)

    @api.constrains('date_start', 'date_end', 'vehicle_id')
    def _check_overlap(self):
        """ 
        ฟังก์ชันตรวจสอบการทับซ้อนของเวลา (เก็บไว้รองรับกรณีระบุเวลาคืนล่วงหน้าในอนาคต)
        """
        for record in self:
            if not record.date_end:
                continue

            domain = [
                ('id', '!=', record.id),
                ('vehicle_id', '=', record.vehicle_id.id),
                ('state', 'in', ['approved', 'borrowed']),
                ('date_end', '!=', False),
                '|', '|',
                '&', ('date_start', '<=', record.date_start), ('date_end', '>', record.date_start),
                '&', ('date_start', '<', record.date_end), ('date_end', '>=', record.date_end),
                '&', ('date_start', '>=', record.date_start), ('date_end', '<=', record.date_end)
            ]
            overlap = self.search_count(domain)
            if overlap > 0:
                raise ValidationError(_('รถคันนี้มีคนจองไว้แล้วในช่วงเวลาดังกล่าว'))
