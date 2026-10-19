$.fn.selectpicker.defaults={countSelectedText:'{0}个已选'};
$.fn.clearForm = function () {
    return this.each(function () {
        var $form = $(this);

        // 清空所有输入框、选择框和文本域
        $form.find(':input').each(function () {
            var $input = $(this);
            // 如果是选择框，重置为默认值
            if ($input.is('select')) {
                $input.prop('selectedIndex', 0); // 默认为第一个选项
            } else {
                $input.val($input.prop('defaultValue')); // 重置为默认值
            }
        });
        $('#platform').selectpicker_val(PLATFORMS)
    });
};
$.fn.selectpicker_val = function (value) {
    $(this).val(value);
    $(this).selectpicker('refresh');
};

function openTab() {
    const tabname = window.location.hash;
    if (tabname) {
        $(`${tabname}`).tab('show');
        $('.tab-pane').not(`${tabname}`).removeClass('show active');
        $('.nav-link.active').removeClass('active');
        $(`.nav-link[href='${tabname}']`).addClass('active');
        window.location.hash = ''
    }
}

$(document).ready(openTab);
$(window).on('hashchange', openTab);

PLATFORMS = ['BOSS直聘', '智联招聘', '前程无忧', '应届生', '猎聘', '拉勾', '牛客网', '国聘网']

function getTaskForm() {
    var data = {
        id: $('#task-id').val().trim(),
        keyword: $('#keyword').val().trim().replace(/[,，|、;；-]/g, ' '),
        city: $('#city').val().trim().replace(/[,，|、;；-]/g, ' '),
        search_prompt: $('#search-prompt').val().trim().replaceAll('\n', ''),
        job_prompt: $('#job-prompt').val().trim().replaceAll('\n', ''),
        search_re: $('#search-re').val().trim(),
        job_re: $('#job-re').val().trim(),
        resume: $('#resume-path').val().trim(),
        match_degree: $('#match-degree').val(),
        employment_type: $('#employment-type').val(),
        recruitment_track: $('#recruitment-track').val(),
        platform: $('#platform').val().join(',')
    };
    return data;
}

function tasksTableAddRow(task, task_id = null) {
    var item = `
        <tr>
            <td>${escapeHtml(task.keyword)}</td>
            <td>${escapeHtml(task.city)}</td>
            <td>${escapeHtml(task.search_prompt)}</td>
            <td>${escapeHtml(task.job_prompt)}</td>
            <td>${escapeHtml(task.search_re)}</td>
            <td>${escapeHtml(task.job_re)}</td>
            <td>
                <span class="tip">${task.resume == null || task.resume == '' ? '未开启' : '已开启'}</span>
                <span class="d-none resume">${escapeHtml(task.resume)}</span>
            </td>
            <td>${escapeHtml(task.match_degree)}</td>
            <td>${escapeHtml(task.employment_type === 'internship' ? '实习' : '全职')}</td>
            <td>${escapeHtml(task.recruitment_track === 'campus' ? '校招' : task.recruitment_track === 'social' ? '社招' : '不限')}</td>
            <td>
                <span class="d-none row-id">${escapeHtml(task_id ? task_id : task.id)}</span>
                <span class="d-none platform">${escapeHtml(task.platform)}</span>
                <span class="d-none employment-type">${escapeHtml(task.employment_type || 'full_time')}</span>
                <span class="d-none recruitment-track">${escapeHtml(task.recruitment_track || 'all')}</span>
                <span class="icon-up"></span>
                <span class="icon-down"></span>
                <span class="icon-delete"></span>
            </td>
        </tr>
    `;
    $('.table-tasks tbody').append(item);

    // 点击列表显示投递任务
    $('.table-tasks tbody tr').click(function () {
        var selected_platform = $(this).find('.platform').text()
        $('#platform').selectpicker_val(selected_platform ? selected_platform.split(',') : PLATFORMS)
        $('#task-id').val($(this).find('.row-id').text())
        $('#keyword').val($(this).find('td:nth-child(1)').text())
        $('#city').val($(this).find('td:nth-child(2)').text())
        $('#search-prompt').val($(this).find('td:nth-child(3)').text())
        $('#job-prompt').val($(this).find('td:nth-child(4)').text())
        $('#search-re').val($(this).find('td:nth-child(5)').text())
        $('#job-re').val($(this).find('td:nth-child(6)').text())
        $('#resume-tip').text($(this).find('td:nth-child(7) .tip').text())
        $('#resume-path').val($(this).find('td:nth-child(7) .resume').text())
        $('#match-degree').val($(this).find('td:nth-child(8)').text())
        $('#employment-type').val($(this).find('.employment-type').text() || 'full_time')
        $('#recruitment-track').val($(this).find('.recruitment-track').text() || 'all')
        $('#alter-task').removeClass('d-none')
    })
}

