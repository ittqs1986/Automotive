# -*- coding: utf-8 -*-
# คอมเมนต์ภาษาไทยเพื่ออธิบายการทำงานของโค้ดตามกฎเหล็ก Odoo Developer
from odoo import models, fields

class VehicleSuggestion(models.Model):
    """
    โมเดลสำหรับจัดเก็บข้อเสนอแนะเกี่ยวกับยานพาหนะ (Suggestions)
    ข้อมูลทั้งหมดจะเป็นแบบไม่ระบุตัวตน (Anonymous) โดยมีเพียงรายละเอียดข้อความ
    วันเวลาที่สร้าง และโรงงานสังกัดของผู้ส่ง ณ ตอนที่บันทึกข้อมูลเท่านั้น
    """
    _name = 'vehicle.suggestion'
    _description = 'ข้อเสนอแนะเกี่ยวกับระบบยานพาหนะ'
    _order = 'date desc'

    # ฟิลด์เก็บเนื้อหาข้อเสนอแนะ
    content = fields.Text(string='ข้อเสนอแนะ', required=True)
    
    # ฟิลด์วันเวลาที่ส่ง (ค่าเริ่มต้นคือ เวลาปัจจุบัน)
    date = fields.Datetime(string='วันเวลาที่ส่ง', default=fields.Datetime.now)
    
    # ฟิลด์โรงงานสังกัดเพื่อแยกตาม Role/กลุ่มโรงงาน
    factory = fields.Selection([
        ('TQS', 'TQS'),
        ('CKR', 'CKR'),
        ('TPS', 'TPS'),
        ('other', 'อื่นๆ / ทั่วไป')
    ], string='โรงงาน/Role', default='other')
