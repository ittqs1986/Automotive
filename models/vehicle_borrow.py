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
    
    # สถานะของคำขอจองรถ
    state = fields.Selection([
        ('draft', 'ฉบับร่าง'),
        ('request', 'รออนุมัติ'),
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
