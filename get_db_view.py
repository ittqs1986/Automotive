# -*- coding: utf-8 -*-
import odoo
from odoo.tools import config
config['db_host'] = 'db'
config['db_port'] = 5432
config['db_user'] = 'ittqs'
config['db_password'] = 'Tqs@12345'

from odoo.modules.registry import Registry

reg = Registry('it-tqs')
with reg.cursor() as cr:
    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
    views = env['ir.ui.view'].search([('key', '=', 'vehicle_borrow.booking_form_template')])
    for v in views:
        arch = v.arch_db or v.arch
        with open("/mnt/extra-addons/tnw-addon/vehicle_borrow/db_view_arch.txt", "w", encoding="utf-8") as f:
            f.write(arch)
        print("Wrote view to db_view_arch.txt successfully.")
