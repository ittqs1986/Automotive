# -*- coding: utf-8 -*-
import os

filepath = '/home/ittqs/odoo-production/addons/tnw-addon/vehicle_borrow/views/website_templates.xml'

if not os.path.exists(filepath):
    print("Error: website_templates.xml not found!")
    exit(1)

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 1. Replace the select dropdown block (lines 657 to 682, which corresponds to 0-indexed index 656 to 681)
# Let's verify what the lines are
print("REPLACING SELECT BLOCK:")
print("START LINE:", repr(lines[656]))
print("END LINE:", repr(lines[681]))

replacement_select = """                                                 <!-- เลือกรถ (ภาษาไทยคอมเมนต์) -->
                                                 <div class="mb-4">
                                                     <div class="d-flex justify-content-between align-items-center mb-2">
                                                         <label for="vehicle_type_filter" class="form-label fw-semibold text-muted small text-uppercase mb-0">
                                                             <i class="fa fa-filter me-1"/>ประเภทรถที่ต้องการยืม
                                                         </label>
                                                         <!-- ปุ่มสำหรับเปิดกล้องสแกน QR Code (ภาษาไทยคอมเมนต์) -->
                                                         <button type="button" id="btn-scan-qr" class="btn btn-sm btn-outline-warning d-flex align-items-center gap-2 py-1 px-3 rounded-pill text-dark fw-bold border-2" data-bs-toggle="modal" data-bs-target="#qrScanModal" style="background-color: #ffc107; border-color: #ffc107;">
                                                             <i class="fa fa-qrcode"/> สแกน QR Code เลือกรถ
                                                         </button>
                                                     </div>
                                                     <select id="vehicle_type_filter" class="form-select form-select-lg mb-3 bg-light" required="1">
                                                         <option value="">-- กรุณาเลือกประเภทรถ --</option>
                                                         <t t-foreach="vehicle_types" t-as="vt">
                                                             <option t-att-value="vt"><t t-esc="vt"/></option>
                                                         </t>
                                                     </select>
                                                     
                                                     <label for="vehicle_id" class="form-label fw-semibold text-muted small text-uppercase">
                                                         <i class="fa fa-car me-1"/>รถที่ต้องการยืม (เลือกประเภทรถก่อน)
                                                     </label>
                                                     <select name="vehicle_id" id="vehicle_id" class="form-select form-select-lg" required="1" disabled="1">
                                                         <option value="">-- กรุณาเลือกรถ --</option>
                                                         <t t-foreach="vehicles" t-as="car">
                                                             <option t-att-value="car.id" 
                                                                     t-att-data-type="car.model_id.name"
                                                                     t-att-selected="post.get('vehicle_id') == str(car.id) if post else False">
                                                                 <t t-esc="car.model_id.name"/> — [<t t-esc="car.license_plate"/>]
                                                             </option>
                                                         </t>
                                                     </select>
                                                 </div>
"""

# Replace lines index 656 to 681 (inclusive, so range is lines[656:682])
# Since we are modifying list in place, let's make sure the script runs correctly
# 682 is the index of `</div>`
lines[656:682] = [replacement_select]

# 2. Replace the script block (now the indices have changed because we replaced 26 lines with 1 multiline string)
# Let's write the file first with the select block replaced, then reload it and find the script indices!
with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print("Select block updated successfully.")

# Reload and find script boundaries
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

script_start_idx = None
script_end_idx = None
for idx, line in enumerate(lines):
    if '<script type="text/javascript">' in line and idx > 650:
        script_start_idx = idx
        break

if script_start_idx is not None:
    for idx in range(script_start_idx, len(lines)):
        if '</script>' in lines[idx]:
            script_end_idx = idx
            break

