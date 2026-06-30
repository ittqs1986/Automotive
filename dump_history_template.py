with open('/home/ittqs/odoo-production/addons/tnw-addon/vehicle_borrow/views/website_templates.xml', 'r', encoding='utf-8') as f:
    content = f.read()
start_idx = content.find('<template id="admin_repair_history_template"')
end_idx = content.find('</template>', start_idx) + 11
print(content[start_idx:end_idx])
