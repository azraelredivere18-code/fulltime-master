
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

function showResumeSetup(setup) {
    var ready = setup && (setup.state === 'manual' || setup.state === 'site_receipt');
    $('.resume-panel').toggleClass('is-ready', !!ready);
    $('#resume-status').text(setup && setup.reason ? setup.reason :
        '先登录或注册，再检查网站是否已有可投递的简历。');
    $('#confirm-resume-ready').text(ready ? '重新确认网站简历' : '网站已有简历');
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
            pywebview.api.get_login_status(selectedPlatform).then(function (state) {
                if (state === 'browser_closed') {
                    return pywebview.api.open_browser(selectedPlatform).then(function (opened) {
                        if (opened !== true) {
                            showTip('info', '先连接平台', String(opened));
                            return false;
                        }
                        return pywebview.api.show_browser_guidance(selectedPlatform, 'login').then(function (shown) {
                            if (!shown) showTip('info', '先连接平台', '请在' + selectedPlatform + '手动登录或注册并准备简历。');
                            return false;
                        });
                    });
                }
                if (state !== 'logged_in') {
                    return pywebview.api.show_browser_guidance(selectedPlatform,
                        state === 'verification' ? 'verification' : state === 'logged_out' ? 'login' : 'unknown')
                        .then(function (shown) {
                            if (!shown) showTip('info', '需要人工介入', '请在' + selectedPlatform + '内置浏览器完成登录、注册或安全验证。');
                            return false;
                        });
                }
                return pywebview.api.get_platform_resume_setup(selectedPlatform).then(function (setup) {
                    showResumeSetup(setup);
                    if (setup.state === 'unprepared') {
                        return pywebview.api.show_browser_guidance(selectedPlatform, 'resume').then(function (shown) {
                            if (!shown) showTip('info', '请先准备网站简历', setup.reason + '。完成后点击“网站已有简历”，或在“创建或上传简历”中操作。');
                            return false;
                        });
                    }
                    return pywebview.api.start(selectedPlatform, 'apply_mode').then(function (res) {
                        if (res == '已运行') {
                            setStartStyle();
                            showStatue('正在等待职位列表');
                        } else {
                            showTip('error', '', res);
                        }
                        return true;
                    });
                });
            }).catch(function (error) {
                showTip('error', '启动失败', String(error));
            }).finally(function () { applyButton.removeAttr('disabled'); });

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
                        pywebview.api.show_browser_guidance(platform,
                            state === 'verification' ? 'verification' : state === 'logged_out' ? 'login' : 'unknown')
                            .then(function (shown) {
                                if (!shown) showTip('info', '需要手动登录', '请在内置浏览器中自行完成' + platform + '登录和安全验证，并在网站上准备好简历。');
                            });
                    }
                });
            }
        });
    });

    $('#open-resume-setup').click(function () {
        pywebview.api.open_resume_setup($('.selected-platform').val()).catch(function (error) {
            showTip('error', '网站简历', String(error));
        });
    });

    $('#confirm-resume-ready').click(function () {
        var platform = $('.selected-platform').val();
        pywebview.api.acknowledge_platform_resume(platform).then(function (result) {
            if (result.state === 'manual') {
                showResumeSetup(result);
            } else {
                pywebview.api.show_browser_guidance(platform, 'login');
            }
            showTip(result.state === 'manual' ? 'success' : 'info', '网站简历', result.reason);
        }).catch(function (error) { showTip('error', '网站简历', String(error)); });
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
        var resumeNotified = {};
        function refreshRunStatus() {
            var platform = $('.selected-platform').val();
            pywebview.api.get_login_status(platform).then(function (state) {
                if ($('.selected-platform').val() !== platform) return;
                var labels = {logged_in:'已登录', logged_out:'未登录，请在内置浏览器手动登录',
                    verification:'请手动完成安全验证', browser_closed:'内置浏览器未打开', unknown:'待确认'};
                $('#login-status').text('登录状态：' + (labels[state] || '待确认'));
                $('.status-led').toggleClass('is-ready', state === 'logged_in');
                if ((state === 'logged_out' || state === 'verification' || state === 'unknown') && !manualLoginNotified[platform]) {
                    pywebview.api.show_browser_guidance(platform,
                        state === 'logged_out' ? 'login' : state === 'verification' ? 'verification' : 'unknown')
                        .then(function (shown) {
                            if (!shown) showTip('info', '需要人工介入', state === 'logged_out' ?
                                '请在内置浏览器中手动登录' + platform + '。程序会等待登录完成。' :
                                state === 'verification' ? '请在内置浏览器中手动完成安全验证。程序会等待验证完成。' :
                                '当前页面尚未确认登录状态。请检查是否需要登录或注册，并准备网站简历。');
                        });
                    manualLoginNotified[platform] = true;
                }
                if (state === 'logged_in') manualLoginNotified[platform] = false;
            });
            pywebview.api.get_platform_resume_setup(platform).then(function (setup) {
                if ($('.selected-platform').val() !== platform) return;
                showResumeSetup(setup);
            });
            pywebview.api.get_run_status().then(function (status) {
                if (!status) return;
                var selected = $('.selected-platform').val();
                var statuses = status.platforms || {};
                var selectedStatus = statuses[selected];
                if (selectedStatus && /简历|附件/.test(selectedStatus.message || '') && !resumeNotified[selected]) {
                    pywebview.api.show_browser_guidance(selected, 'resume');
                    resumeNotified[selected] = true;
                } else if (!selectedStatus || !/简历|附件/.test(selectedStatus.message || '')) {
                    resumeNotified[selected] = false;
                }
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