if script_start_idx is not None and script_end_idx is not None:
    print(f"REPLACING JS SCRIPT BLOCK (from line {script_start_idx+1} to {script_end_idx+1}):")
    print("START LINE:", repr(lines[script_start_idx]))
    print("END LINE:", repr(lines[script_end_idx]))
    
    replacement_js = """                                                 <script type="text/javascript">
                                                     document.addEventListener('DOMContentLoaded', function() {
                                                         const typeFilter = document.getElementById('vehicle_type_filter');
                                                         const vehicleSelect = document.getElementById('vehicle_id');
                                                         const galleryContainer = document.getElementById('vehicle_gallery_container');
                                                         const galleryItems = document.querySelectorAll('.vehicle-gallery-item');
                                                         const allOptions = Array.from(vehicleSelect.options).slice(1);

                                                         // ฟังก์ชันสำหรับอัปเดตตัวเลือกยานพาหนะตามประเภทรถที่เลือก (ภาษาไทยคอมเมนต์)
                                                         function updateVehicleOptions(selectedType) {
                                                             vehicleSelect.innerHTML = '<option value="">-- กรุณาเลือกรถ --</option>';
                                                             if (!selectedType) {
                                                                 vehicleSelect.disabled = true;
                                                                 galleryContainer.classList.add('d-none');
                                                                 return;
                                                             }

                                                             let found = false;
                                                             allOptions.forEach(opt => {
                                                                 if (opt.getAttribute('data-type') === selectedType) {
                                                                     vehicleSelect.appendChild(opt);
                                                                     found = true;
                                                                 }
                                                             });
                                                             vehicleSelect.disabled = !found;

                                                             // จัดการการแสดงรูปภาพแกลลอรี่ด้านล่าง (ภาษาไทยคอมเมนต์)
                                                             galleryContainer.classList.remove('d-none');
                                                             galleryItems.forEach(item => {
                                                                 item.style.display = (item.getAttribute('data-type') === selectedType) ? 'block' : 'none';
                                                             });
                                                         }

                                                         typeFilter.addEventListener('change', function() {
                                                             updateVehicleOptions(this.value);
                                                         });

                                                         // --- ระบบกล้องและสแกน QR Code (ภาษาไทยคอมเมนต์) ---
                                                         let html5QrCode;
                                                         const qrModal = document.getElementById('qrScanModal');
                                                         const qrReaderResults = document.getElementById('qr-reader-results');

                                                         if (qrModal) {
                                                             // เมื่อหน้าต่าง Modal แสดง ให้เริ่มการใช้งานกล้องถ่ายรูป (ภาษาไทยคอมเมนต์)
                                                             qrModal.addEventListener('shown.bs.modal', function () {
                                                                 html5QrCode = new Html5Qrcode("qr-reader");
                                                                 const qrCodeSuccessCallback = (decodedText, decodedResult) => {
                                                                     console.log("สแกนสำเร็จ:", decodedText);
                                                                     try {
                                                                         const url = new URL(decodedText);
                                                                         const vehicleId = url.searchParams.get("scan_vehicle_id") || url.searchParams.get("vehicle_id");
                                                                         if (vehicleId) {
                                                                             const targetOpt = allOptions.find(opt => opt.value === vehicleId);
                                                                             if (targetOpt) {
                                                                                 const vehicleType = targetOpt.getAttribute('data-type');
                                                                                 if (vehicleType) {
                                                                                     typeFilter.value = vehicleType;
                                                                                     updateVehicleOptions(vehicleType);
                                                                                     vehicleSelect.value = vehicleId;
                                                                                     
                                                                                     if (qrReaderResults) {
                                                                                         qrReaderResults.className = "mt-3 text-success fw-bold";
                                                                                         qrReaderResults.innerText = "สแกนสำเร็จ: ระบบกำลังเลือกยานพาหนะให้...";
                                                                                     }
                                                                                     
                                                                                     // ปิดสแกนเนอร์และปิด Modal (ภาษาไทยคอมเมนต์)
                                                                                     stopScanner().then(() => {
                                                                                         const modalInstance = bootstrap.Modal.getInstance(qrModal);
                                                                                         if (modalInstance) {
                                                                                             modalInstance.hide();
                                                                                         }
                                                                                     });
                                                                                 }
                                                                             } else {
                                                                                 if (qrReaderResults) {
                                                                                     qrReaderResults.className = "mt-3 text-danger fw-bold";
                                                                                     qrReaderResults.innerText = "ไม่พบยานพาหนะคันนี้ในรายการที่ว่าง/พร้อมใช้";
                                                                                 }
                                                                             }
                                                                         } else {
                                                                             if (qrReaderResults) {
                                                                                 qrReaderResults.className = "mt-3 text-warning fw-bold";
                                                                                 qrReaderResults.innerText = "รหัส QR Code นี้ไม่พบรหัสรถยนต์";
                                                                             }
                                                                         }
                                                                     } catch (e) {
                                                                         if (qrReaderResults) {
                                                                             qrReaderResults.className = "mt-3 text-danger fw-bold";
                                                                             qrReaderResults.innerText = "ลิงก์หรือรูปภาพ QR Code ไม่ถูกต้อง";
                                                                         }
                                                                     }
                                                                 };
                                                                 
                                                                 const config = { fps: 10, qrbox: { width: 220, height: 220 } };
                                                                 html5QrCode.start({ facingMode: "environment" }, config, qrCodeSuccessCallback)
                                                                     .catch((err) => {
                                                                         console.error("ไม่สามารถเริ่มการสแกนได้:", err);
                                                                         document.getElementById('qr-reader').innerHTML = `
                                                                             <div class="text-danger p-4 text-center">
                                                                                 <i class="fa fa-exclamation-triangle fa-2x mb-2"></i><br>
                                                                                 ไม่สามารถเปิดกล้องได้ หรือไม่มีสิทธิ์เข้าถึงกล้อง
                                                                             </div>`;
                                                                     });
                                                             });

                                                             // ฟังก์ชันสำหรับปิดการทำงานของกล้องสแกน (ภาษาไทยคอมเมนต์)
                                                             function stopScanner() {
                                                                 if (html5QrCode && html5QrCode.isScanning) {
                                                                     return html5QrCode.stop().then(() => {
                                                                         html5QrCode.clear();
                                                                         if (qrReaderResults) qrReaderResults.innerText = "";
                                                                     });
                                                                 }
                                                                 return Promise.resolve();
                                                             }

                                                             // ปิดการใช้กล้องเมื่อปิด Modal (ภาษาไทยคอมเมนต์)
                                                             qrModal.addEventListener('hidden.bs.modal', function () {
                                                                 stopScanner();
                                                             });
                                                         }

                                                         // --- จัดการค่าจากพารามิเตอร์ URL (ภาษาไทยคอมเมนต์) ---
                                                         const urlParams = new URLSearchParams(window.location.search);
                                                         const preSelectedId = urlParams.get('vehicle_id') || urlParams.get('scan_vehicle_id');
                                                         if (preSelectedId) {
                                                             const targetOpt = allOptions.find(opt => opt.value === preSelectedId);
                                                             if (targetOpt) {
                                                                 const vehicleType = targetOpt.getAttribute('data-type');
                                                                 if (vehicleType) {
                                                                     typeFilter.value = vehicleType;
                                                                     updateVehicleOptions(vehicleType);
                                                                     vehicleSelect.value = preSelectedId;
                                                                 }
                                                             }
                                                         }
                                                     });
                                                 </script>
"""
    lines[script_start_idx:script_end_idx+1] = [replacement_js]
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print("JS script block updated successfully.")
else:
    print("Error: Could not find script boundaries.")
