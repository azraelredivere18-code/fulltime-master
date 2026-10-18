const PROFILE_FIELDS = [
    ['full_name','姓名'],['phone','手机号'],['email','电子邮箱'],['id_number','身份证号'],
    ['gender','性别'],['birth_date','出生日期'],['ethnicity','民族'],['political_status','政治面貌'],
    ['household_registration','户籍所在地'],['current_city','现居城市'],['address','通信地址'],
    ['university','毕业院校'],['degree','学位'],['education','最高学历'],['major','专业'],
    ['graduation_date','毕业日期'],['school_start_date','入学日期'],['work_years','工作年限'],
    ['self_intro','自我介绍'],['skills','技能特长']
];
const names = Object.fromEntries(PROFILE_FIELDS);
const fields = document.getElementById('profile-fields');
for (const [key,label] of PROFILE_FIELDS) {
    const group = document.createElement('div');
    if (['self_intro','skills'].includes(key)) group.className = 'wide';
    const caption = document.createElement('label');
    caption.htmlFor = 'profile-' + key;
    caption.textContent = label;
    const input = ['self_intro','skills'].includes(key) ? document.createElement('textarea') : document.createElement('input');
    input.id = 'profile-' + key;
    input.dataset.key = key;
    if (input.tagName === 'INPUT') input.type = key === 'id_number' ? 'password' : key === 'email' ? 'email' : 'text';
    input.autocomplete = 'off';
    input.disabled = true;
    group.append(caption,input);
    fields.append(group);
}
const byId = id => document.getElementById(id);
let profileDirty = false;
let profileReady = false;
let editVersion = 0;
let previewReady = false;
let lastPageUrl = '';
byId('fill-form').disabled = true;
byId('save-profile').disabled = true;
fields.addEventListener('input',() => {
    editVersion++;
    profileDirty = true;
    previewReady = false;
    byId('fill-form').disabled = true;
    setStatus('save-status','资料有未保存的修改。');
});
const setStatus = (id,text) => { byId(id).textContent = text; };
const call = async (name,...args) => {
    try { return await window.pywebview.api[name](...args); }
    catch (error) { setStatus('fill-result','操作失败：' + String(error)); return null; }
};
function profileFromForm() {
    return Object.fromEntries(Array.from(fields.querySelectorAll('[data-key]'))
        .map(input => [input.dataset.key,input.value.trim()]));
}
function showFormResult(result, preview) {
    if (!result) return;
    if (result.state !== 'ok') {
        setStatus('fill-result',result.reason || '当前页面不可填写：请核对网页网址与已确认域名。');
        return;
    }
    const labels = Object.fromEntries((result.targets || []).map(row => [row.field,row.label]));
    const available = (preview ? result.available || [] : result.filled || []).map(key =>
        (names[key] || key) + (labels[key] ? '（网页：' + labels[key] + '）' : ''));
    const skipped = (result.skipped || []).map(row => (names[row.field] || row.field) + '：' + row.reason);
    setStatus('fill-result', (preview ? '识别到可填写字段：' : '已填写字段：') +
        (available.join('、') || '无') + '\n' +
        (skipped.length ? '跳过：' + skipped.join('；') + '\n' : '') +
        (result.frames ? '页面含 ' + result.frames + ' 个内嵌表单，需人工处理。\n' : '') +
        (preview ? '确认后点击“填写空白字段”。' : '请在浏览器中核对每一项，然后自行提交。'));
}
async function refreshPageStatus() {
    const status = await call('official_page_status');
    if (!status) return;
    if (status.url !== lastPageUrl || status.state !== 'ready') {
        previewReady = false;
        byId('fill-form').disabled = true;
    }
    lastPageUrl = status.url;
    const label = status.state === 'ready' ? '已确认当前域名' :
        status.state === 'redirected' ? '网站已跳转，请核对并确认当前域名' :
        status.state === 'loading' ? '正在打开目标页面，请稍候' : '浏览器未打开';
    setStatus('page-status',label + (status.url ? ' · ' + status.url : ''));
}
window.addEventListener('pywebviewready',async () => {
    const profile = await call('get_official_profile');
    if (profile && !profileDirty) for (const [key,value] of Object.entries(profile)) {
        const input = byId('profile-' + key);
        if (input) input.value = value;
    }
    profileReady = !!profile;
    fields.querySelectorAll('[data-key]').forEach(input => { input.disabled = !profileReady; });
    byId('save-profile').disabled = !profileReady;
    if (!profileReady) setStatus('save-status','资料未能读取，请检查当前 Windows 账户。');
    await refreshPageStatus();
    setInterval(refreshPageStatus,5000);
});
byId('open-site').addEventListener('click',async () => {
    previewReady = false;
    byId('fill-form').disabled = true;
    const result = await call('open_official_site',byId('official-url').value);
    if (result && result.state === 'error') setStatus('page-status',result.reason);
    else await refreshPageStatus();
});
byId('trust-current').addEventListener('click',async () => {
    previewReady = false;
    byId('fill-form').disabled = true;
    const status = await call('official_page_status');
    if (!status || !status.url || !window.confirm('请核对浏览器当前网址：\n' + status.url + '\n\n确认在此域名填写个人资料？')) return;
    const result = await call('trust_current_official_site');
    if (result && result.state === 'error') setStatus('page-status',result.reason);
    else await refreshPageStatus();
});
byId('save-profile').addEventListener('click',async () => {
    if (!profileReady) return;
    const snapshot = profileFromForm();
    const version = editVersion;
    byId('save-profile').disabled = true;
    const saved = await call('save_official_profile',snapshot);
    byId('save-profile').disabled = false;
    if (saved && version === editVersion) profileDirty = false;
    setStatus('save-status',saved ?
        (profileDirty ? '保存期间资料又被修改，请再次保存。' : '资料已加密保存到本机当前 Windows 账户。') :
        '保存失败。');
    previewReady = false;
    byId('fill-form').disabled = true;
});
byId('clear-profile').addEventListener('click',async () => {
    if (!window.confirm('清空本机保存的个人资料？')) return;
    const version = editVersion;
    const cleared = await call('clear_official_profile');
    if (cleared) {
        if (version === editVersion) {
            fields.querySelectorAll('[data-key]').forEach(input => { input.value = ''; });
            profileDirty = false;
            setStatus('save-status','本机资料已清空。');
        } else setStatus('save-status','本机资料已清空，但编辑中的内容尚未保存。');
        previewReady = false;
        byId('fill-form').disabled = true;
    }
});
byId('inspect-form').addEventListener('click',async () => {
    if (!profileReady) { setStatus('fill-result','请等待个人资料加载。'); return; }
    if (profileDirty) { setStatus('fill-result','请先加密保存已修改的个人资料。'); return; }
    previewReady = false;
    byId('fill-form').disabled = true;
    const result = await call('inspect_official_form');
    showFormResult(result,true);
    previewReady = !!(result && result.state === 'ok' && (result.available || []).length);
    byId('fill-form').disabled = !previewReady;
});
byId('fill-form').addEventListener('click',async () => {
    if (!previewReady) { setStatus('fill-result','请先识别当前表单。'); return; }
    if (profileDirty) { setStatus('fill-result','请先加密保存已修改的个人资料。'); return; }
    if (!window.confirm('将已保存资料填入当前网页的空白字段？填写后请自行核对并提交。')) return;
    previewReady = false;
    byId('fill-form').disabled = true;
    showFormResult(await call('fill_official_form',byId('include-id').checked),false);
});
byId('record-application').addEventListener('click',async () => {
    if (!window.confirm('你是否已在企业官网看到投递成功提示？程序不会代你核实网页回执。')) return;
    const result = await call('record_official_application',{
        company:byId('record-company').value.trim(),
        title:byId('record-title').value.trim(),area:byId('record-area').value.trim()
    });
    setStatus('record-status',result ? result.reason : '记录失败。');
});
