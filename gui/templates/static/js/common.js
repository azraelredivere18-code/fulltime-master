function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (character) {
        return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character];
    });
}

function showTip(type, title, content) {
    // 设置标题
    $('#tip-modal #tip-title').text(title);

    // 根据类型设置内容
    var icon = '';
    switch (type) {
        case 'success':
            icon = '<span class="tip-symbol tip-success" aria-hidden="true">✓</span> ';
            break;
        case 'warring':
            icon = '<span class="tip-symbol tip-warning" aria-hidden="true">!</span> ';
            break;
        case 'error':
            icon = '<span class="tip-symbol tip-error" aria-hidden="true">×</span> ';
            break;
        case 'info':
            icon = '<span class="tip-symbol tip-info" aria-hidden="true">i</span> ';
            break;
        default:
            icon = '';
    }

    // The message can include site or task data, so render it as text.
    $('#tip-modal .modal-body').html(icon).append($('<span class="align-middle">').text(content));

    // 打开模态框
    $('#tip-modal').modal({
        keyboard: false
    });
}


function getOS() {
    const ua = navigator.userAgent;

    if (/Android/.test(ua)) return "Android";
    if (/iPhone|iPad|iPod/.test(ua)) return "iOS";
    if (/Win(dows)?/.test(ua)) return "Windows";
    if (/Mac OS/.test(ua)) return "MacOS";
    if (/Linux/.test(ua)) return "Linux";

    return "Unknown";
}

function isRE(pattern) {
    const regexSymbols = /[.*+?^${}()|[\]\\]/;
    if (!regexSymbols.test(pattern)) {
        return false; // 如果没有正则符号，返回 false
    }

    try {
        new RegExp(pattern);
        return true;
    } catch (e) {
        return false;
    }
}

$(function () {
    if (getOS() == 'MacOS') {
        $('.icon-close').addClass('d-none')
    }
})
