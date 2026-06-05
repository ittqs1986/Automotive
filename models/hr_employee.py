# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class HrEmployee(models.Model):
    """
    สืบทอดโมเดลพนักงาน (hr.employee) เพื่อเพิ่มฟิลด์ระบุโรงงานและจัดการสิทธิ์
    สำหรับใช้งานร่วมกับระบบยืม-คืนรถ (Vehicle Borrowing System)
    """
    _inherit = 'hr.employee'

    # ฟิลด์ระบุโรงงานที่พนักงานสังกัด
    factory = fields.Selection([
        ('TQS', 'TQS'),
        ('CKR', 'CKR'),
        ('TPS', 'TPS'),
    ], string='โรงงาน', tracking=True)

    # ฟิลด์กำหนดสิทธิ์ในการใช้งานระบบยืมรถของพนักงาน
    vehicle_borrow_role = fields.Selection([
        ('none', 'ไม่มีสิทธิ์'),
        ('user_tqs', 'User Factory TQS'),
        ('user_ckr', 'User Factory CKR'),
        ('user_tps', 'User Factory TPS'),
        ('admin_tqs', 'Admin Factory TQS'),
        ('admin_ckr', 'Admin Factory CKR'),
        ('admin_tps', 'Admin Factory TPS'),
        ('head_admin', 'Head Admin'),
    ], string='สิทธิ์ระบบยืมรถ', default='none', tracking=True)

    @api.onchange('vehicle_borrow_role')
    def _onchange_vehicle_borrow_role(self):
        """
        เมื่อมีการเปลี่ยนบทบาท (Role) ระบบจะเลือกโรงงาน (Factory)
        ที่สอดคล้องกันให้โดยอัตโนมัติ เพื่ออำนวยความสะดวกให้ผู้ใช้งาน
        """
        if self.vehicle_borrow_role:
            role = self.vehicle_borrow_role
            if 'tqs' in role:
                self.factory = 'TQS'
            elif 'ckr' in role:
                self.factory = 'CKR'
            elif 'tps' in role:
                self.factory = 'TPS'

    @api.onchange('factory')
    def _onchange_factory(self):
        """
        เมื่อมีการเลือกหรือเปลี่ยนโรงงาน (Factory) และสิทธิ์เดิมเป็น 'ไม่มีสิทธิ์'
        ระบบจะตั้งค่าเริ่มต้นให้เป็นผู้ใช้งาน (User) ของโรงงานนั้นๆ ทันที
        """
        if self.factory and (self.vehicle_borrow_role == 'none' or not self.vehicle_borrow_role):
            if self.factory == 'TQS':
                self.vehicle_borrow_role = 'user_tqs'
            elif self.factory == 'CKR':
                self.vehicle_borrow_role = 'user_ckr'
            elif self.factory == 'TPS':
                self.vehicle_borrow_role = 'user_tps'

    def _sync_user_groups(self):
        """
        ฟังก์ชันสำหรับซิงโครไนซ์กลุ่มสิทธิ์ของ Odoo (res.users)
        ให้ตรงกับบทบาทการใช้งานของระบบยืมรถที่ถูกระบุไว้บนตัวพนักงาน
        """
        for employee in self:
            # ตรวจสอบว่าพนักงานคนนี้มีการผูกบัญชีผู้ใช้ระบบ (res.users) หรือไม่
            if not employee.user_id:
                continue
            
            user = employee.user_id
            
            # รายการกลุ่มสิทธิ์ของระบบยืมรถที่ต้องการจัดการถอดออกทั้งหมดก่อนเขียนใหม่
            all_groups_refs = [
                'vehicle_borrow.group_vb_head_admin',
                'vehicle_borrow.group_vb_admin_tqs',
                'vehicle_borrow.group_vb_admin_ckr',
                'vehicle_borrow.group_vb_admin_tps',
                'vehicle_borrow.group_vb_user_tqs',
                'vehicle_borrow.group_vb_user_ckr',
                'vehicle_borrow.group_vb_user_tps',
            ]
            
            remove_groups = []
            for ref in all_groups_refs:
                try:
                    grp = self.env.ref(ref)
                    if grp:
                        remove_groups.append(grp)
                except Exception:
                    continue
            
            # ทำความสะอาดสิทธิ์ยืมรถเดิมทั้งหมดออกจากบัญชีผู้ใช้
            if remove_groups:
                user.sudo().write({'group_ids': [(3, g.id) for g in remove_groups]})
                
            # ตารางจับคู่สิทธิ์ระบบยืมรถกับกลุ่มผู้ใช้ Odoo
            group_map = {
                'head_admin': 'vehicle_borrow.group_vb_head_admin',
                'admin_tqs': 'vehicle_borrow.group_vb_admin_tqs',
                'admin_ckr': 'vehicle_borrow.group_vb_admin_ckr',
                'admin_tps': 'vehicle_borrow.group_vb_admin_tps',
                'user_tqs': 'vehicle_borrow.group_vb_user_tqs',
                'user_ckr': 'vehicle_borrow.group_vb_user_ckr',
                'user_tps': 'vehicle_borrow.group_vb_user_tps',
            }
            
            # บันทึกกลุ่มสิทธิ์ใหม่ให้กับบัญชีผู้ใช้ที่เกี่ยวข้อง
            if employee.vehicle_borrow_role in group_map:
                try:
                    target_group = self.env.ref(group_map[employee.vehicle_borrow_role])
                    if target_group:
                        user.sudo().write({'group_ids': [(4, target_group.id)]})
                except Exception as e:
                    _logger.error("เกิดข้อผิดพลาดในการเชื่อมโยงสิทธิ์ %s ให้กับผู้ใช้ %s: %s", 
                                  group_map[employee.vehicle_borrow_role], user.login, str(e))

    @api.model_create_multi
    def create(self, vals_list):
        # รันขั้นตอนสร้างพนักงานหลักในระบบ Odoo
        employees = super(HrEmployee, self).create(vals_list)
        # เรียกใช้งานการซิงโครไนซ์สิทธิ์พนักงานไปยังบัญชี res.users
        employees._sync_user_groups()
        return employees

    def write(self, vals):
        # บันทึกข้อมูลแก้ไขข้อมูลพนักงานหลักในระบบ Odoo
        res = super(HrEmployee, self).write(vals)
        # หากมีการแก้ไขบทบาทหรือผูกบัญชีผู้ใช้ใหม่ ให้ดำเนินการซิงโครไนซ์สิทธิ์กลุ่มผู้ใช้ทันที
        if 'vehicle_borrow_role' in vals or 'user_id' in vals:
            self._sync_user_groups()
        return res
