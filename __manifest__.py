{
    'name': 'Vehicle Borrowing System',        # ชื่อโมดูล: ระบบยืมรถ
    'version': '2.65',                         # เวอร์ชัน 2.65: เพิ่มป้ายกำกับแจ้งเตือนสีแดง "X ใหม่" บนปุ่มเมนูหลัก จัดการงานซ่อม ในแถบ Sidebar เมื่อมีแจ้งซ่อมใหม่เข้ามา
    'category': 'Human Resources/Fleet',       # หมวดหมู่: ทรัพยากรบุคคลและยานพาหนะ
    'summary': 'ระบบยืม-คืนรถสำหรับพนักงาน',     # สรุป: ระบบจัดการการยืมรถภายในองค์กร
    'author': 'ittqs',                         # ผู้เขียน: ittqs
    'depends': ['base', 'fleet', 'hr', 'website'], # การขึ้นต่อกัน: พื้นฐาน, ยานพาหนะ, พนักงาน, เว็บไซต์
    'data': [                                  # ข้อมูลไฟล์ที่โหลดเข้าสู่ระบบ
        'security/vehicle_borrow_groups.xml',   # กลุ่มสิทธิ์ (Factory Groups)
        'security/vehicle_borrow_security.xml', # กฎความปลอดภัย (Record Rules)
        'security/ir.model.access.csv',        # ความปลอดภัยและสิทธิ์การเข้าถึง
        'data/sequence_data.xml',              # ระบบรันเลขเอกสารอัตโนมัติ
        'views/vehicle_borrow_views.xml',       # หน้าจอเมนูในระบบหลังบ้าน
        'views/vehicle_borrow_menus.xml',       # โครงสร้างเมนูทางลัด
        'views/website_templates.xml',         # หน้าตาเว็บไซต์สำหรับการจองออนไลน์
        'views/spare_parts_views.xml',          # ระบบจัดการอะไหล่
        'views/suggestion_templates.xml',       # หน้าจอระบบข้อเสนอแนะและ Admin Panel ของข้อเสนอแนะ
    ],
    'assets': {
        # โหลดใน frontend ทุกหน้า (รวม /web/login)
        'web.assets_frontend': [
            'vehicle_borrow/static/src/js/login_factory_selector.js',
        ],
        # โหลดใน backend ด้วย (ครอบคลุมกรณี portal/backend login)
        'web.assets_web': [
            'vehicle_borrow/static/src/js/login_factory_selector.js',
        ],
    },
    'installable': True,                      # ระบุว่าติดตั้งได้
    'application': True,                      # ระบุว่าเป็นแอปพลิเคชันหลัก
    'license': 'LGPL-3',                       # สิทธิบัตรการใช้งาน
}
