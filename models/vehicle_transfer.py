# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

FACTORY_SELECTION = [
    ('TQS', 'TQS'),
    ('CKR', 'CKR'),
    ('TPS', 'TPS'),
]

class VehicleTransferRequest(models.Model):
    _name = 'vehicle.transfer.request'
    _description = 'Vehicle Transfer Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='เลขที่ส่งย้าย', required=True, copy=False, readonly=True, index=True, default=lambda self: _('New'))
    vehicle_id = fields.Many2one('fleet.vehicle', string='ยานพาหนะ', required=True, tracking=True)
    from_factory = fields.Selection(FACTORY_SELECTION, string='จากโรงงานเดิม', readonly=True)
    to_factory = fields.Selection(FACTORY_SELECTION, string='ไปโรงงานใหม่', required=True)
    reason = fields.Text(string='เหตุผลในการโยกย้าย')
    
    requester_id = fields.Many2one('res.users', string='ผู้ส่งย้าย', default=lambda self: self.env.user, readonly=True)
    date_requested = fields.Datetime(string='วันที่ส่งเรื่อง', default=fields.Datetime.now, readonly=True)
    
    approver_id = fields.Many2one('res.users', string='ผู้อนุมัติ (Head Admin)', readonly=True)
    date_approved = fields.Datetime(string='วันที่อนุมัติ', readonly=True)
    
    receiver_id = fields.Many2one('res.users', string='ผู้ตอบรับ', readonly=True)
    date_accepted = fields.Datetime(string='วันที่ตอบรับ', readonly=True)
    
    state = fields.Selection([
        ('draft', 'ฉบับร่าง'),
        ('requested', 'รอการอนุมัติ'),
        ('approved', 'รอการตอบรับ'),
        ('accepted', 'ตอบรับเรียบร้อย'),
        ('cancelled', 'ยกเลิก')
    ], string='สถานะ', default='draft', tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        # ปรับปรุงให้รองรับ Odoo 19 ในรูปแบบ Multi-record (vals_list)
        # ทำการวนลูปตั้งค่าเลขเอกสารและโรงงานเริ่มต้นของรถยนต์ทุกรายการ
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('vehicle.transfer.request') or _('New')
            
            # ตรวจสอบ Factory ปัจจุบัน ของรถที่ต้องการโยกย้าย
            if 'vehicle_id' in vals:
                vehicle = self.env['fleet.vehicle'].browse(vals['vehicle_id'])
                vals['from_factory'] = vehicle.factory
                
        return super(VehicleTransferRequest, self).create(vals_list)

    def action_request(self):
        self.write({'state': 'requested'})

    def action_approve(self):
        # ตรวจสอบสิทธิ์ Head Admin (ถ้าไม่ได้เช็คใน Controller ให้เช็คใน Model ด้วย)
        if not self.env.user.has_group('vehicle_borrow.group_vb_head_admin'):
            raise ValidationError(_("เฉพาะ Head Admin เท่านั้นที่สามารถอนุมัติได้"))
            
        for record in self:
            if record.state != 'requested':
                continue
                
            record.write({
                'state': 'approved',
                'approver_id': self.env.user.id,
                'date_approved': fields.Datetime.now()
            })

    def action_accept(self):
        for record in self:
            if record.state != 'approved':
                continue
                
            record.write({
                'state': 'accepted',
                'receiver_id': self.env.user.id,
                'date_accepted': fields.Datetime.now()
            })
            # ทำการโยกย้ายโรงงานจริงเมื่อยอมรับ
            record.vehicle_id.sudo().write({'factory': record.to_factory})

    def action_cancel(self):
        self.write({'state': 'cancelled'})
