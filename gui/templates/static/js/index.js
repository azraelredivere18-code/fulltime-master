
function setStopStyle() {
    var applyButton = $('#start-apply')
    applyButton.removeClass('btn-danger')
    applyButton.addClass('btn-primary')
    applyButton.html(actionLabel(false))
}

function actionLabel(stopping) {
    return stopping ? '停止自动投递' : '开始自动投递 <span aria-hidden="true">→</span>'
}

function setStartStyle() {
    var applyButton = $('#start-apply')
    applyButton.removeClass('btn-primary')
    applyButton.addClass('btn-danger')
    applyButton.text(actionLabel(true))
}

function showTask(kw, city) {
    $('.task-show').removeClass('d-none')
    if(kw && kw != 'None'){
        $('.task-keyword').text(kw)
    }
    if(city && city != 'None'){
        $('.task-city').text(city)
    }
}

function showStatue(text) {
    $('.status-show').removeClass('d-none')
    $('.task-msg').text(text)
}

function notify_redirect() {
    var ele = $(this)
    var href = ele.attr('href')
    if (href) {
        pywebview.api.open_url(href);
    }
}

$(function () {
    window.currentWorkMode = 'apply_mode';
    if (getOS() == 'MacOS') {
        $('.topbar').css('visibility', 'hidden')
    }

    $('.selected-platform').on('change', function() {
        var selectedValue = $(this).val();
        var taskStatus = $('.task-show')
        setStopStyle();

        pywebview.api.get_task(selectedValue).then(function (task) {
            if (task) {
                showTask(task.keyword, task.city)
            } else {
                $('.task-show').addClass('d-none')
            }
        })

        pywebview.api.get_run_status(selectedValue).then(function (status) {
            if ($('.selected-platform').val() !== selectedValue) return;
            if (status && status.running) setStartStyle();
            else setStopStyle();
        });
        if(!taskStatus.text().includes('？')) taskStatus.removeClass('d-none');
    });

    $('#start-apply').click(function () {
        var selectedPlatform = $('.selected-platform').val()
        var applyButton = $(this)
        if (applyButton.hasClass('btn-primary')) {
            applyButton.attr('disabled', 'disabled')
            pywebview.api.start(selectedPlatform, 'apply_mode').then(function (res) {
                if (res == '已运行') {
                    setStartStyle()
                    showStatue('正在等待职位列表')
                } else {
                    showTip('error', '', res)
                }
                applyButton.removeAttr('disabled')
            })

        } else {
            pywebview.api.stop(selectedPlatform).then(function (res) {
                if (res == '已停止') {
                    setStopStyle()
                }
            })
        }
    })

    $('#open-browser').click(function () {
        var platform = $('.selected-platform').val();
        pywebview.api.open_browser(platform).then(function (opened) {
            if (opened !== true) {
                showTip('error', '', typeof opened === 'string' ? opened :
                    '无法打开内置浏览器。请确认系统已安装 Microsoft Edge WebView2 Runtime。');
            } else {
                pywebview.api.get_login_status(platform).then(function (state) {
                    if (state !== 'logged_in') {
                        showTip('info', '需要手动登录', '请在内置浏览器中自行完成' + platform + '登录和安全验证，并在网站上准备好简历。完成后返回本窗口开始搜索。');
                    }
                });
            }
        });
    });

    $('#export-page-diagnostics').click(function () {
        var platform = $('.selected-platform').val();
        pywebview.api.export_page_diagnostics(platform).then(function (result) {
            showTip(result.state === 'saved' ? 'success' : 'info', '页面诊断',
                result.reason + (result.path ? '\n' + result.path : ''));
        }).catch(function (error) { showTip('error', '页面诊断', String(error)); });
    });

    window.addEventListener('pywebviewready', function () {
        var manualLoginNotified = {};
        function refreshRunStatus() {
            var platform = $('.selected-platform').val();
            pywebview.api.get_login_status(platform).then(function (state) {
                if ($('.selected-platform').val() !== platform) return;
                var labels = {logged_in:'已登录', logged_out:'未登录，请在内置浏览器手动登录',
                    verification:'请手动完成安全验证', browser_closed:'内置浏览器未打开', unknown:'待确认'};
                $('#login-status').text('登录状态：' + (labels[state] || '待确认'));
                $('.status-led').toggleClass('is-ready', state === 'logged_in');
                if ((state === 'logged_out' || state === 'verification') && !manualLoginNotified[platform]) {
                    showTip('info', '需要人工介入', state === 'logged_out' ?
                        '请在内置浏览器中手动登录' + platform + '。程序会等待登录完成。' :
                        '请在内置浏览器中手动完成安全验证。程序会等待验证完成。');
                    manualLoginNotified[platform] = true;
                }
                if (state === 'logged_in') manualLoginNotified[platform] = false;
            });
            pywebview.api.get_run_status().then(function (status) {
                if (!status) return;
                var selected = $('.selected-platform').val();
                var statuses = status.platforms || {};
                var selectedStatus = statuses[selected];
                if (selectedStatus && selectedStatus.running) setStartStyle();
                else setStopStyle();
                var active = Object.values(statuses).filter(function (entry) { return entry.running; });
                if (!active.length) {
                    showStatue((selectedStatus && selectedStatus.message) || status.message || '尚未开始');
                    return;
                }
                showStatue(active.map(function (entry) {
                    return entry.platform + '：' + entry.message + '；已记录 ' +
                        (entry.saved || 0) + '，已确认' +
                        (entry.platform === 'BOSS直聘' ? '沟通 ' : '投递 ') +
                        (entry.applied || 0) + '；今日名额 ' +
                        (entry.daily_used || 0) + '/' + (entry.daily_limit || 0);
                }).join('\n'));
            });
        }
        refreshRunStatus();
        setInterval(refreshRunStatus, 2500);
    });

    $('.logo > *').click(notify_redirect)
})