function blocklistAddData(blocklist, blocklist_id = null) {
    var item = `
            <div class="blocklist-item d-flex justify-content-between rounded-lg p-2 mb-2">
                <span>${escapeHtml(blocklist.company)}</span>
                <span class="d-none blocklist-id">${escapeHtml(blocklist_id ? blocklist_id : blocklist.id)}</span>
                <span class="icon-delete"></span>
            </div>
    `;
    $('.blocklist-container').append(item);
}

function setAuthInfo() {
    pywebview.api.get_version().then(function (version) {
        $('#version').text(version)
    })
}

function render_platform_setting(platform, data, applyConfig) {
    var platformFilter = applyConfig[platform] ? applyConfig[platform].filter : {}
    var platformSayhello = applyConfig[platform] && applyConfig[platform].sayhello ? applyConfig[platform].sayhello : {}
    var platformDelay = applyConfig[platform] ? applyConfig[platform].delay : {}
    var platformLanguage = applyConfig[platform] ? applyConfig[platform].language : ""
    if (platform !== 'boss') {
        const selected = Object.entries(platformFilter || {}).filter(function (entry) {
            return entry[1] !== null && entry[1] !== '' && entry[1] !== '不限' &&
                entry[1] !== '否' && !(Array.isArray(entry[1]) && entry[1].length === 0);
        });
        const note = $('<div class="alert alert-info small" role="status"></div>');
        note.text('网站原生筛选尚待登录后校准。当前任务会执行关键词、城市、正则、岗位类型和销售排除。' +
            (selected.length ? '旧设置仍启用：' + selected.map(function (entry) { return entry[0]; }).join('、') + '。请先清除。' : ''));
        $(`#${platform}-setting form`).append(note);
        if (selected.length) {
            const clear = $('<button type="button" class="btn btn-outline-primary btn-sm mb-2">清除旧网站筛选</button>');
            clear.on('click', function () {
                pywebview.api.set_apply_config(`${platform}.filter`, {}).then(function () {
                    note.text('已清除旧网站筛选；关键词、城市、正则、岗位类型和销售排除仍生效。');
                    clear.remove();
                });
            });
            $(`#${platform}-setting form`).append(clear);
        }
        return;
    }

    // 退出登录
    if (['boss', 'liepin', 'zhilian', 'qiancheng', 'guopin', 'yjs', 'niuke', 'jobonline', 'jobmdcn', 'jobsdbhk'].includes(platform)) {
        var signoutHtml = `
                    <div class="form-group row">
                        <label for="${platform}-signout"
                               class="col-sm-2 col-form-label col-form-label-sm text-right">退出登录</label>
                        <div class="col-sm-10">
                            <button type="button" class="btn btn-outline-primary btn-sm" id="${platform}-signout">
                                退出登录
                            </button>
                        </div>
                    </div>
`
        $(`#${platform}-setting form`).append(signoutHtml);

        $(`#${platform}-signout`).click(function () {
            pywebview.api.signout(platform).then(function (success) {
                showTip(success ? 'success' : 'info', '',
                    success ? '已退出登录' : '请在招聘平台的浏览器页面手动退出登录')
            })
        });
    }
    // 打招呼设置
    if (['boss', 'liepin'].includes(platform)) {
        var sayhelloHtml = `
                    <div class="form-group row">
                        <label for="${platform}-sayhello" class="col-sm-2 col-form-label col-form-label-sm text-right">
                            <span class="badge badge-success">单</span>
                            打招呼语
                        </label>
                        <div class="col-sm-10">
                            <select class="custom-select custom-select-sm w-100 selectpicker" id="${platform}-sayhello"
                                    data-style="btn-sm">
                                <option value="平台默认" ${platformSayhello?.option?.includes('平台默认') ? 'selected' : ''}>平台默认(先在平台APP开启自动打招呼)</option>
                                <option value="AI打招呼" ${platformSayhello?.option?.includes('AI打招呼') ? 'selected' : ''}>AI打招呼(先在平台APP关闭自动打招呼)</option>
                            </select>
                        </div>
                    </div>
                    <div class="form-group row">
                        <label for="${platform}-sayhello-prompt" class="col-sm-2 col-form-label col-form-label-sm text-right">
                            <span class="badge badge-primary">填</span>
                            AI打招呼要求
                        </label>
                        <div class="col-sm-10">
                            <input type="text" class="form-control form-control-sm flex-grow-1" id="${platform}-sayhello-prompt"
                                   placeholder="（选填）填写生成字数、语气、格式等要求的提示词" value="${platformSayhello.requirement ? platformSayhello.requirement : ''}">
                        </div>
                    </div>
`
        $(`#${platform}-setting form`).append(sayhelloHtml);

        $(`#${platform}-sayhello`).change(function () {
            pywebview.api.set_apply_config(`${platform}.sayhello.option`, $(this).val())
        });

        $(`#${platform}-sayhello-prompt`).on('input', function () {
            pywebview.api.set_apply_config(`${platform}.sayhello.requirement`, $(this).val())
        });
    }

    // 遍历数据并生成表单元素
    $.each(data, function (key, value) {
        const selectionMode = value.selectionMode;
        var value_selected = platformFilter ? platformFilter[key] : null
        if (selectionMode && selectionMode == 'hidden') {
            return true;
        }
        if (value_selected && selectionMode == 'multiple') {
            value_selected = platformFilter[key].split(value.separator || ',')
        }
        const optionsHtml = value.options.map(option => {
            return `<option value="${option.code}" ${value_selected && value_selected.includes(option.code) ? 'selected' : ''}>${option.name}</option>`;
        }).join('');

        const formGroup = `
            <div class="form-group row">
                <label for="${platform}-${key}" class="col-sm-2 col-form-label col-form-label-sm text-right">
                    <span class="badge badge-${selectionMode === 'single' ? 'success' : 'warning'}">${selectionMode === 'single' ? '单' : '多'}</span>
                    ${value.name}
                </label>
                <div class="col-sm-10">
                    <select class="custom-select custom-select-sm w-100 selectpicker" id="${platform}-${key}" data-style="btn-sm" title="不限" ${selectionMode === 'multiple' ? 'multiple' : ''}>
                        ${optionsHtml}
                    </select>
                </div>
            </div>
        `;
        $(`#${platform}-setting form`).append(formGroup);

        // 添加事件监听器
        $(`#${platform}-${key}`).change(function () {
            const selectedValues = $(this).val();
            // 检查是否选择了 "不限"
            if (selectedValues && selectedValues.includes("不限")) {
                $(this).find('option').prop('selected', false);
                $(this).selectpicker('refresh');
                $(this).selectpicker('toggle');
                pywebview.api.set_apply_config(`${platform}.filter.${key}`, '')
                return
            }

            if (selectionMode === 'single') {
                pywebview.api.set_apply_config(`${platform}.filter.${key}`, selectedValues)
            } else {
                const concatenatedValues = selectedValues ? selectedValues.join(value.separator || ',') : '';
                pywebview.api.set_apply_config(`${platform}.filter.${key}`, concatenatedValues)
            }
        });
    });
    $('.selectpicker').selectpicker();

    // boss海外设置
    if (['boss'].includes(platform)) {
        var bossHtml = `
                    <div class="form-group row">
                        <label for="${platform}-language" class="col-sm-2 col-form-label col-form-label-sm text-right">
                            <span class="badge badge-primary">填</span>
                            工作语言
                        </label>
                        <div class="col-sm-10">
                            <input type="text" class="form-control form-control-sm flex-grow-1" id="${platform}-language"
                                   placeholder="BOSS海外特定选项" value="${platformLanguage ? platformLanguage : ''}">
                        </div>
                    </div>
`
        $(`#${platform}-setting form`).append(bossHtml);

        $(`#${platform}-language`).on('input', function () {
            pywebview.api.set_apply_config(`${platform}.language`, $(this).val().replace(/[,，|、;；-]/g, ' '))
        });
    }

    // 暂停设置
    var delayHtml = `
    <div class="form-group row">
        <label for="${platform}-delay-list-start" class="col-sm-2 col-form-label col-form-label-sm text-right">
            <span class="badge badge-primary">填</span>
            列表页暂停
        </label>
        <div class="col-sm-10">
            <small>随机暂停</small>
            <input type="number" class="form-control form-control-sm w-auto d-inline-block" id="${platform}-delay-list-start" value="${platformDelay?.list?.start}" placeholder="默认">
            <small>秒到</small>
            <input type="number" class="form-control form-control-sm w-auto d-inline-block " id="${platform}-delay-list-end" value="${platformDelay?.list?.end}" placeholder="默认">
            <small>秒</small>
        </div>
    </div>
    <div class="form-group row">
        <label for="${platform}-delay-detail-start" class="col-sm-2 col-form-label col-form-label-sm text-right">
            <span class="badge badge-primary">填</span>
            详情页暂停
        </label>
        <div class="col-sm-10">
            <small>随机暂停</small>
            <input type="number" class="form-control form-control-sm w-auto d-inline-block" id="${platform}-delay-detail-start" value="${platformDelay?.detail?.start}" placeholder="默认">
            <small>秒到</small>
            <input type="number" class="form-control form-control-sm w-auto d-inline-block " id="${platform}-delay-detail-end" value="${platformDelay?.detail?.end}" placeholder="默认">
            <small>秒</small>
        </div>
    </div>
`
    $(`#${platform}-setting form`).append(delayHtml);

    var delayTip = true
    $(`[id^=${platform}-delay]`).click(function () {
        if (delayTip) {
            delayTip = false
            showTip('warring', '', '强烈不建议缩短暂停时间，投递过快会导致平台封账号、封IP等措施（尤其是BOSS），导致的一切后果（包括但不限于上述情况）自行负责！')
        }
    });

    $(`#${platform}-delay-list-start`).change(function () {
        delayTip = true
        if ($(this).val() && $(this).val() < 3) {
            $(this).val(3)
            showTip('info', '', '不能小于3秒')
            return
        }
        pywebview.api.set_apply_config(`${platform}.delay.list.start`, $(this).val())
    });
    $(`#${platform}-delay-list-end`).change(function () {
        delayTip = true
        if ($(this).val() && $(this).val() < 3) {
            $(this).val(3)
            showTip('info', '', '不能小于3秒')
            return
        }
        pywebview.api.set_apply_config(`${platform}.delay.list.end`, $(this).val())
    });
    $(`#${platform}-delay-detail-start`).change(function () {
        delayTip = true
        if ($(this).val() && $(this).val() < 3) {
            $(this).val(3)
            showTip('info', '', '不能小于3秒')
            return
        }
        pywebview.api.set_apply_config(`${platform}.delay.detail.start`, $(this).val())
    });
    $(`#${platform}-delay-detail-end`).change(function () {
        delayTip = true
        if ($(this).val() && $(this).val() < 3) {
            $(this).val(3)
            showTip('info', '', '不能小于3秒')
            return
        }
        pywebview.api.set_apply_config(`${platform}.delay.detail.end`, $(this).val())
    });

}

