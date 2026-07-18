let goldChart = null;
let priceHistory = [];
let refreshTimer = null;
let currentInterval = 60;
let searchResults = [];

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

document.addEventListener("DOMContentLoaded", () => {
    loadPrice();
    refreshChart();
    loadTodayPrices();
    loadPnl();
    loadConfig();
    loadVersion();
    loadWatches();
    setInterval(loadPrice, 5000);
    setInterval(loadWatches, 30000);
    updateStatus(true);
    initPnlCalc();
});

async function loadVersion() {
    try {
        const res = await fetch("/api/version");
        const data = await res.json();
        document.getElementById("currentVersion").textContent = "v" + data.current;
        if (data.latest) {
            document.getElementById("latestVersion").textContent = "v" + data.latest;
        }
        if (data.available) {
            document.getElementById("btnApplyUpdate").style.display = "inline-flex";
            showUpdateStatus("有新版本可用", "info");
        }
        if (data.updating) {
            document.getElementById("btnApplyUpdate").style.display = "inline-flex";
            showUpdateStatus(data.message, "info");
        }
    } catch (e) { console.error(e); }
}

async function checkUpdate() {
    document.getElementById("btnCheckUpdate").disabled = true;
    document.getElementById("btnCheckUpdate").textContent = "检查中...";
    try {
        const res = await fetch("/api/update/check", { method: "POST" });
        const data = await res.json();
        showUpdateStatus(data.msg, data.ok ? "success" : "error");
        if (data.ok) {
            const versionRes = await fetch("/api/version");
            const versionData = await versionRes.json();
            document.getElementById("latestVersion").textContent = "v" + versionData.latest;
            if (versionData.available) {
                document.getElementById("btnApplyUpdate").style.display = "inline-flex";
            }
        }
    } catch (e) {
        showUpdateStatus("检查失败", "error");
    }
    document.getElementById("btnCheckUpdate").disabled = false;
    document.getElementById("btnCheckUpdate").textContent = "检查更新";
}

async function applyUpdate() {
    if (!confirm("确定要更新吗？更新过程中服务将短暂中断。")) return;
    document.getElementById("btnApplyUpdate").disabled = true;
    showUpdateStatus("正在更新...", "info");
    try {
        const res = await fetch("/api/update/apply", { method: "POST" });
        const data = await res.json();
        showUpdateStatus(data.msg, data.ok ? "info" : "error");
    } catch (e) {
        showUpdateStatus("更新请求失败", "error");
    }
}

function showUpdateStatus(msg, type) {
    const el = document.getElementById("updateStatus");
    el.textContent = msg;
    el.className = "update-status show " + type;
}

function initPnlCalc() {
    const priceEl = document.getElementById("buyPrice");
    const weightEl = document.getElementById("buyWeight");
    const amountEl = document.getElementById("buyAmount");

    priceEl.addEventListener("input", () => {
        const p = parseFloat(priceEl.value) || 0;
        const w = parseFloat(weightEl.value) || 0;
        const a = parseFloat(amountEl.value) || 0;
        if (p > 0 && w > 0) {
            amountEl.value = (p * w).toFixed(2);
        } else if (p > 0 && a > 0) {
            weightEl.value = (a / p).toFixed(2);
        }
    });
    weightEl.addEventListener("input", () => {
        const p = parseFloat(priceEl.value) || 0;
        const w = parseFloat(weightEl.value) || 0;
        const a = parseFloat(amountEl.value) || 0;
        if (p > 0 && w > 0) {
            amountEl.value = (p * w).toFixed(2);
        } else if (w > 0 && a > 0) {
            priceEl.value = (a / w).toFixed(2);
        }
    });
    amountEl.addEventListener("input", () => {
        const p = parseFloat(priceEl.value) || 0;
        const w = parseFloat(weightEl.value) || 0;
        const a = parseFloat(amountEl.value) || 0;
        if (p > 0 && a > 0) {
            weightEl.value = (a / p).toFixed(2);
        } else if (w > 0 && a > 0) {
            priceEl.value = (a / w).toFixed(2);
        }
    });

    document.getElementById("buyPrice").value = document.getElementById("currentPrice").textContent.replace("元/克", "").trim() || "";
}

