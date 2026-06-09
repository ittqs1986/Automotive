import re

with open('/home/ittqs/odoo-production/addons/tnw-addon/vehicle_borrow/views/website_templates.xml', 'r', encoding='utf-8') as f:
    content = f.read()

start_idx = content.find('<template id="admin_repair_template"')
end_idx = content.find('</template>', start_idx)
template_content = content[start_idx:end_idx]

div_open = len(re.findall(r'<div\b[^>]*>', template_content))
div_close = len(re.findall(r'</div>', template_content))

print(f"Open: {div_open}, Close: {div_close}")

t_open = len(re.findall(r'<t\b[^>]*>', template_content))
t_close = len(re.findall(r'</t>', template_content))
print(f"t Open: {t_open}, t Close: {t_close}")

