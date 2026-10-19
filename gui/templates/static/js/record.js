
function recordLink(value, url) {
    return `<span class="link external-record-link" data-url="${escapeHtml(url)}">${escapeHtml(value)}</span>`;
}

function safeRecordText(value) {
    return escapeHtml(value);
}

function recordStatus(value, row) {
    if (row.attempt_state === 'manual_confirmed')
        return '<span class="record-status confirmed">手动确认</span>';
    if (value === '是') return '<span class="record-status confirmed">已确认</span>';
    if (row.attempt_state === 'pending' || row.attempt_state === 'unknown')
        return '<span class="record-status pending">待核实</span>';
    return '<span class="record-status filtered">未投递</span>';
}

function recordDetail(index, row) {
    var fields = [['职位', row.title], ['岗位类型', row.employment_type === 'internship' ? '实习' :
        row.employment_type === 'full_time' ? '全职' : '待确认'],
        ['招聘渠道', row.recruitment_track === 'campus' ? '校招' :
            row.recruitment_track === 'social' ? '社招' : '待确认'],
        ['公司', row.company], ['地区', row.area],
        ['搜索城市', row.search_city], ['薪资', row.salary], ['经验', row.experience],
        ['学历', row.education], ['任务 ID', row.task_id], ['匹配度', row.match_degree],
        ['投递时间', row.submit_time], ['备注', row.remarks]];
    return '<div class="record-detail">' + fields.map(function (entry) {
        return '<p><strong>' + escapeHtml(entry[0]) + '：</strong>' +
            escapeHtml(entry[1] || '—') + '</p>';
    }).join('') + '</div>';
}

function updateRecordSummary(rows) {
    var confirmed = rows.filter(function (row) {
        return row.submit === '是' && row.attempt_state !== 'manual_confirmed';
    }).length;
    var manual = rows.filter(function (row) { return row.attempt_state === 'manual_confirmed'; }).length;
    var pending = rows.filter(function (row) {
        return row.attempt_state === 'pending' || row.attempt_state === 'unknown';
    }).length;
    $('#record-summary').text('共 ' + rows.length + ' 条职位记录 · 已确认 ' +
        confirmed + ' 条 · 手动确认 ' + manual + ' 条 · 待核实 ' + pending + ' 条。点击行首可查看完整字段。');
}

