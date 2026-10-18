let frameCount = 0;
let lastFrameTime = Date.now();
let requestInProgress = false;
let updateTabsRunning = false;
let lastTabsData = null;
let frameLoopScheduled = false;
let moveThrottleLock = false;

const loadingEl = document.getElementById('loading');
const browserFrame = document.getElementById('browser-frame');
const tabsContainer = document.getElementById('tabs-container');
const statusEl = document.getElementById('status');

function showLoading() {
    loadingEl.style.display = 'block';
    browserFrame.style.display = 'none';
}

function hideLoading() {
    loadingEl.style.display = 'none';
    browserFrame.style.display = 'block';
}

function isTabsEqual(a, b) {
    if (!a || !b || a.length !== b.length) return false;
    return a.every((item, idx) => {
        const target = b[idx];
        return item.id === target.id && item.title === target.title && item.active === target.active;
    });
}

function updateTabs() {
    if(updateTabsRunning) return;
    updateTabsRunning = true;
    window.pywebview.api.get_tabs().then(function (tabs) {
        if(isTabsEqual(tabs, lastTabsData)) return;
        lastTabsData = JSON.parse(JSON.stringify(tabs));
        tabsContainer.innerHTML = '';
        tabs.forEach(function (tab) {
            const tabEl = document.createElement('div');
            tabEl.className = 'tab' + (tab.active ? ' active' : '');
            tabEl.dataset.tabId = tab.id;

            const titleEl = document.createElement('span');
            titleEl.className = 'tab-title';
            titleEl.textContent = tab.title;

            // const closeEl = document.createElement('span');
            // closeEl.className = 'tab-close';
            // closeEl.textContent = '×';
            // closeEl.addEventListener('click', function (e) {
            //     e.stopPropagation();
            //     window.pywebview.api.close_tab(tab.id).catch(err=>console.error(err));
            // });

            tabEl.appendChild(titleEl);
            // tabEl.appendChild(closeEl);

            tabEl.addEventListener('click', function () {
                window.pywebview.api.switch_tab(tab.id).catch(err=>console.error(err));
            });

            tabsContainer.appendChild(tabEl);
        });
    }).catch(function (err) {
        console.error(err);
    }).finally(()=>{
        updateTabsRunning = false;
    });
}

function scheduleFrameLoop() {
    if(frameLoopScheduled) return;
    frameLoopScheduled = true;
    window.pywebview.api.get_frame().then(function (frame) {
        frameLoopScheduled = false;
        if (frame) {
            // 仅在画面真正变化时替换图片，避免相同数据重复解码造成卡顿
            if(browserFrame.src !== frame){
                browserFrame.src = frame;
            }
            hideLoading();
            frameCount++;

            if (frameCount % 60 === 0) {
                const costMs = Date.now() - lastFrameTime;
                const fps = (60 / (costMs / 1000)).toFixed(1);
                statusEl.textContent = 'Connected! | Frames: ' + frameCount + ' | ' + fps + ' fps';
                lastFrameTime = Date.now();
            }

            if (frameCount === 1) {
                statusEl.textContent = 'Connected!';
            }
        } else if (frameCount === 0) {
            // 长轮询无新帧是正常现象（页面静止/浏览器推流间隙），
            // 只有从未收到过帧时才显示加载中，避免画面闪烁
            showLoading();
        }
        requestAnimationFrame(scheduleFrameLoop);
    }).catch(function (err) {
        frameLoopScheduled = false;
        console.error(err);
        setTimeout(scheduleFrameLoop, 100);
    });
}

setTimeout(scheduleFrameLoop, 1500);
setInterval(updateTabs, 2000);

let isMouseDown = false;
let hasMoved = false;
let mouseDownTime = 0;
let mouseDownX = 0;
let mouseDownY = 0;
let mouseButtons = 0;
let lastMouseX = 0;
let lastMouseY = 0;

function getCoords(e) {
    const frame = browserFrame;
    const rect = frame.getBoundingClientRect();

    const actualWidth = frame.naturalWidth || 1280;
    const actualHeight = frame.naturalHeight || 800;

    const scaleX = actualWidth / rect.width;
    const scaleY = actualHeight / rect.height;

    const x = Math.round((e.clientX - rect.left) * scaleX);
    const y = Math.round((e.clientY - rect.top) * scaleY);
    return {x, y};
}

async function sendMouseEvent(event_type, e) {
    const coords = getCoords(e);
    try{
        await pywebview.api.dispatch_mouse_event(event_type, coords.x, coords.y, e.button, mouseButtons);
    }catch(err){
        console.error(err);
    }
}

browserFrame.addEventListener('mousedown', function (e) {
    e.preventDefault();
    isMouseDown = true;
    hasMoved = false;
    const coords = getCoords(e);
    mouseDownX = coords.x;
    mouseDownY = coords.y;
    mouseButtons |= (1 << e.button);
    sendMouseEvent('mouseDown', e);
});

browserFrame.addEventListener('mousemove', function (e) {
    if(moveThrottleLock) return;
    moveThrottleLock = true;
    setTimeout(()=>{
        const coords = getCoords(e);
        if (coords.x !== lastMouseX || coords.y !== lastMouseY) {
            sendMouseEvent('mouseMove', e);
            lastMouseX = coords.x;
            lastMouseY = coords.y;
        }
        if (isMouseDown && !hasMoved) {
            const distance = Math.sqrt(Math.pow(coords.x - mouseDownX, 2) + Math.pow(coords.y - mouseDownY, 2));
            if (distance > 3) {
                hasMoved = true;
            }
        }
        moveThrottleLock = false;
    }, 8);
});

document.addEventListener('mouseup', function (e) {
    if (isMouseDown) {
        sendMouseEvent('mouseUp', e);
        isMouseDown = false;
        mouseButtons &= ~(1 << e.button);
        hasMoved = false;
    }
});

document.addEventListener('mouseleave', function (e) {
    if (isMouseDown) {
        sendMouseEvent('mouseUp', e);
        isMouseDown = false;
        mouseButtons = 0;
        hasMoved = false;
    }
});

window.addEventListener('blur', function(){
    if(isMouseDown){
        sendMouseEvent('mouseUp', {});
    }
    isMouseDown = false;
    mouseButtons = 0;
    hasMoved = false;
});

browserFrame.addEventListener('wheel', function (e) {
    e.preventDefault();
    const coords = getCoords(e);
    pywebview.api.handle_mouse_wheel(coords.x, coords.y, e.deltaX, e.deltaY).catch(err=>console.error(err));
});

document.addEventListener('keydown', async function (e) {
    if(e.repeat) return;
    const specialKeys = ['Enter', 'Backspace', 'Tab', 'Escape', 'ArrowUp', 'ArrowDown',
        'ArrowLeft', 'ArrowRight', 'Delete', 'Home', 'End',
        'PageUp', 'PageDown', ' '];

    try{
        if (specialKeys.includes(e.key)) {
            e.preventDefault();
            await pywebview.api.handle_keyboard_event(e.key);
        } else if (e.key.length === 1) {
            await pywebview.api.handle_keyboard_event(e.key);
        }
    }catch(err){
        console.error(err);
    }
});