with open('/home/ittqs/odoo-production/addons/tnw-addon/vehicle_borrow/views/website_templates.xml', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = False

for i, line in enumerate(lines):
    # lines array is 0-indexed. line 1976 is index 1975
    # line 2019 is index 2018
    # line 2046 is index 2045
    # line 2049 is index 2048
    
    if 1975 <= i <= 2018:
        continue
    
    if 2045 <= i <= 2048:
        continue
        
    new_lines.append(line)

with open('/home/ittqs/odoo-production/addons/tnw-addon/vehicle_borrow/views/website_templates.xml', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("XML fixed.")
