# -*- coding: utf-8 -*-
with open('/home/ittqs/odoo-production/addons/tnw-addon/vehicle_borrow/views/website_templates.xml', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for idx in range(650, 725):
    if idx < len(lines):
        print(f"{idx+1}: {repr(lines[idx])}")
