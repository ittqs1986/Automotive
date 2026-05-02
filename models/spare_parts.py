# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class VehicleSparePartCategory(models.Model):
    _name = 'vehicle.spare.part.category'
    _description = 'Spare Part Category'

    name = fields.Char(string='หมวดหมู่อะไหล่', required=True)

class VehicleSparePart(models.Model):
    _name = 'vehicle.spare.part'
    _description = 'Spare Part'

    name = fields.Char(string='ชื่ออะไหล่', required=True)
    code = fields.Char(string='รหัสอะไหล่')
    factory = fields.Selection([
        ('TQS', 'TQS'),
        ('CKR', 'CKR'),
        ('TPS', 'TPS'),
    ], string='โรงงาน', required=True, default='TQS',
       help='โรงงานที่เป็นเจ้าของคลังอะไหล่นี้')
    category_id = fields.Many2one('vehicle.spare.part.category', string='หมวดหมู่')
    uom = fields.Char(string='หน่วยนับ', default='ชิ้น')
    image = fields.Image(string='รูปภาพ')
    description = fields.Text(string='รายละเอียด/หมายเหตุ')
    min_qty = fields.Float(string='จำนวนขั้นต่ำที่ควรมี', default=1.0)
    active = fields.Boolean(string='ใช้งานอยู่', default=True)
    
    qty_on_hand = fields.Float(string='จำนวนคงเหลือ', compute='_compute_qty_on_hand', store=True)
    
    movement_ids = fields.One2many('vehicle.spare.part.movement', 'part_id', string='ประวัติการรับเข้า-เบิกออก')

    @api.depends('movement_ids.qty', 'movement_ids.move_type')
    def _compute_qty_on_hand(self):
        for rec in self:
            total_in = sum(rec.movement_ids.filtered(lambda m: m.move_type == 'in').mapped('qty'))
            total_out = sum(rec.movement_ids.filtered(lambda m: m.move_type == 'out').mapped('qty'))
            rec.qty_on_hand = total_in - total_out

class VehicleSparePartMovement(models.Model):
    _name = 'vehicle.spare.part.movement'
    _description = 'Spare Part Movement Log'
    _order = 'date desc, id desc'

    part_id = fields.Many2one('vehicle.spare.part', string='อะไหล่', required=True, ondelete='cascade')
    factory = fields.Selection([
        ('TQS', 'TQS'),
        ('CKR', 'CKR'),
        ('TPS', 'TPS'),
    ], string='โรงงาน', related='part_id.factory', store=True, readonly=True,
       help='โรงงานที่เกี่ยวข้องกับการเคลื่อนไหวนี้ (อ้างอิงจากอะไหล่)')
    date = fields.Datetime(string='วันที่รายการ', default=fields.Datetime.now, required=True)
    move_type = fields.Selection([
        ('in', 'รับเข้า (Receive)'),
        ('out', 'เบิกออก (Issue)')
    ], string='ประเภทรายการ', required=True)
    qty = fields.Float(string='จำนวน', required=True, default=1.0)
    reference = fields.Char(string='เลขที่อ้างอิง/หมายเหตุ')
    
    # สำหรับการเบิกออก
    vehicle_id = fields.Many2one('fleet.vehicle', string='รถที่นำไปใช้')
    repair_id = fields.Many2one('vehicle.repair.request', string='ใบแจ้งซ่อม')
    user_id = fields.Many2one('res.users', string='ผู้บันทึก', default=lambda self: self.env.user, readonly=True)

    # ข้อมูลเพิ่มเติมสำหรับการรับเข้า
    lot_number = fields.Char(string='ล็อตการผลิต')
    unit_price = fields.Float(string='ราคาต่อหน่วย (บาท)')

    @api.constrains('qty')
    def _check_qty(self):
        for rec in self:
            if rec.qty <= 0:
                raise ValidationError(_("จำนวนต้องมากกว่า 0"))

    @api.model
    def create(self, vals):
        if vals.get('move_type') == 'out':
            part = self.env['vehicle.spare.part'].browse(vals.get('part_id'))
            if part.qty_on_hand < vals.get('qty', 0):
                raise ValidationError(_("สินค้าคงเหลือไม่เพียงพอ (คงเหลือ %s %s)") % (part.qty_on_hand, part.uom or ''))
        return super().create(vals)