function switchTab(name) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');
    document.querySelector(`.nav-item[data-tab="${name}"]`).classList.add('active');
    if (name === 'watches') loadWatches();
}

function setChartRange(days, el) {
    document.querySelectorAll('.chart-controls .chip').forEach(c => c.classList.remove('active'));
    el.classList.add('active');
    refreshChart(days);
}

function setInterval_(seconds, el) {
    document.querySelectorAll('.interval-control .chip').forEach(c => c.classList.remove('active'));
    if (el) el.classList.add('active');
    document.getElementById('customInterval').value = '';
    currentInterval = seconds;
}

async function loadPrice() {
    try {
        const res = await fetch("/api/price");
        const data = await res.json();
        if (data.price) {
            const prev = priceHistory.length > 0 ? priceHistory[priceHistory.length - 1] : null;
            priceHistory.push(data.price);
            if (priceHistory.length > 100) priceHistory.shift();

            document.getElementById("currentPrice").textContent = data.price.toFixed(2);
            document.getElementById("priceTime").textContent = data.time.replace("T", " ").substring(0, 19);
            const sourceMap = { czbank: '浙商银行', jdjygold: '京东黄金', custom: '自定义' };
            document.getElementById("priceSource").textContent = sourceMap[data.source] || data.source;

            if (prev) {
                const diff = data.price - prev;
                const el = document.getElementById("priceChange");
                el.textContent = (diff >= 0 ? '+' : '') + diff.toFixed(2);
                el.className = 'meta-value ' + (diff >= 0 ? 'up' : 'down');
            }
            loadPnl();
            updateStatus(true);
        }
    } catch (e) {
        updateStatus(false);
        console.error(e);
    }
}

function updateStatus(online) {
    const dot = document.getElementById("statusDot");
    const text = document.getElementById("statusText");
    if (online) {
        dot.classList.add("online");
        text.textContent = "运行中";
    } else {
        dot.classList.remove("online");
        text.textContent = "连接失败";
    }
}

async function refreshChart(days = 30) {
    try {
        const res = await fetch("/api/chart?days=" + days);
        const data = await res.json();
        renderChart(data, days);
    } catch (e) { console.error(e); }
}

function renderChart(data, days) {
    const ctx = document.getElementById("goldChart").getContext("2d");
    if (goldChart) goldChart.destroy();

    const labels = data.map(d => d.date.substring(5));
    const avgPrices = data.map(d => d.avg_price ? parseFloat(d.avg_price.toFixed(2)) : null);
    const highPrices = data.map(d => d.high ? parseFloat(d.high.toFixed(2)) : null);
    const lowPrices = data.map(d => d.low ? parseFloat(d.low.toFixed(2)) : null);

    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, 'rgba(240,185,11,0.2)');
    gradient.addColorStop(1, 'rgba(240,185,11,0)');

    goldChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: labels,
            datasets: [
                {
                    label: "均价",
                    data: avgPrices,
                    borderColor: "#f0b90b",
                    backgroundColor: gradient,
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: days <= 7 ? 4 : 0,
                    pointHoverRadius: 6,
                    pointBackgroundColor: "#f0b90b",
                },
                {
                    label: "最高",
                    data: highPrices,
                    borderColor: "rgba(0,214,143,0.5)",
                    borderWidth: 1,
                    borderDash: [4, 4],
                    pointRadius: 0,
                    tension: 0.4,
                },
                {
                    label: "最低",
                    data: lowPrices,
                    borderColor: "rgba(255,71,87,0.5)",
                    borderWidth: 1,
                    borderDash: [4, 4],
                    pointRadius: 0,
                    tension: 0.4,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#1a1a25',
                    titleColor: '#9999aa',
                    bodyColor: '#e8e8ed',
                    borderColor: '#2a2a38',
                    borderWidth: 1,
                    padding: 12,
                    cornerRadius: 8,
                    callbacks: {
                        label: ctx => ctx.dataset.label + ": " + ctx.parsed.y + " 元/克"
                    }
                }
            },
            scales: {
                x: {
                    ticks: { color: '#666678', maxRotation: 0, font: { size: 11 } },
                    grid: { color: 'rgba(42,42,56,0.5)', drawBorder: false }
                },
                y: {
                    ticks: { color: '#666678', font: { size: 11 }, callback: v => v + '' },
                    grid: { color: 'rgba(42,42,56,0.5)', drawBorder: false },
                },
            },
        },
    });
}