var apply_setting = null;
$(function () {

    // 加载数据
    window.addEventListener('pywebviewready', function () {

        pywebview.api.get_config('appname').then(function (appname) {
            if(appname != '全职高手'){
                $('.mcp-row').addClass('d-none')
                $('.bit-browser-setting').addClass('d-none')
                $('#browser option:last-child').addClass('d-none')
            }
        })

        pywebview.api.get_apply_config().then(function (apply_config) {
            $('#intelligent-perception').selectpicker_val(apply_config.intelligent_perception);
            $('#company-filter').selectpicker_val(apply_config.company_filter);
            $('#off-site-filter').selectpicker_val(apply_config.off_site_filter);
            $('#exclude-sales-roles').prop('checked', !!apply_config.exclude_sales_roles);
            $('#platform-resume-path').text(apply_config.resume_file || '未选择文件');
            $('#chat-prompt').val(apply_config?.chat_prompt);
            $('#pages').val(apply_config.max_page);
            apply_setting = apply_config
        })

        pywebview.api.get_tasks().then(function (tasks) {
            for (var i = 0; i < tasks.length; i++) {
                tasksTableAddRow(tasks[i])
            }
        })

        pywebview.api.get_biz_config().then(function (biz) {
            if (biz) {
                $('.d-biz').removeClass('d-none')
            }
        })


        pywebview.api.get_curr_config().then(function (curr_config) {
            $('#bit-window-id').val(curr_config?.bit?.window_id);
            $('#apply-scope').selectpicker_val(curr_config.apply_scope);
            $('#task-scope').selectpicker_val(curr_config.task_scope);
        })

        pywebview.api.get_blocklist().then(function (blocklist) {
            for (var i = 0; i < blocklist.length; i++) {
                blocklistAddData(blocklist[i])
            }
        })

        pywebview.api.get_app_config().then(function (app_config) {
            $('#bit-port').val(app_config.bit?.port);
            $('#miao').val(app_config.miao);
        })

        setAuthInfo()
    })

    // 加载平台设置
    $('.nav-link[href="#boss-setting"]').click(function () {
        if ($('#boss-setting form').text().trim() == '') {
            pywebview.api.get_platform_setting('boss').then(function (data) {
                render_platform_setting('boss', data, apply_setting)
            })
        }
    })
    
    // 当点击软件设置标签页时，检查MCP服务状态
    $('.nav-link[href="#software-setting"]').click(function () {
        checkMCPStatus();
    })
    $('.nav-link[href="#qiancheng-setting"]').click(function () {
        if ($('#qiancheng-setting form').text().trim() == '') {
            pywebview.api.get_platform_setting('qiancheng').then(function (data) {
                render_platform_setting('qiancheng', data, apply_setting)
            })
        }
    })
    $('.nav-link[href="#liepin-setting"]').click(function () {
        if ($('#liepin-setting form').text().trim() == '') {
            pywebview.api.get_platform_setting('liepin').then(function (data) {
                render_platform_setting('liepin', data, apply_setting)
            })
        }
    })
    $('.nav-link[href="#guopin-setting"]').click(function () {
        if ($('#guopin-setting form').text().trim() == '') {
            pywebview.api.get_platform_setting('guopin').then(function (data) {
                render_platform_setting('guopin', data, apply_setting)
            })
        }
    })
    $('.nav-link[href="#lagou-setting"]').click(function () {
        if ($('#lagou-setting form').text().trim() == '') {
            pywebview.api.get_platform_setting('lagou').then(function (data) {
                render_platform_setting('lagou', data, apply_setting)
            })
        }
    })
    $('.nav-link[href="#yjs-setting"]').click(function () {
        if ($('#yjs-setting form').text().trim() == '') {
            pywebview.api.get_platform_setting('yjs').then(function (data) {
                render_platform_setting('yjs', data, apply_setting)
            })
        }
    })
    $('.nav-link[href="#gdzhzp-setting"]').click(function () {
        if ($('#gdzhzp-setting form').text().trim() == '') {
            pywebview.api.get_platform_setting('gdzhzp').then(function (data) {
                render_platform_setting('gdzhzp', data, apply_setting)
            })
        }
    })
    $('.nav-link[href="#zhilian-setting"]').click(function () {
        if ($('#zhilian-setting form').text().trim() == '') {
            pywebview.api.get_platform_setting('zhilian').then(function (data) {
                render_platform_setting('zhilian', data, apply_setting)
            })
        }
    })
    $('.nav-link[href="#niuke-setting"]').click(function () {
        if ($('#niuke-setting form').text().trim() == '') {
            pywebview.api.get_platform_setting('niuke').then(function (data) {
                render_platform_setting('niuke', data, apply_setting)
            })
        }
    })
    $('.nav-link[href="#jobonline-setting"]').click(function () {
        if ($('#jobonline-setting form').text().trim() == '') {
            pywebview.api.get_platform_setting('jobonline').then(function (data) {
                render_platform_setting('jobonline', data, apply_setting)
            })
        }
    })
    $('.nav-link[href="#jobmdcn-setting"]').click(function () {
        if ($('#jobmdcn-setting form').text().trim() == '') {
            pywebview.api.get_platform_setting('jobmdcn').then(function (data) {
                render_platform_setting('jobmdcn', data, apply_setting)
            })
        }
    })
    $('.nav-link[href="#offertoday-setting"]').click(function () {
        if ($('#offertoday-setting form').text().trim() == '') {
            pywebview.api.get_platform_setting('offertoday').then(function (data) {
                render_platform_setting('offertoday', data, apply_setting)
            })
        }
    })
    $('.nav-link[href="#jobsdbhk-setting"]').click(function () {
        if ($('#jobsdbhk-setting form').text().trim() == '') {
            pywebview.api.get_platform_setting('jobsdbhk').then(function (data) {
                render_platform_setting('jobsdbhk', data, apply_setting)
            })
        }
    })

    // 投递任务上移按钮事件
    $(document).on('click', '#tasks-setting .icon-up', function () {
        const row = $(this).closest('tr');
        const prevRow = row.prev('tr');
        if (prevRow.length) {
            const row_id = row.find('.row-id').text();
            const prev_row_id = prevRow.find('.row-id').text();
            pywebview.api.alter_task('move_up', {
                'prev': prev_row_id,
                'curr': row_id
            }).then(function (changed) {
                if (changed) row.insertBefore(prevRow);
            });
        }
    });

    // 投递任务下移按钮事件
    $(document).on('click', '#tasks-setting .icon-down', function () {
        const row = $(this).closest('tr');
        const nextRow = row.next('tr');
        if (nextRow.length) {
            const row_id = row.find('.row-id').text();
            const next_row_id = nextRow.find('.row-id').text();
            pywebview.api.alter_task('move_down', {
                'next': next_row_id,
                'curr': row_id
            }).then(function (changed) {
                if (changed) row.insertAfter(nextRow);
            });
        }
    });

    // 投递任务删除按钮事件
    $(document).on('click', '#tasks-setting .icon-delete', function () {
        const row = $(this).closest('tr');
        const row_id = row.find('.row-id').text();
        pywebview.api.alter_task('delete', row_id).then(function (deleted) {
            if (deleted) row.remove();
        });
    });

    // 黑名单删除按钮事件
    $(document).on('click', '#blocklist-setting .icon-delete', function () {
        const row = $(this).closest('.blocklist-item');
        data_id = row.find('.blocklist-id').text()
        pywebview.api.alter_blocklist('delete', data_id)
        row.remove();
    });


    $('#intelligent-perception').change(function () {
        pywebview.api.set_apply_config('intelligent_perception', $(this).val())
    });

    $('#company-filter').change(function () {
        pywebview.api.set_apply_config('company_filter', $(this).val())
    });

    $('#off-site-filter').change(function () {
        pywebview.api.set_apply_config('off_site_filter', $(this).val())
    });

    $('#exclude-sales-roles').change(function () {
        pywebview.api.set_apply_config('exclude_sales_roles', $(this).is(':checked'))
    });

    $('#pick-platform-resume').click(function () {
        pywebview.api.choose_platform_resume().then(function (path) {
            if (path) $('#platform-resume-path').text(path);
        }).catch(function (error) { showTip('error', '', String(error)); });
    });

    $('#upload-platform-resume').click(function () {
        var button = $(this).prop('disabled', true);
        pywebview.api.upload_selected_resume($('#resume-platform').val()).then(function (result) {
            showTip(result.state === 'confirmed' ? 'success' : 'info', '附件简历', result.reason);
        }).catch(function (error) {
            showTip('error', '附件简历', String(error));
        }).finally(function () { button.prop('disabled', false); });
    });

    $('#pages').on('input', function () {
        pywebview.api.set_apply_config('max_page', parseInt($(this).val()))
    });

    $('#apply-scope').change(function () {
        pywebview.api.set_curr_config('apply_scope', $(this).val())
    });

    $('#task-scope').change(function () {
        pywebview.api.set_curr_config('task_scope', $(this).val())
        pywebview.api.close_current_window()
    });

    $('#bit-port').on('input', function () {
        pywebview.api.set_app_config('bit.port', $(this).val())
    });

    $('#bit-window-id').on('input', function () {
        pywebview.api.set_curr_config('bit.window_id', $(this).val())
    });

    $('#miao').on('input', function () {
        pywebview.api.set_app_config('miao', $(this).val())
    });

    $('#send-miao-test').click(function () {
        pywebview.api.send_notification_miao('太棒了！您成功设置了提醒！').then(function (res) {
            if (res) {
                showTip('success', '', '已发送测试提醒')
            } else {
                showTip('warring', '', '发送失败，请检查喵码是否正确')
            }
        })
    });

    // MCP服务相关
    var mcpRunning = false;
    var mcpAddress = '';
    var eventSource = null;

    // 检查MCP服务状态
    function checkMCPStatus() {
        if (typeof pywebview !== 'undefined' && pywebview.api) {
            pywebview.api.is_mcp_running().then(function (address) {
                if (address) {
                    mcpRunning = true;
                    mcpAddress = address;
                    updateMCPUI(true);
                } else {
                    mcpRunning = false;
                    mcpAddress = '';
                    updateMCPUI(false);
                }
            });
        }
    }

    // 更新MCP UI状态
    function updateMCPUI(isRunning) {
        var $mcpBtn = $('#mcp');
        var $mcpStatus = $('#mcp-status');
        
        if (isRunning) {
            $mcpBtn.text('停止MCP');
            $mcpBtn.addClass('btn-danger');
            $mcpBtn.removeClass('btn-outline-primary');
            $mcpStatus.text('MCP地址：' + mcpAddress + ' 类型：streamable-http');
            startSSE();
        } else {
            $mcpBtn.text('启动MCP');
            $mcpBtn.removeClass('btn-danger');
            $mcpBtn.addClass('btn-outline-primary');
            $mcpStatus.text('');
            stopSSE();
        }
    }

    // 启动SSE连接
    function startSSE() {
        if (eventSource) {
            eventSource.close();
        }
        
        eventSource = new EventSource('http://' + mcpAddress + '/api/events');
        
        eventSource.onmessage = function (event) {
            try {
                var data = JSON.parse(event.data);
                // 可以在这里处理实时数据更新
                console.log('MCP event:', data);
            } catch (e) {
                console.error('Error parsing SSE data:', e);
            }
        };
        
        eventSource.onerror = function (error) {
            console.error('SSE error:', error);
            eventSource.close();
        };
    }

    // 停止SSE连接
    function stopSSE() {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
    }

    // MCP服务按钮点击事件
    $('#mcp').click(function () {
        var $this = $(this);
        if (typeof pywebview !== 'undefined' && pywebview.api) {
            // 添加disable属性，避免频繁点击
            $this.attr('disabled', 'disabled');
            
            if (mcpRunning) {
                // 停止MCP服务
                pywebview.api.stop_mcp().then(function (success) {
                    if (success) {
                        mcpRunning = false;
                        mcpAddress = '';
                        updateMCPUI(false);
                    }
                    // 移除disable属性
                    $this.removeAttr('disabled');
                });
            } else {
                // 启动MCP服务
                pywebview.api.start_mcp().then(function (address) {
                    if (address) {
                        mcpRunning = true;
                        mcpAddress = address;
                        updateMCPUI(true);
                    } else {
                        // 显示端口占用提醒
                        showTip('warring', '', '启动失败，可能是端口占用');
                    }
                    // 移除disable属性
                    $this.removeAttr('disabled');
                });
            }
        }
    });

    // 页面加载时检查MCP状态
    $(document).ready(function () {
        checkMCPStatus();
    });

    $('[data-toggle="tooltip"]').tooltip()
    $('.datepicker').datepicker({
        language: 'zh-CN',
        autoclose: true,
        format: "yyyy-mm-dd"
    });

    // 更多投递任务
    $('#task-more-btn').click(function () {
        $('.task-more').toggle()
    })

    // 保存投递任务
    $('#save-task').click(function () {
        var task = getTaskForm();
        task.id = null
        if (task.keyword == '') {
            showTip('warring', '', '请填写搜索职位')
            return
        }
        if (task.city == '') {
            showTip('warring', '', '请填写城市')
            return
        }
        if (task.match_degree == '') {
            showTip('warring', '', '请填写匹配度')
            return
        }
        if (task.match_degree < 0 || task.match_degree > 95) {
            showTip('warring', '', '匹配度要在0到95之间')
            return
        }
        if (task.search_prompt.includes(' ')) {
            showTip('warring', '', 'AI筛选职位应填写提示词，而不是关键词')
            return
        }
        if (task.job_prompt.includes(' ')) {
            showTip('warring', '', 'AI匹配职位应填写提示词，而不是关键词')
            return
        }
        if ((task.search_prompt.length > 0 && task.search_prompt.length < 5) && task.search_prompt !== "关闭") {
            showTip('warring', '', 'AI筛选职位设置错误')
            return
        }
        if (task.job_prompt.length > 0 && task.job_prompt.length < 5) {
            showTip('warring', '', 'AI匹配职位设置错误')
            return
        }
        if (task.search_prompt.length > 90) {
            showTip('warring', '', 'AI筛选职位设置错误')
            return
        }
        if (task.job_prompt.length > 90) {
            showTip('warring', '', 'AI匹配职位设置错误')
            return
        }
        if (task.search_prompt && task.job_prompt && (task.search_prompt == task.job_prompt)) {
            showTip('warring', '', 'AI筛选职位和AI匹配职位设置错误')
            return
        }
        if (task.search_re && !isRE(task.search_re)) {
            showTip('warring', '', '正则筛选职位需要填写正则表达式')
            return
        }
        if (task.job_re && !isRE(task.job_re)) {
            showTip('warring', '', '正则匹配职位需要填写正则表达式')
            return
        }
        if (task.platform == '') {
            showTip('warring', '', '请选择投递的平台')
            return
        }
        if (task.resume == '') {
            showTip('info', '简历提醒', '任务已保存。自动投递使用招聘网站上的简历；请在内置浏览器登录后检查网站简历。任务中的本地简历文本不会自动上传。')
        }
        if (task.city.includes('市')) {
            showTip('warring', '提示', '城市名不可加“市”')
        }
        if (task.platform.split(',').length === $('#platform option').length) {
            task.platform = null
        }

        $('#resume-tip').text('')
        $('#tasks-setting form').clearForm()
        pywebview.api.save_task(task).then(function (new_task_id) {
            if (new_task_id) {
                tasksTableAddRow(task, new_task_id)
            }
        })
    });

    // 修改投递任务
    $('#alter-task').click(function () {
        var task = getTaskForm();
        if (task.keyword == '') {
            showTip('warring', '', '请填写搜索职位')
            return
        }
        if (task.city == '') {
            showTip('warring', '', '请填写城市')
            return
        }
        if (task.match_degree == '') {
            showTip('warring', '', '请填写匹配度')
            return
        }
        if (task.match_degree < 0 || task.match_degree > 95) {
            showTip('warring', '', '匹配度要在0到95之间')
            return
        }
        if (task.search_prompt.includes(' ')) {
            showTip('warring', '', 'AI筛选职位应填写提示词，而不是关键词')
            return
        }
        if (task.job_prompt.includes(' ')) {
            showTip('warring', '', 'AI匹配职位应填写提示词，而不是关键词')
            return
        }
        if (task.search_prompt && task.job_prompt && (task.search_prompt == task.job_prompt)) {
            showTip('warring', '', 'AI筛选职位和AI匹配职位设置错误')
            return
        }
        if (task.search_re && !isRE(task.search_re)) {
            showTip('warring', '', '正则筛选职位填写的不是正则表达式')
            return
        }
        if (task.job_re && !isRE(task.job_re)) {
            showTip('warring', '', '正则匹配职位填写的不是正则表达式')
            return
        }
        if (task.platform.split(',').length === $('#platform option').length) {
            task.platform = null
        }
        if (task.city.includes('市')) {
            showTip('warring', '提示', '城市名不可加“市”')
        }
        pywebview.api.update_task(task).then(function (updated) {
            if (!updated) {
                showTip('warring', '', '任务未保存，请重试')
                return
            }
            $('.table-tasks tbody tr').each(function (index, element) {
            var curr_task = $(element)
            var resume = $('#resume-path').val()
            if (curr_task.find('.row-id').text() == task.id) {
                curr_task.find('td:nth-child(1)').text(task.keyword)
                curr_task.find('td:nth-child(2)').text(task.city)
                curr_task.find('td:nth-child(3)').text(task.search_prompt)
                curr_task.find('td:nth-child(4)').text(task.job_prompt)
                curr_task.find('td:nth-child(5)').text(task.search_re)
                curr_task.find('td:nth-child(6)').text(task.job_re)
                curr_task.find('td:nth-child(7) .tip').text((resume == null || resume.trim() === '') ? '未开启' : '已开启')
                curr_task.find('td:nth-child(7) .resume').text(resume)
                curr_task.find('td:nth-child(8)').text(task.match_degree)
                curr_task.find('td:nth-child(9)').text(task.employment_type === 'internship' ? '实习' : '全职')
                curr_task.find('td:nth-child(10)').text(task.recruitment_track === 'campus' ? '校招' : task.recruitment_track === 'social' ? '社招' : '不限')
                curr_task.find('.platform').text(task.platform)
                curr_task.find('.employment-type').text(task.employment_type)
                curr_task.find('.recruitment-track').text(task.recruitment_track)
            }
            })
            $('#resume-tip').text('')
            $('#tasks-setting form').clearForm()
            $('#alter-task').addClass('d-none')
        }).catch(function (error) { showTip('warring', '', String(error)) })
    });

    // 设置简历模态框导入简历
    $('#resume-modal-import').click(function () {
        pywebview.api.get_file_content(['简历 (*.docx;*.pdf)']).then(function (content) {
            if (content == null || content == '') {
                showTip('warring', '', '该文件没有读取到文字内容')
            } else {
                $('#resume-modal-edit').val(content)
            }
        })
    })

    var resume_edit_type = null
    $('#resume-modal').on('show.bs.modal', function (event) {
        var button = $(event.relatedTarget)
        var recipient = button.data('whatever')
        var content = $('#resume-modal-edit')
        resume_edit_type = recipient

        // 打开设置简历初始化简历内容
        if (resume_edit_type === 'chat') {
            pywebview.api.get_apply_config().then(function (apply_config) {
                content.val(apply_config?.chat_resume);
            })
        } else if (resume_edit_type === 'task') {
            content.val($('#resume-path').val())
        }
    })

    $('#regex-modal').on('show.bs.modal', function (event) {
        var button = $(event.relatedTarget)
        var func = button.data('whatever')
        var title = $('#regex-modal .modal-title')
        var regex = $('#regex')

        // 打开设置简历初始化简历内容
        if (func === 'search_re') {
            title.text('正则筛选职位')
            regex.val($('#search-re').val()).trigger('input')
        } else if (func === 'job_re') {
            title.text('正则匹配职位')
            regex.val($('#job-re').val()).trigger('input')
        }
    })
    
    $('#include_keyword, #exclude_keyword').on('input', function (event) {
        var title = $('#regex-modal .modal-title')
        let include_keywords = $('#include_keyword').val().trim().replace(/[,，|、;；-]/g, ' ')
        let exclude_keywords = $('#exclude_keyword').val().trim().replace(/[,，|、;；-]/g, ' ')

        if (title.text() == '正则筛选职位'){
            pywebview.api.keywords_to_regex(include_keywords, exclude_keywords, 'OR').then(function (regex) {
                $('#regex').val(regex)
            })
        } else {
            pywebview.api.keywords_to_regex(include_keywords, exclude_keywords, 'AND').then(function (regex) {
                $('#regex').val(regex)
            })
        }
    })

    $('#regex').on('input', function (event) {
        let regex = $('#regex').val()

        pywebview.api.regex_to_keywords(regex).then(function (result) {
            $('#include_keyword').val(result[0])
            $('#exclude_keyword').val(result[1])
        })
    })

    $('#regex-modal').on('hide.bs.modal', function (event) {
        var title = $('#regex-modal .modal-title').text()
        var regex = $('#regex').val()

        // 打开设置简历初始化简历内容
        if (title === '正则筛选职位') {
            $('#search-re').val(regex)
        } else if (title === '正则匹配职位') {
            $('#job-re').val(regex)
        }
    })

    // 关闭设置简历保存
    $('#resume-modal').on('hide.bs.modal', function (event) {
        var content = $('#resume-modal-edit').val()
        // 监听简历内容变化设置对应简历
        if (resume_edit_type === 'chat') {
            pywebview.api.set_apply_config('chat_resume', content)
        } else if (resume_edit_type === 'task') {
            $('#resume-path').val(content)
            $('#resume-tip').text('已设置简历')
        }
    })

    // 保存AI回复要求
    $('#chat-prompt').on('input', function () {
        pywebview.api.set_apply_config('chat_prompt', $(this).val())
    });

    // 保存黑名单
    $('#save-blocklist').click(function () {
        var companyName = $('#blocklist-company').val()
        if (!companyName) {
            return
        }
        var blocklist = {'company': companyName}
        pywebview.api.save_blocklist(blocklist).then(function (new_blocklist_id) {
            blocklistAddData(blocklist, new_blocklist_id)
            $('#blocklist-company').val('')
        }).catch(function (error) {
            showTip('error', '公司黑名单', String(error))
        })
    })
})
