import re

filepath = '/home/ittqs/odoo-production/addons/tnw-addon/vehicle_borrow/views/website_templates.xml'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

full_modal = """
                <!-- Repair Detail Modal -->
                <div class="modal fade" id="repairDetailModal" tabindex="-1">
                    <div class="modal-dialog modal-lg">
                        <div class="modal-content border-0 shadow-lg rounded-4">
                            <div class="modal-header bg-primary text-white border-0 py-3">
                                <h5 class="modal-title fw-bold">
                                    <i class="fa fa-info-circle me-2"/> รายละเอียดการซ่อมเชิงลึก
                                </h5>
                                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body p-4">
                                <div class="row mb-4">
                                    <div class="col-md-6">
                                        <label class="small text-muted text-uppercase fw-bold">ข้อมูลรถยนต์</label>
                                        <div id="rd_vehicle" class="h5 fw-bold text-dark">-</div>
                                        <div id="rd_repair_no" class="text-muted small">-</div>
                                    </div>
                                    <div class="col-md-6 text-md-end">
                                        <div id="rd_state_badge"></div>
                                    </div>
                                </div>
                                <div class="card border-light bg-light rounded-3 mb-4">
                                    <div class="card-body">
                                        <div class="row g-3">
                                            <div class="col-6 col-md-3">
                                                <label class="extra-small text-muted text-uppercase">วันที่แจ้งซ่อม</label>
                                                <div id="rd_report_date" class="small fw-bold">-</div>
                                            </div>
                                            <div class="col-6 col-md-3">
                                                <label class="extra-small text-muted text-uppercase">วันที่ซ่อมเสร็จ</label>
                                                <div id="rd_finish_date" class="small fw-bold">-</div>
                                            </div>
                                            <div class="col-6 col-md-3">
                                                <label class="extra-small text-muted text-uppercase">ผู้แจ้งซ่อม</label>
                                                <div id="rd_reporter" class="small fw-bold">-</div>
                                            </div>
                                            <div class="col-6 col-md-3">
                                                <label class="extra-small text-muted text-uppercase">ผู้ซ่อม (Admin)</label>
                                                <div id="rd_repairman" class="small fw-bold text-primary">-</div>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <div class="mb-4">
                                    <h6 class="fw-bold border-start border-4 border-primary ps-2 mb-3">อาการเสียที่แจ้ง</h6>
                                    <p id="rd_description" class="p-3 bg-white border rounded-3 text-dark" style="white-space: pre-wrap;">-</p>
                                </div>

                                <div class="mb-4">
                                    <h6 class="fw-bold border-start border-4 border-success ps-2 mb-3">รายละเอียดการดำเนินงาน</h6>
                                    <p id="rd_repair_details" class="p-3 bg-white border rounded-3 text-dark" style="white-space: pre-wrap;">-</p>
                                    <div id="rd_parts_text" class="small text-muted italic mt-1"></div>
                                </div>

                                <div class="mb-4">
                                    <h6 class="fw-bold border-start border-4 border-warning ps-2 mb-3">รายการอะไหล่ที่เบิกใช้ (จากสต็อก)</h6>
                                    <div class="table-responsive">
                                        <table class="table table-sm table-hover align-middle">
                                            <thead class="bg-light">
                                                <tr>
                                                    <th>รายการอะไหล่</th>
                                                    <th class="text-center">จำนวน</th>
                                                    <th class="text-end">ราคา/หน่วย</th>
                                                    <th class="text-end">รวม</th>
                                                </tr>
                                            </thead>
                                            <tbody id="rd_parts_body">
                                                <!-- Dynamic Content -->
                                            </tbody>
                                        </table>
                                    </div>
                                </div>

                                <!-- อะไหล่อื่นๆเพิ่มเติม (นอกระบบสต็อก) -->
                                <div class="mb-4">
                                    <h6 class="fw-bold border-start border-4 border-info ps-2 mb-3">
                                        <i class="fa fa-plus-circle me-1 text-info"/>  อะไหล่อื่นๆเพิ่มเติม (นอกระบบสต็อก)
                                    </h6>
                                    <p id="rd_extra_parts" class="p-3 bg-white border rounded-3 text-dark mb-0" style="white-space: pre-wrap;">ไม่มีรายการ</p>
                                </div>
                            </div>
                            <!-- แถบสรุประยะเวลา + ราคารวม อยู่ใน modal-footer -->
                            <div class="modal-footer border-0 p-0">
                                <div class="d-flex flex-column gap-2 w-100 p-3 pt-0">
                                    <!-- แถวที่ 1: ระยะเวลา -->
                                    <div class="alert alert-warning border-0 shadow-sm w-100 py-3 mb-0" style="background: linear-gradient(135deg, #fef3c7, #fde68a);">
                                        <div class="extra-small text-uppercase fw-bold opacity-75 mb-1"><i class="fa fa-clock-o me-1"/>ระยะเวลาที่ใช้ซ่อมทั้งหมด</div>
                                        <div id="rd_duration" class="h5 mb-0 fw-bold" style="color:#92400e;">-</div>
                                    </div>
                                    <!-- แถวที่ 2: สรุปค่าใช้จ่าย breakdown -->
                                    <div class="rounded-3 p-3" style="background: linear-gradient(135deg, #1e3a5f, #1d4ed8);">
                                        <div class="d-flex justify-content-between mb-2">
                                            <span class="text-white-50 small">ค่าแรง / ค่าซ่อม</span>
                                            <span id="rd_labor_cost" class="text-white small fw-bold">฿ 0.00</span>
                                        </div>
                                        <div class="d-flex justify-content-between mb-2">
                                            <span class="text-white-50 small">รวมค่าอะไหล่ (จากสต็อก)</span>
                                            <span id="rd_parts_cost" class="text-white small fw-bold">฿ 0.00</span>
                                        </div>
                                        <div class="d-flex justify-content-between mb-2">
                                            <span class="text-white-50 small">ค่าใช้จ่ายเพิ่มเติม</span>
                                            <span id="rd_extra_cost" class="text-white small fw-bold">฿ 0.00</span>
                                        </div>
                                        <hr class="border-white-50 my-2"/>
                                        <div class="d-flex justify-content-between align-items-center">
                                            <span class="text-white fw-bold text-uppercase small"><i class="fa fa-money me-1"/>รวมค่าใช้จ่ายทั้งสิ้น</span>
                                            <div id="rd_total_cost" class="h4 mb-0 fw-bold text-white">-</div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                </div>
            </div>
"""

# Find the block to replace
start_idx = content.find('<!-- Repair Detail Modal -->', content.find('<template id="admin_repair_history_template"'))
end_idx = content.find('<!-- Data from Controller -->', start_idx)

if start_idx != -1 and end_idx != -1:
    content = content[:start_idx] + full_modal + "            " + content[end_idx:]
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed!")
else:
    print("Could not find blocks to replace.")
