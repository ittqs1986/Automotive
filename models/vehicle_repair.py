# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class VehicleRepairRequest(models.Model):
    """
    โมดูลบันทึกการแจ้งซ่อมรถ (Vehicle Repair Request)
    ใช้สำหรับบันทึกประวัติการส่งซ่อมและสถานะการซ่อมรถ
    """
    _name = 'vehicle.repair.request'
    _description = 'Vehicle Repair Request'
    _order = 'create_date desc'

    name = fields.Char(
        string='เลขที่แจ้งซ่อม', required=True, copy=False, readonly=True,
        index=True, default=lambda self: _('New')
    )
    vehicle_id = fields.Many2one('fleet.vehicle', string='รถยนต์', required=True, tracking=True)
    reported_by_id = fields.Many2one('res.users', string='ผู้แจ้งซ่อม', required=True,
                                     default=lambda self: self.env.user, tracking=True)
    report_date = fields.Datetime(string='วันที่แจ้งซ่อม', required=True,
                                   default=fields.Datetime.now)
    description = fields.Text(string='รายละเอียดอาการเสีย', required=True)
    repair_details = fields.Text(string='รายละเอียดการที่ซ่อม')
    parts_used = fields.Text(string='ข้อมูลอะไหล่ใช้ในการซ่อม')
    repair_cost = fields.Float(string='ค่าใช้จ่ายในการซ่อม')
    finish_date = fields.Datetime(string='วันที่ซ่อมเสร็จ')

    state = fields.Selection([
        ('repairing', 'กำลังซ่อม'),
        ('done', 'ซ่อมเสร็จแล้ว'),
        ('cancelled', 'ยกเลิก'),
    ], string='สถานะ', default='repairing', tracking=True)

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('vehicle.repair.request') or _('New')
        result = super().create(vals)
        # เมื่อแจ้งซ่อม ให้เปลี่ยนสถานะรถเป็น "กำลังซ่อม"
        if result.vehicle_id:
            result.vehicle_id.sudo().write({'vehicle_status': 'repairing'})
        return result

    def action_done(self, vals=None):
        """ซ่อมเสร็จ → คืนสถานะรถเป็น active"""
        for rec in self:
            update_data = {'state': 'done', 'finish_date': fields.Datetime.now()}
            if vals:
                update_data.update(vals)
            rec.write(update_data)
            rec.vehicle_id.sudo().write({'vehicle_status': 'active'})

    def action_cancel(self):
        """ยกเลิกการแจ้งซ่อม → คืนสถานะรถเป็น active"""
        for rec in self:
            rec.write({'state': 'cancelled'})
            rec.vehicle_id.sudo().write({'vehicle_status': 'active'})
