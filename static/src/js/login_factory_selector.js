/**
 * Vehicle Borrow - Login Factory Selector
 * - Injects factory selection buttons (TQS / CKR / TPS) into Odoo's /web/login page.
 * - Injects a hidden <input name="factory"> so the value is submitted with the login form POST.
 * - Reads ?factory_error=1 URL param and shows an error banner when factory mismatch occurs.
 */
(function () {
    'use strict';

    var FACTORIES = [
        { id: 'TQS', label: 'TQS', color: '#16a34a', shadow: 'rgba(22,163,74,0.3)' },
        { id: 'CKR', label: 'CKR', color: '#880808', shadow: 'rgba(136,8,8,0.3)' },
        { id: 'TPS', label: 'TPS', color: '#ebd13fff', shadow: 'rgba(217,119,6,0.3)' },
    ];
    var LS_KEY = 'vb_selected_factory';

    function isLoginPage() {
        var path = window.location.pathname;
        return path === '/web/login' || path === '/web/login/' ||
            path === '/odoo/login' || path.endsWith('/login');
    }

    function getSelectedFactory() {
        return window.localStorage.getItem(LS_KEY) || '';
    }

    function setSelectedFactory(factory) {
        window.localStorage.setItem(LS_KEY, factory);
    }

    function getUrlParam(name) {
        var params = new URLSearchParams(window.location.search);
        return params.get(name) || '';
    }

    /* ------------------------------------------------------------------ */
    /*  Build the factory error banner (shown when ?factory_error=1)       */
    /* ------------------------------------------------------------------ */
    function buildErrorBannerHTML(selectedFactory) {
        var factoryLabel = selectedFactory ? (' "' + selectedFactory + '"') : '';
        return '<div id="vb_factory_error_banner" style="' +
            'background:#fee2e2;border:1.5px solid #fca5a5;border-radius:8px;' +
            'padding:12px 16px;margin-bottom:16px;text-align:center;' +
            'color:#b91c1c;font-size:13px;font-weight:600;">' +
            '<span style="margin-right:6px;">⚠️</span>' +
            'เลือกโรงงานไม่ถูกต้อง' + factoryLabel + '<br>' +
            '<span style="font-weight:400;font-size:12px;color:#991b1b;">' +
            'กรุณาเลือกโรงงานที่คุณมีสิทธิ์เข้าใช้งาน แล้วลองเข้าสู่ระบบใหม่อีกครั้ง' +
            '</span></div>';
    }

    /* ------------------------------------------------------------------ */
    /*  Build the factory selector widget HTML                             */
    /* ------------------------------------------------------------------ */
    function buildSelectorHTML() {
        var html = '<div id="vb_factory_selector" style="' +
            'margin-bottom:20px;padding:16px 0 4px;' +
            'border-bottom:1px solid #e5e7eb;text-align:center;">' +
            '<p style="font-size:11px;font-weight:700;letter-spacing:1px;' +
            'color:#6b7280;text-transform:uppercase;margin-bottom:12px;">' +
            '<span style="margin-right:6px;">🏭</span>เลือกโรงงานของคุณ</p>' +
            '<div style="display:flex;gap:10px;justify-content:center;margin-bottom:10px;">';

        FACTORIES.forEach(function (f) {
            html += '<button type="button" id="vbf_btn_' + f.id.toLowerCase() + '" ' +
                'data-factory="' + f.id + '" ' +
                'onclick="vbSelectFactory(\'' + f.id + '\')" ' +
                'style="' +
                'flex:1;max-width:100px;padding:10px 0;' +
                'border:2px solid ' + f.color + ';' +
                'background:transparent;color:' + f.color + ';' +
                'font-weight:700;font-size:14px;border-radius:8px;' +
                'cursor:pointer;transition:all 0.2s;" ' +
                'onmouseover="this.style.opacity=\'0.85\'" ' +
                'onmouseout="this.style.opacity=\'1\'">' +
                f.label + '</button>';
        });

        html += '</div><div id="vbf_selected_label" style="' +
            'font-size:12px;color:#6b7280;min-height:18px;margin-top:2px;"></div></div>';

        return html;
    }

    /* ------------------------------------------------------------------ */
    /*  Factory select action: update UI + sync hidden input               */
    /* ------------------------------------------------------------------ */
    window.vbSelectFactory = function (factory) {
        setSelectedFactory(factory);

        // Sync hidden input in form
        var hidden = document.getElementById('vb_factory_hidden');
        if (hidden) hidden.value = factory;

        // Update button styles
        FACTORIES.forEach(function (f) {
            var btn = document.getElementById('vbf_btn_' + f.id.toLowerCase());
            if (!btn) return;
            if (f.id === factory) {
                btn.style.background = f.color;
                btn.style.color = '#fff';
                btn.style.boxShadow = '0 0 0 3px ' + f.shadow;
            } else {
                btn.style.background = 'transparent';
                btn.style.color = f.color;
                btn.style.boxShadow = 'none';
            }
        });

        // Update label
        var label = document.getElementById('vbf_selected_label');
        if (label) {
            label.innerHTML = '<span style="color:#16a34a;margin-right:4px;">✓</span>' +
                'โรงงานที่เลือก: <strong>' + factory + '</strong>';
        }
    };

    /* ------------------------------------------------------------------ */
    /*  Inject hidden <input name="factory"> into the login form           */
    /* ------------------------------------------------------------------ */
    function injectHiddenInput(form) {
        if (document.getElementById('vb_factory_hidden')) return;
        var input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'factory';
        input.id = 'vb_factory_hidden';
        input.value = getSelectedFactory();
        form.appendChild(input);
    }

    /* ------------------------------------------------------------------ */
    /*  Inject the full selector + error banner (if needed) into the page  */
    /* ------------------------------------------------------------------ */
    function injectSelector() {
        if (document.getElementById('vb_factory_selector')) return;

        // Find the login form
        var form = document.querySelector('form.oe_login_form') ||
            document.querySelector('form[action*="login"]') ||
            document.querySelector('.card-body form') ||
            document.querySelector('form');
        if (!form) return;

        var container = form.parentNode;

        // ── Error banner (factory mismatch) ──────────────────────────
        var factoryError = getUrlParam('factory_error');
        if (factoryError === '1') {
            var errorFactory = getUrlParam('factory') || getSelectedFactory();
            var bannerDiv = document.createElement('div');
            bannerDiv.innerHTML = buildErrorBannerHTML(errorFactory);
            container.insertBefore(bannerDiv.firstChild, form);
        }

        // ── Factory selector widget ───────────────────────────────────
        var selectorDiv = document.createElement('div');
        selectorDiv.innerHTML = buildSelectorHTML();
        container.insertBefore(selectorDiv.firstChild, form);

        // ── Hidden input inside form ──────────────────────────────────
        injectHiddenInput(form);

        // ── Restore previous selection ────────────────────────────────
        var saved = getSelectedFactory();
        if (saved) {
            window.vbSelectFactory(saved);
        }
    }

    /* ------------------------------------------------------------------ */
    /*  Entry point                                                        */
    /* ------------------------------------------------------------------ */
    function init() {
        if (!isLoginPage()) return;

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function () {
                injectSelector();
                setTimeout(injectSelector, 600);
                setTimeout(injectSelector, 1800);
            });
        } else {
            injectSelector();
            setTimeout(injectSelector, 600);
            setTimeout(injectSelector, 1800);
        }
    }

    init();
})();
