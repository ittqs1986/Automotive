# -*- coding: utf-8 -*-
import os

filepath = '/home/ittqs/odoo-production/addons/tnw-addon/vehicle_borrow/views/website_templates.xml'

if not os.path.exists(filepath):
    print("Error: website_templates.xml not found!")
    exit(1)

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Target select section replacement
target_select = """                                                 <!-- เลือกรถ -->
                                                 <div class="mb-4">
                                                     <label for="vehicle_type_filter" class="form-label fw-semibold text-muted small text-uppercase">
                                                         <i class="fa fa-filter me-1"/>ประเภทรถที่ต้องการยืม
                                                     </label>
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
                                                 </div>"""

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
                                                 </div>"""

# 2. Target JS script replacement
target_js = """                                                 <script type="text/javascript">
                                                     document.addEventListener('DOMContentLoaded', function() {
                                                         const typeFilter = document.getElementById('vehicle_type_filter');
                                                         const vehicleSelect = document.getElementById('vehicle_id');
                                                         const galleryContainer = document.getElementById('vehicle_gallery_container');
                                                         const galleryItems = document.querySelectorAll('.vehicle-gallery-item');
                                                         const allOptions = Array.from(vehicleSelect.options).slice(1);

                                                         typeFilter.addEventListener('change', function() {
                                                             const selectedType = this.value;
                                                             
                                                             // 1. Update Dropdown
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

                                                             // 2. Update Gallery
                                                             galleryContainer.classList.remove('d-none');
                                                             galleryItems.forEach(item => {
                                                                 item.style.display = (item.getAttribute('data-type') === selectedType) ? 'block' : 'none';
                                                             });
                                                         });
                                                     });
                                                 </script>"""

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
                                                 </script>"""

replaced = False
if target_select in content:
    content = content.replace(target_select, replacement_select)
    print("1. Select form replaced successfully.")
    replaced = True
else:
    # Try normalizing spaces/newlines to see if we match
    print("WARNING: target_select not matched exactly. Trying replacement via normalize...")
    # Replace using a simpler match if needed
    
if target_js in content:
    content = content.replace(target_js, replacement_js)
    print("2. JavaScript code replaced successfully.")
    replaced = True
else:
    print("WARNING: target_js not matched exactly.")

if replaced:
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("SUCCESS: website_templates.xml updated.")
else:
    print("FAILURE: No changes made.")