async function loadTodayPrices() {
    try {
        const res = await fetch("/api/today");
        const data = await res.json();
        const el = document.getElementById("todayPrices");
        const countEl = document.getElementById("recordCount");
        countEl.textContent = data.length + "条";
        if (data.length === 0) {
            el.innerHTML = '<div class="empty-state">暂无数据</div>';
            return;
        }
        let html = "";
        data.forEach(p => {
            html += `<div class="record-item"><span class="record-time">${p.time}</span><span class="record-price">${p.price} 元/克</span></div>`;
        });
        el.innerHTML = html;
    } catch (e) { console.error(e); }
}

async function loadPnl() {
    try {
        const res = await fetch("/api/pnl");
        const data = await res.json();
        const el = document.getElementById("pnlResults");
        if (!data.purchases || data.purchases.length === 0) {
            el.innerHTML = '<div class="empty-state" style="margin-top:16px">暂无买入记录</div>';
            return;
        }
        let html = "";
        data.purchases.forEach((p, i) => {
            const isProfit = p.pnl >= 0;
            const sign = isProfit ? '+' : '';
            const weight = p.weight || 0;
            const amount = p.amount || (p.purchase_price * weight);
            const totalPnl = (p.pnl * weight).toFixed(2);
            html += `
            <div class="pnl-card ${isProfit ? 'profit' : 'loss'}">
                <div class="pnl-header">
                    <div>
                        <div class="pnl-title">${escapeHtml(p.note) || '记录 #' + (i+1)}</div>
                        <div class="pnl-detail">
                            <span>${p.purchase_price}元/克</span>
                            ${weight > 0 ? `<span>${weight}克</span>` : ''}
                            ${amount > 0 ? `<span>共${amount.toFixed(2)}元</span>` : ''}
                            <span>手续费${p.fee}%</span>
                        </div>
                    </div>
                    <div class="pnl-value ${isProfit ? 'profit' : 'loss'}">
                        ${sign}${p.pnl}元/克
                    </div>
                </div>
                <div class="pnl-detail">
                    <span>当前价 ${p.current_price}元/克</span>
                    <span>${sign}${p.pnl_percent}%</span>
                    ${weight > 0 ? `<span>盈亏 ${sign}${totalPnl}元</span>` : ''}
                    <span style="margin-left:auto;cursor:pointer;color:var(--red)" onclick="deletePnl(${i})">删除</span>
                </div>
            </div>`;
        });
        el.innerHTML = html;
    } catch (e) { console.error(e); }
}

async function addPurchase() {
    const price = document.getElementById("buyPrice").value;
    const weight = document.getElementById("buyWeight").value || 0;
    const amount = document.getElementById("buyAmount").value || 0;
    const fee = document.getElementById("buyFee").value || 0;
    const note = document.getElementById("buyNote").value;
    if (!price) { showToast("请输入买入金价"); return; }
    await fetch("/api/pnl", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            price: parseFloat(price),
            weight: parseFloat(weight),
            amount: parseFloat(amount),
            fee: parseFloat(fee),
            note
        })
    });
    document.getElementById("buyPrice").value = "";
    document.getElementById("buyNote").value = "";
    loadPnl();
    showToast("已添加");
}

async function deletePnl(idx) {
    await fetch("/api/pnl", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ delete_index: idx })
    });
    loadPnl();
}

