import re

filepath = '/home/ittqs/odoo-production/addons/tnw-addon/vehicle_borrow/views/website_templates.xml'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update the link in sidebar
content = content.replace(
    'href="/automotive/repair#repair_history_section"',
    'href="/automotive/repair/history"'
)

# 2. Extract Full Repair History Section
history_pattern = re.compile(r'(<!-- Full Repair History Section -->\s*<div class="row mt-5" id="repair_history_section" style="scroll-margin-top: 100px;">.*?</div>\s*</div>\s*</div>\s*</div>)', re.DOTALL)
history_match = history_pattern.search(content)
history_html = history_match.group(1) if history_match else ""

# 3. Extract Repair Detail Modal
detail_modal_pattern = re.compile(r'(<!-- Repair Detail Modal -->\s*<div class="modal fade" id="repairDetailModal" tabindex="-1">.*?</div>\s*</div>\s*</div>)', re.DOTALL)
detail_match = detail_modal_pattern.search(content)
detail_html = detail_match.group(1) if detail_match else ""

# 4. Extract Javascript for History and Repair Detail Modal
# We'll just grab the JS functions needed: fillRepairModal, repairDetailModalEl event, filter_vehicle_id event.
js_script = """
            <script type="text/javascript">
                document.addEventListener('DOMContentLoaded', function() {
                    if (window.repairDetailsJsonStr) {
                        try {
                            window.repairDetailsJson = JSON.parse(window.repairDetailsJsonStr);
                        } catch(e) {
                            console.error("Error parsing repairDetailsJson", e);
                            window.repairDetailsJson = {};
                        }
                    } else {
                        window.repairDetailsJson = {};
                    }

                    function fillRepairModal(repairId) {
                        let data = window.repairDetailsJson[String(repairId)];
                        if (!data) {
                            for (let key in window.repairDetailsJson) {
                                if (Number(key) === Number(repairId)) {
                                    data = window.repairDetailsJson[key];
                                    break;
                                }
                            }
                        }
                        if (!data) return;

                        document.getElementById('rd_vehicle').textContent = data.vehicle;
                        document.getElementById('rd_reporter').textContent = data.reporter;
                        document.getElementById('rd_repairman').textContent = data.repairman;
                        document.getElementById('rd_report_date').textContent = data.report_date;
                        document.getElementById('rd_finish_date').textContent = data.finish_date;
                        document.getElementById('rd_duration').textContent = data.duration;
                        document.getElementById('rd_description').textContent = data.description;
                        document.getElementById('rd_repair_details').textContent = data.repair_details;
                        document.getElementById('rd_labor_cost').textContent = parseFloat(data.labor_cost || 0).toLocaleString(undefined, {minimumFractionDigits: 2});
                        document.getElementById('rd_extra_cost').textContent = parseFloat(data.extra_cost || 0).toLocaleString(undefined, {minimumFractionDigits: 2});
                        document.getElementById('rd_total_cost').textContent = parseFloat(data.total_cost || 0).toLocaleString(undefined, {minimumFractionDigits: 2});

                        const partsList = data.parts || [];
                        const tbody = document.getElementById('rd_parts_tbody');
                        tbody.innerHTML = '';
                        if (partsList.length === 0) {
                            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted py-3">ไม่มีรายการเบิกอะไหล่</td></tr>';
                        } else {
                            partsList.forEach(function(p) {
                                const tr = document.createElement('tr');
                                tr.innerHTML = `
                                    <td><div class="fw-semibold text-dark">${p.name}</div></td>
                                    <td class="text-end">${p.qty} ${p.uom}</td>
                                    <td class="text-end">${parseFloat(p.price || 0).toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
                                    <td class="text-end fw-bold text-primary">${parseFloat(p.total || 0).toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
                                `;
                                tbody.appendChild(tr);
                            });
                        }

                        const partsTextDiv = document.getElementById('rd_parts_text');
                        if (data.parts_used_text &amp;&amp; data.parts_used_text !== '-') {
                            partsTextDiv.innerHTML = '<i class="fa fa-info-circle me-1"></i> บันทึกเพิ่มเติม: ' + data.parts_used_text;
                        } else {
                            partsTextDiv.innerHTML = '';
                        }
                    }

                    const repairDetailModalEl = document.getElementById('repairDetailModal');
                    if (repairDetailModalEl) {
                        repairDetailModalEl.addEventListener('show.bs.modal', function(event) {
                            const triggerEl = event.relatedTarget;
                            if (!triggerEl) return;
                            const repairId = triggerEl.getAttribute('data-id');
                            if (!repairId) return;
                            fillRepairModal(repairId);
                        });
                    }

                    const filterType = document.getElementById('filter_vehicle_type');
                    const filterVehicle = document.getElementById('filter_vehicle_id');
                    if (filterType &amp;&amp; filterVehicle) {
                        const allFilterOptions = Array.from(filterVehicle.options).slice(1);
                        filterType.addEventListener('change', function() {
                            const selectedType = this.value;
                            filterVehicle.innerHTML = '<option value="">-- ทั้งหมด --</option>';
                            allFilterOptions.forEach(function(opt) {
                                if (!selectedType || opt.getAttribute('data-type') === selectedType) {
                                    filterVehicle.appendChild(opt.cloneNode(true));
                                }
                            });
                        });
                    }
                });
            </script>
"""

new_template = f"""
    <!-- Admin Repair History Template -->
    <template id="admin_repair_history_template" name="Admin Repair History">
        <t t-call="vehicle_borrow.vb_layout">
            <div id="wrap" class="oe_structure oe_empty bg-light py-5">
                <div class="container pb-5">
                    {history_html.replace('id="repair_history_section" style="scroll-margin-top: 100px;"', '')}
                    {detail_html}
                </div>
            </div>
            <!-- Data from Controller -->
            <script type="text/javascript">
                window.repairDetailsJsonStr = `<t t-esc="repair_details_json"/>`;
            </script>
            {js_script}
        </t>
    </template>
"""

# Remove history and detail modal from old template
if history_html:
    content = content.replace(history_html, "")
if detail_html:
    content = content.replace(detail_html, "")

# Remove filter_vehicle_type script from old template
filter_script_pattern = re.compile(r'// ===== ระบบกรองประเภทรถในตัวกรองประวัติการซ่อม =====.*?}\s*}\s*', re.DOTALL)
content = filter_script_pattern.sub('', content)

# Append new template right before <record id="menu_vehicle_booking_website"
insert_pos = content.find('<!-- Nav Menu -->')
if insert_pos != -1:
    content = content[:insert_pos] + new_template + "\n    " + content[insert_pos:]
else:
    # Append before closing odoo
    content = content.replace('</odoo>', new_template + '\n</odoo>')

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("Template split successful.")