$(function () {

    $(document).on('click', '.external-record-link', function () {
        pywebview.api.open_url($(this).attr('data-url'));
    });

    $(document).on('click', '.reconcile-apply-record', function () {
        var button = $(this);
        button.prop('disabled', true);
        pywebview.api.reconcile_apply_record(Number(button.attr('data-id'))).then(function (result) {
            $('#backfill-status').text(result.reason || '');
            if (result.state === 'confirmed') location.reload();
            else button.prop('disabled', false);
        }).catch(function (error) {
            $('#backfill-status').text(String(error));
            button.prop('disabled', false);
        });
    });

    if (getOS() == 'MacOS') {
        $('.topbar').css('visibility', 'hidden')
    }

    $('.btn').tooltip()

    window.addEventListener('pywebviewready', function () {

        var ApplyData = null;
        var ChatData = null;
        var backfillWasRunning = false;
        function refreshBackfillStatus() {
            pywebview.api.get_record_backfill_status().then(function (status) {
                if (!status) return;
                $('#backfill-status').text(status.message || '');
                $('#backfill-records').prop('disabled', !!status.running);
                if (backfillWasRunning && !status.running) {
                    pywebview.api.get_apply_record().then(function (rows) {
                        ApplyData = rows;
                        $('#record-table').bootstrapTable('load', ApplyData);
                        initCharts(ApplyData);
                        updateRecordSummary(ApplyData);
                    });
                }
                backfillWasRunning = !!status.running;
            });
        }
        $('#backfill-records').click(function () {
            $(this).prop('disabled', true);
            pywebview.api.start_record_backfill().then(function (status) {
                $('#backfill-status').text(status.message || '');
                $('#backfill-records').prop('disabled', !!status.running);
                backfillWasRunning = !!status.running;
            }).catch(function (error) {
                $('#backfill-status').text(String(error));
                $('#backfill-records').prop('disabled', false);
            });
        });
        refreshBackfillStatus();
        setInterval(refreshBackfillStatus, 2500);
        
        // 获取投递记录数据
        pywebview.api.get_apply_record().then(function (applyRecord) {
            ApplyData = applyRecord;
            updateRecordSummary(ApplyData);
            
            $('#record-table').bootstrapTable({
                columns: [{
                    field: 'create_time',
                    title: '日期',
                    sortable: true,
                    filterControl: 'input',
                    formatter: safeRecordText
                }, {
                    field: 'source',
                    title: '平台',
                    sortable: true,
                    filterControl: 'input',
                    formatter: safeRecordText
                }, {
                    field: 'task_id',
                    title: '任务 ID',
                    visible: false,
                    sortable: true,
                    filterControl: 'input',
                    formatter: safeRecordText
                }, {
                    field: 'match_degree',
                    title: '匹配度',
                    visible: false,
                    sortable: true,
                    filterControl: 'input',
                    formatter: safeRecordText
                }, {
                    field: 'submit',
                    title: '状态',
                    sortable: true,
                    filterControl: 'input',
                    formatter: recordStatus
                }, {
                    field: 'title',
                    title: '职位',
                    sortable: true,
                    filterControl: 'input',
                    formatter:function(value,row){
                        if(row.link){
                            if (row.source==='智联招聘'){
                                if (row.link.includes('zhaopin.com/jobdetail')){
                                    return recordLink(value, row.link);
                                } else {
                                    return escapeHtml(value);
                                }
                            } else if(row.source==='国聘网') {
                                return escapeHtml(value);
                            } else {
                                return recordLink(value, row.link);
                            }
                        } else {
                            return escapeHtml(value);
                        }
                      }
                }, {
                    field: 'employment_type',
                    title: '岗位类型',
                    sortable: true,
                    filterControl: 'select',
                    formatter: function (value) {
                        return safeRecordText(value === 'internship' ? '实习' :
                            value === 'full_time' ? '全职' : '待确认');
                    }
                }, {
                    field: 'recruitment_track',
                    title: '招聘渠道',
                    sortable: true,
                    filterControl: 'select',
                    formatter: function (value) {
                        return safeRecordText(value === 'campus' ? '校招' :
                            value === 'social' ? '社招' : '待确认');
                    }
                }, {
                    field: 'company',
                    title: '公司',
                    sortable: true,
                    filterControl: 'input',
                    formatter:function(value,row){
                        if(row.link){
                            if (row.source==='智联招聘'){
                                if (row.link.includes('zhaopin.com/companydetail')){
                                    return recordLink(value, row.link);
                                } else {
                                    return escapeHtml(value);
                                }
                            } else if(row.source==='国聘网') {
                                return recordLink(value, row.link);
                            } else {
                                return escapeHtml(value);
                            }
                        } else {
                            return escapeHtml(value);
                        }
                      }
                }, {
                    field: 'area',
                    title: '地区',
                    sortable: true,
                    filterControl: 'input',
                    formatter: safeRecordText
                }, {
                    field: 'search_city',
                    title: '搜索城市',
                    visible: false,
                    sortable: true,
                    filterControl: 'input',
                    formatter: safeRecordText
                }, {
                    field: 'salary',
                    title: '薪资',
                    sortable: true,
                    filterControl: 'input',
                    formatter: function (value) {
                        return value === '薪资待解析' ?
                            '<span class="salary-unreadable" title="网站薪资字形未能可靠识别，请打开职位查看">薪资待解析</span>' :
                            safeRecordText(value);
                    }
                }, {
                    field: 'experience',
                    title: '经验',
                    sortable: true,
                    filterControl: 'input',
                    formatter: safeRecordText
                }, {
                    field: 'education',
                    title: '学历',
                    sortable: true,
                    filterControl: 'input',
                    formatter: safeRecordText
                }, {
                    field: 'submit_time',
                    title: '投递日期',
                    visible: false,
                    sortable: true,
                    filterControl: 'input',
                    formatter: safeRecordText
                }, {
                    field: 'remarks',
                    title: '备注',
                    sortable: true,
                    filterControl: 'input',
                    formatter: function (value, row) {
                        var text = safeRecordText(value);
                        return row.attempt_state === 'pending' && ['BOSS直聘', '智联招聘', '前程无忧', '应届生', '猎聘', '拉勾', '牛客网', '国聘网'].includes(row.source) ?
                            text + ' <button type="button" class="btn btn-outline-primary btn-sm reconcile-apply-record" data-id="' +
                            Number(row.id) + '">核实</button>' : text;
                    }
                }],
                iconsPrefix: 'bi',
                detailView: true,
                detailFormatter: recordDetail,
                pagination: true,
                locale: 'zh-cn',
                pageSize: 50,
                pageList: [50, 100, 200, 500],
                search: true,
                showColumns: true,
                showRefresh: false,
                toolbar: '.toolbar',
                filterControl: true,
                exportTypes: ['excel', 'json', 'csv', 'txt', 'sql'],
                data: ApplyData,
                classes: 'table table-sm table-hover',
                formatNoMatches: function () {
                    return '暂无相关数据';
                }
            });

            $('.datepicker').datepicker({
                format: 'yyyy-mm-dd',
                language: 'zh-CN',
                autoclose: true
            });
            
            // 初始化图表
            initCharts(ApplyData);
        })

        pywebview.api.get_chat_record().then(function (chatRecord) {
            ChatData = chatRecord
            $('#chat-table').bootstrapTable({
                columns: [{
                    field: 'create_time',
                    title: '日期',
                    sortable: true,
                    filterControl: 'input',
                    formatter: safeRecordText
                }, {
                    field: 'source',
                    title: '平台',
                    sortable: true,
                    filterControl: 'input',
                    formatter: safeRecordText
                },{
                    field: 'title',
                    title: '职位',
                    sortable: true,
                    filterControl: 'input',
                    formatter: safeRecordText
                }, {
                    field: 'company',
                    title: '公司',
                    sortable: true,
                    filterControl: 'input',
                    formatter: safeRecordText
                }, {
                    field: 'hr_name',
                    title: '招聘者',
                    sortable: true,
                    filterControl: 'input',
                    formatter: safeRecordText
                }, {
                    field: 'option',
                    title: '操作',
                    sortable: true,
                    filterControl: 'input',
                    formatter: safeRecordText
                }, {
                    field: 'msg_reply',
                    title: '消息/回复',
                    sortable: true,
                    filterControl: 'input',
                    formatter: safeRecordText
                }, {
                    field: 'remarks',
                    title: '备注',
                    sortable: true,
                    filterControl: 'input',
                    formatter: safeRecordText
                }],
                iconsPrefix: 'bi',
                pagination: true,
                locale: 'zh-cn',
                pageSize: 100,
                pageList: [100, 400, 700, 1000, 3000],
                search: true,
                showColumns: true,
                showRefresh: false,
                toolbar: '.toolbar',
                filterControl: true,
                exportTypes: ['excel', 'json', 'csv', 'txt', 'sql'],
                data: ChatData,
                classes: 'table table-sm table-hover',
                formatNoMatches: function () {
                    return '暂无相关数据';
                }
            });

            $('.datepicker').datepicker({
                format: 'yyyy-mm-dd',
                language: 'zh-CN',
                autoclose: true
            });
        })

        $('#date-filter').click(function () {
            var start = $('#start-date').val();
            var end = $('#end-date').val();
            if (start && end) {
                var ApplyDataFiltered = RecordMetrics.filterByDate(ApplyData || [], start, end);
                var ChatDataFiltered = (ChatData || []).filter(function (item) {
                    var day = String(item.create_time || '').slice(0, 10);
                    return day >= start && day <= end;
                });
                $('#record-table').bootstrapTable('load', ApplyDataFiltered);
                $('#chat-table').bootstrapTable('load', ChatDataFiltered);
                initCharts(ApplyDataFiltered);
                updateRecordSummary(ApplyDataFiltered);
            } else {
                showTip('warring', '', '请选择开始日期和结束日期')
            }
        })
        
        $('#reset').click(function () {
            $('#start-date').val('');
            $('#end-date').val('');
            $('#record-table').bootstrapTable('load', ApplyData);
            $('#chat-table').bootstrapTable('load', ChatData);
            initCharts(ApplyData || []);
            updateRecordSummary(ApplyData || []);
        })
        
        $('.record-window #tip-modal').on('hidden.bs.modal', function (e) {
          location.reload()
        })
    });

    var chartInstances = {};
    function clearChart(id) {
        if (chartInstances[id]) {
            chartInstances[id].destroy();
            delete chartInstances[id];
        }
    }

    // 初始化图表
    function initCharts(data) {
        data = data || [];
        
        // 确保 DOM 元素加载完成后再绘制图表
        setTimeout(function() {
            // 绘制 7 日投递数量折线图
            if (document.getElementById('dailyTrendChart')) {
                drawDailyTrendChart(data);
            }
            
            // 绘制当日平台占比饼状图
            if (document.getElementById('platformPieChart')) {
                drawPlatformPieChart(data);
            }
            
            // 绘制当日匹配度占比饼状图
            if (document.getElementById('matchDegreePieChart')) {
                drawMatchDegreePieChart(data);
            }
        }, 100);
    }
    
    // 绘制 7 日投递数量折线图
    function drawDailyTrendChart(data) {
        var trend = RecordMetrics.dailyTrend(data, formatDate(new Date()));
        var dates = trend.labels;
        var counts = trend.counts;
        
        // 绘制折线图
        clearChart('dailyTrendChart');
        var ctx = document.getElementById('dailyTrendChart').getContext('2d');
        chartInstances.dailyTrendChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: dates,
                datasets: [{
                    label: '投递数量',
                    data: counts,
                    borderColor: 'rgb(54, 162, 235)',
                    tension: 0.1,
                    fill: true,
                    backgroundColor: 'rgba(54, 162, 235, 0.2)'
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: 'top',
                    },
                    title: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    }
                }
            }
        });
    }
    
    // 绘制当日平台占比饼状图
    function drawPlatformPieChart(data) {
        var today = formatDate(new Date());
        var platformData = RecordMetrics.platformCounts(data, today);
        
        // 转换为饼状图数据格式
        var labels = Object.keys(platformData);
        var values = Object.values(platformData);
        
        // 绘制饼状图
        clearChart('platformPieChart');
        var ctx = document.getElementById('platformPieChart').getContext('2d');
        
        // 确保有数据再绘制饼状图
        if (labels.length > 0 && values.length > 0) {
            chartInstances.platformPieChart = new Chart(ctx, {
                type: 'pie',
                data: {
                    labels: labels,
                    datasets: [{
                        data: values,
                        backgroundColor: [
                            'rgba(255, 99, 132, 0.8)',
                            'rgba(54, 162, 235, 0.8)',
                            'rgba(255, 206, 86, 0.8)',
                            'rgba(75, 192, 192, 0.8)',
                            'rgba(153, 102, 255, 0.8)',
                            'rgba(255, 159, 64, 0.8)'
                        ],
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: {
                            position: 'bottom',
                        },
                        title: {
                            display: false
                        }
                    }
                }
            });
        } else {
            // 如果没有数据，显示提示信息
            var canvas = document.getElementById('platformPieChart');
            var context = canvas.getContext('2d');
            context.clearRect(0, 0, canvas.width, canvas.height);
            context.font = '14px Arial';
            context.fillStyle = '#666';
            context.textAlign = 'center';
            context.fillText('暂无数据', canvas.width / 2, canvas.height / 2);
        }
    }
    
    // 绘制当日匹配度占比饼状图
    function drawMatchDegreePieChart(data) {
        var today = formatDate(new Date());
        var matchDegreeData = RecordMetrics.matchDegreeCounts(data, today);
        
        // 过滤掉数量为 0 的范围
        var labels = [];
        var values = [];
        for (var range in matchDegreeData) {
            if (matchDegreeData[range] > 0) {
                labels.push(range);
                values.push(matchDegreeData[range]);
            }
        }
        
        // 绘制饼状图
        clearChart('matchDegreePieChart');
        var ctx = document.getElementById('matchDegreePieChart').getContext('2d');
        
        // 确保有数据再绘制饼状图
        if (labels.length > 0 && values.length > 0) {
            chartInstances.matchDegreePieChart = new Chart(ctx, {
                type: 'pie',
                data: {
                    labels: labels,
                    datasets: [{
                        data: values,
                        backgroundColor: [
                            'rgba(255, 99, 132, 0.8)',
                            'rgba(54, 162, 235, 0.8)',
                            'rgba(255, 206, 86, 0.8)',
                            'rgba(75, 192, 192, 0.8)',
                            'rgba(153, 102, 255, 0.8)',
                            'rgba(255, 159, 64, 0.8)',
                            'rgba(199, 199, 199, 0.8)',
                            'rgba(83, 102, 255, 0.8)',
                            'rgba(255, 99, 255, 0.8)',
                            'rgba(255, 199, 64, 0.8)',
                            'rgba(99, 255, 132, 0.8)'
                        ],
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: {
                            position: 'bottom',
                        },
                        title: {
                            display: false
                        }
                    }
                }
            });
        } else {
            // 如果没有数据，显示提示信息
            var canvas = document.getElementById('matchDegreePieChart');
            var context = canvas.getContext('2d');
            context.clearRect(0, 0, canvas.width, canvas.height);
            context.font = '14px Arial';
            context.fillStyle = '#666';
            context.textAlign = 'center';
            context.fillText('暂无数据', canvas.width / 2, canvas.height / 2);
        }
    }
    
    // 格式化日期为 YYYY-MM-DD
    function formatDate(date) {
        var year = date.getFullYear();
        var month = String(date.getMonth() + 1).padStart(2, '0');
        var day = String(date.getDate()).padStart(2, '0');
        return year + '-' + month + '-' + day;
    }
})