async function loadConfig() {
    try {
        const res = await fetch("/api/config");
        const cfg = await res.json();
        document.getElementById("useCustomApi").checked = cfg.use_custom_api || false;
        document.getElementById("customApiUrl").value = cfg.custom_api_url || "";
        document.getElementById("alertEnabled").checked = cfg.alert_enabled || false;
        document.getElementById("alertLow").value = cfg.alert_threshold_low ?? "";
        document.getElementById("alertHigh").value = cfg.alert_threshold_high ?? "";
        if (cfg.fetch_interval) {
            currentInterval = cfg.fetch_interval;
            updateIntervalUI(cfg.fetch_interval);
        }
    } catch (e) { console.error(e); }

    try {
        const res = await fetch("/api/config/push");
        const pc = await res.json();
        document.getElementById("wechatWebhook").value = pc.wechat_webhook || "";
        document.getElementById("feishuWebhook").value = pc.feishu_webhook || "";
        const qq = pc.qq_bot || {};
        document.getElementById("qqAppId").value = qq.app_id || "";
        document.getElementById("qqToken").value = qq.token || qq.app_secret || "";
        document.getElementById("qqUserId").value = qq.user_id || "";
    } catch (e) { console.error(e); }
}

function updateIntervalUI(seconds) {
    document.querySelectorAll('.interval-control .chip').forEach(c => c.classList.remove('active'));
    const map = {60:0, 300:1, 600:2, 1800:3};
    if (map[seconds] !== undefined) {
        document.querySelectorAll('.interval-control .chip')[map[seconds]].classList.add('active');
        document.getElementById('customInterval').value = '';
    } else {
        document.getElementById('customInterval').value = seconds;
    }
}

async function saveSourceSettings() {
    const customVal = document.getElementById("customInterval").value;
    const interval = customVal ? parseInt(customVal) : currentInterval;
    await fetch("/api/config", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            use_custom_api: document.getElementById("useCustomApi").checked,
            custom_api_url: document.getElementById("customApiUrl").value,
            fetch_interval: interval,
        })
    });
    await fetch("/api/config/interval", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ interval })
    });
    showToast("设置已保存");
}

async function savePushSettings() {
    const payload = {};
    const wechat = document.getElementById("wechatWebhook").value.trim();
    const feishu = document.getElementById("feishuWebhook").value.trim();
    const qqAppId = document.getElementById("qqAppId").value.trim();
    const qqToken = document.getElementById("qqToken").value.trim();
    const qqUserId = document.getElementById("qqUserId").value.trim();

    if (wechat) payload.wechat_webhook = wechat;
    if (feishu) payload.feishu_webhook = feishu;
    if (qqAppId && qqToken) {
        payload.qq_bot = {
            app_id: qqAppId,
            token: qqToken,
            user_id: qqUserId,
        };
    }

    await fetch("/api/config/push", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
    });
    showToast("推送设置已保存");
}

async function saveAlertSettings() {
    await fetch("/api/config", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            alert_enabled: document.getElementById("alertEnabled").checked,
            alert_threshold_low: parseFloat(document.getElementById("alertLow").value) || 0,
            alert_threshold_high: parseFloat(document.getElementById("alertHigh").value) || 9999,
        })
    });
    showToast("预警设置已保存");
}

async function testPush(channel) {
    try {
        const res = await fetch("/api/push/test", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ channel })
        });
        const data = await res.json();
        showToast(data.ok ? "推送成功" : "失败: " + data.msg);
    } catch (e) { showToast("测试失败"); }
}

async function searchWatch() {
    const input = document.getElementById("watchSearchInput");
    const keyword = input.value.trim();
    if (!keyword) return;
    const btn = document.getElementById("btnSearchWatch");
    btn.textContent = "搜索中...";
    btn.disabled = true;
    try {
        const res = await fetch("/api/watches", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ keyword })
        });
        const data = await res.json();
        renderSearchResults(data.results || []);
    } catch (e) {
        showToast("搜索失败");
    }
    btn.textContent = "搜索";
    btn.disabled = false;
}

