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
    non_stock_parts = fields.Text(string='ข้อมูลอะไหล่นอกสต๊อก') # สำหรับกรอกอะไหล่นอกคลัง/ร้านภายนอก
    repair_cost = fields.Float(string='ค่าใช้จ่ายในการซ่อม')
    additional_cost = fields.Float(string='ค่าใช้จ่ายเพิ่มเติม') # สำหรับค่าแรงหรือค่าใช้จ่ายภายนอกอื่นๆ
    finish_date = fields.Datetime(string='วันที่ซ่อมเสร็จ')

    # ความสัมพันธ์กับประวัติการเบิกอะไหล่คลังและการดึงข้อมูลอัตโนมัติ
    movement_ids = fields.One2many('vehicle.spare.part.movement', 'repair_id', string='รายการอะไหล่ที่เบิกใช้')
    auto_parts_used = fields.Text(string='อะไหล่ที่เบิกจากคลัง (ระบบ)', compute='_compute_auto_parts_used')
    auto_parts_cost = fields.Float(string='ราคารวมอะไหล่ที่เบิกใช้ (ระบบ)', compute='_compute_auto_parts_cost') # คำนวณราคาอะไหล่อัตโนมัติ
    auto_parts_json = fields.Text(string='ข้อมูลอะไหล่เบิกคลัง (JSON)', compute='_compute_auto_parts_json') # ข้อมูล JSON สำหรับใช้ใน frontend
    repair_duration = fields.Char(string='ระยะเวลาที่ใช้ซ่อม', compute='_compute_repair_duration') # ฟิลด์สำหรับเก็บระยะเวลาที่ใช้ซ่อมบำรุง

    @api.depends('movement_ids', 'movement_ids.qty', 'movement_ids.unit_price')
    def _compute_auto_parts_cost(self):
        # รวมราคาของอะไหล่คลังที่ถูกเบิกมาผูกกับใบแจ้งซ่อมใบนี้ (move_type = 'out')
        for rec in self:
            moves = rec.movement_ids.filtered(lambda m: m.move_type == 'out')
            rec.auto_parts_cost = sum(m.qty * m.unit_price for m in moves)

    @api.depends('movement_ids', 'movement_ids.qty', 'movement_ids.part_id', 'movement_ids.unit_price', 'movement_ids.lot_number')
    def _compute_auto_parts_json(self):
        # รวบรวมข้อมูลอะไหล่คลังในรูปแบบ JSON string เพื่อส่งไปใช้งานจัดการลบ/คืนสต็อกที่หน้าเว็บ
        import json
        for rec in self:
            moves = rec.movement_ids.filtered(lambda m: m.move_type == 'out')
            parts_data = []
            for m in moves:
                parts_data.append({
                    'id': m.id,
                    'name': m.part_id.name,
                    'code': m.part_id.code or '',
                    'qty': m.qty,
                    'uom': m.part_id.uom or 'ชิ้น',
                    'lot': m.lot_number or '-',
                    'price': m.unit_price
                })
            rec.auto_parts_json = json.dumps(parts_data)

    @api.depends('movement_ids', 'movement_ids.qty', 'movement_ids.part_id')
    def _compute_auto_parts_used(self):
        # รวบรวมข้อมูลอะไหล่คลังที่ถูกเบิกมาผูกกับใบแจ้งซ่อมนี้เพื่อนำไปแสดงผลโดยอัตโนมัติ
        for rec in self:
            moves = rec.movement_ids.filtered(lambda m: m.move_type == 'out')
            if moves:
                parts_list = []
                for m in moves:
                    parts_list.append(f"- {m.part_id.name} ({m.part_id.code}) จำนวน {int(m.qty)} {m.part_id.uom or 'ชิ้น'} [ล็อต: {m.lot_number or '-'}]")
                rec.auto_parts_used = "\n".join(parts_list)
            else:
                rec.auto_parts_used = ""

    @api.depends('report_date', 'finish_date')
    def _compute_repair_duration(self):
        # คำนวณระยะเวลาระหว่างวันที่แจ้งและวันที่เสร็จสิ้น ออกมาในรูปแบบ วัน ชั่วโมง และนาที ภาษาไทย
        for rec in self:
            if rec.report_date and rec.finish_date:
                diff = rec.finish_date - rec.report_date
                days = diff.days
                hours, remainder = divmod(diff.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                
                parts = []
                if days > 0:
                    parts.append(f"{days} วัน")
                if hours > 0:
                    parts.append(f"{hours} ชั่วโมง")
                if minutes > 0:
                    parts.append(f"{minutes} นาที")
                
                rec.repair_duration = " ".join(parts) if parts else "น้อยกว่า 1 นาที"
            else:
                rec.repair_duration = "-"

    state = fields.Selection([
        ('reported', 'รอตรวจสอบ'),
        ('repairing', 'กำลังซ่อม'),
        ('done', 'ซ่อมเสร็จแล้ว'),
        ('cancelled', 'ยกเลิก'),
    ], string='สถานะ', default='reported', tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        # ปรับปรุงให้รองรับ Odoo 19 ในรูปแบบ Multi-record (vals_list) เพื่อป้องกันการ Error ตอนแจ้งซ่อม
        # ทำการวนลูปประมวลผลเพื่อตั้งเลขที่เอกสารตามโรงงาน TQS, CKR, TPS
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                seq_code = 'vehicle.repair.request'
                vehicle_id = vals.get('vehicle_id')
                if vehicle_id:
                    vehicle = self.env['fleet.vehicle'].browse(vehicle_id)
                    if vehicle.exists() and vehicle.factory:
                        seq_code = f'vehicle.repair.request.{vehicle.factory.lower()}'
                
                try:
                    vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')
                except Exception:
                    # กรณีหา Sequence ย่อยไม่เจอ ให้ถอยกลับมาใช้ Sequence หลัก
                    vals['name'] = self.env['ir.sequence'].next_by_code('vehicle.repair.request') or _('New')
        results = super().create(vals_list)
        # นำส่วนอัปเดตรถยนต์เป็น "กำลังซ่อม" ในฟังก์ชัน create ออก เพื่อให้รถยนต์ยังจองได้อยู่ จนกว่าช่างจะกดอนุมัติซ่อม
        return results

    def action_approve(self):
        """อนุมัติซ่อม → เปลี่ยนสถานะใบแจ้งซ่อมเป็น 'กำลังซ่อม' และปรับสถานะรถยนต์เป็น 'repairing' เพื่อล็อกไม่ให้จองได้"""
        for rec in self:
            rec.write({'state': 'repairing'})
            if rec.vehicle_id:
                rec.vehicle_id.sudo().write({'vehicle_status': 'repairing'})

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
