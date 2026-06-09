import re

with open('/home/ittqs/odoo-production/addons/tnw-addon/vehicle_borrow/views/website_templates.xml', 'r', encoding='utf-8') as f:
    content = f.read()

start_idx = content.find('<template id="admin_repair_history_template"')
end_idx = content.find('</template>', start_idx)

lines = content[start_idx:end_idx].split('\n')

open_count = 0
for i, line in enumerate(lines):
    opens = len(re.findall(r'<div\b[^>]*>', line))
    closes = len(re.findall(r'</div>', line))
    
    # Also check <t> and </t>
    # Note: self closing <t />
    t_opens = len(re.findall(r'<t\b[^>]*>', line)) - len(re.findall(r'<t\b[^>]*/>', line))
    t_closes = len(re.findall(r'</t>', line))
    
    open_count += opens - closes
    print(f"Line {i} ({opens} open, {closes} close) -> open_count: {open_count}")

print(f"Final open_count: {open_count}")