function renderSearchResults(results) {
    const el = document.getElementById("searchResults");
    if (results.length === 0) {
        el.innerHTML = '<div class="empty-state">未找到相关结果</div>';
        return;
    }
    searchResults = results;
    let html = '<div class="search-result-list">';
    results.forEach((item, i) => {
        const t = typeLabel[item.type] || item.type;
        const typeClass = item.type === 'futures' ? ' futures' : '';
        const pct = item.change_pct || 0;
        const sign = pct >= 0 ? '+' : '';
        const color = pct >= 0 ? 'var(--green)' : 'var(--red)';
        html += `
        <div class="search-result-item" onclick="addWatchItem(${i})">
            <div class="result-info">
                <span class="result-type${typeClass}">${t}</span>
                <span class="result-name">${escapeHtml(item.name)}</span>
                <span class="result-code">${item.code}</span>
            </div>
            <div class="result-price">
                <span>${item.price}</span>
                <span style="color:${color}">${sign}${pct}%</span>
            </div>
        </div>`;
    });
    html += '</div>';
    el.innerHTML = html;
}

async function addWatchItem(index) {
    const item = searchResults[index];
    if (!item) return;
    try {
        const res = await fetch("/api/watches", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ keyword: item.code })
        });
        const data = await res.json();
        if (data.ok && data.results && data.results.length > 0) {
            const added = data.results[0];
            const typeLabel = {a_stock: 'A股', hk_stock: '港股', fund: '基金', futures: '期货'};
            showToast(`已添加: ${typeLabel[added.type] || ''} ${added.name}`);
            loadWatches();
            document.getElementById("searchResults").innerHTML = '';
            document.getElementById("watchSearchInput").value = '';
        }
    } catch (e) {
        showToast("添加失败");
    }
}

async function loadWatches() {
    try {
        const res = await fetch("/api/watches");
        const data = await res.json();
        const el = document.getElementById("watchList");
        const countEl = document.getElementById("watchCount");
        const watches = data.watches || [];
        countEl.textContent = watches.length + "条";
        if (watches.length === 0) {
            el.innerHTML = '<div class="empty-state">暂无监控，搜索添加股票/基金</div>';
            return;
        }
        const typeLabel = {a_stock: 'A股', hk_stock: '港股', fund: '基金', futures: '期货'};
        let html = "";
        watches.forEach((w, i) => {
            const t = typeLabel[w.type] || w.type;
            const typeClass = w.type === 'futures' ? ' futures' : '';
            const price = w.price || '-';
            const pct = w.change_pct || 0;
            const sign = pct >= 0 ? '+' : '';
            const color = pct >= 0 ? 'var(--green)' : 'var(--red)';
            const time = w.time || '--';
            html += `
            <div class="watch-item">
                <div class="watch-info">
                    <span class="watch-type${typeClass}">${t}</span>
                    <div class="watch-name">${escapeHtml(w.name || '')}</div>
                    <div class="watch-code">${w.code}</div>
                </div>
                <div class="watch-price">
                    <div class="watch-current">${price}</div>
                    <div class="watch-pct" style="color:${color}">${sign}${pct}%</div>
                    <div class="watch-time">${time}</div>
                </div>
                <div class="watch-actions">
                    <span class="watch-delete" onclick="deleteWatch(${i})">删除</span>
                </div>
            </div>`;
        });
        el.innerHTML = html;
    } catch (e) { console.error(e); }
}

async function deleteWatch(index) {
    try {
        await fetch(`/api/watches?index=${index}`, { method: "DELETE" });
        loadWatches();
        showToast("已删除");
    } catch (e) {
        showToast("删除失败");
    }
}

async function sendChat() {
    const input = document.getElementById("chatInput");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    addChatMsg(text, "user");
    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ message: text })
        });
        const data = await res.json();
        addChatMsg(data.response || "未知响应", "bot");
        if (text.includes("添加监控") || text.includes("删除")) {
            loadWatches();
        }
    } catch (e) {
        addChatMsg("发送失败: " + e.message, "system");
    }
}

function addChatMsg(text, type) {
    const el = document.getElementById("chatMessages");
    const msg = document.createElement("div");
    msg.className = "chat-msg " + type;
    msg.textContent = text;
    el.appendChild(msg);
    el.scrollTop = el.scrollHeight;
}

function showToast(msg) {
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 2000);
}
