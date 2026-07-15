let goldChart = null;
let priceHistory = [];
let refreshTimer = null;
let currentInterval = 60;

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
    setInterval(loadPrice, 5000);
    updateStatus(true);
});

function switchTab(name) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');
    document.querySelector(`.nav-item[data-tab="${name}"]`).classList.add('active');
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
            html += `
            <div class="pnl-card ${isProfit ? 'profit' : 'loss'}">
                <div class="pnl-header">
                    <div>
                        <div class="pnl-title">${escapeHtml(p.note) || '记录 #' + (i+1)}</div>
                        <div class="pnl-detail">
                            <span>买入 ${p.purchase_price}元/克</span>
                            <span>手续费 ${p.fee}%</span>
                        </div>
                    </div>
                    <div class="pnl-value ${isProfit ? 'profit' : 'loss'}">
                        ${sign}${p.pnl}元/克
                    </div>
                </div>
                <div class="pnl-detail">
                    <span>当前价 ${p.current_price}元/克</span>
                    <span>${sign}${p.pnl_percent}%</span>
                    <span style="margin-left:auto;cursor:pointer;color:var(--red)" onclick="deletePnl(${i})">删除</span>
                </div>
            </div>`;
        });
        el.innerHTML = html;
    } catch (e) { console.error(e); }
}

async function addPurchase() {
    const price = document.getElementById("buyPrice").value;
    const fee = document.getElementById("buyFee").value || 0;
    const note = document.getElementById("buyNote").value;
    if (!price) { showToast("请输入买入金价"); return; }
    await fetch("/api/pnl", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ price: parseFloat(price), fee: parseFloat(fee), note })
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
        document.getElementById("qqToken").value = qq.app_secret || "";
        document.getElementById("qqGroupId").value = qq.group_id || "";
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
    const qqSecret = document.getElementById("qqToken").value.trim();
    const qqGroup = document.getElementById("qqGroupId").value.trim();

    if (wechat) payload.wechat_webhook = wechat;
    if (feishu) payload.feishu_webhook = feishu;
    if (qqAppId && qqSecret) {
        payload.qq_bot = { app_id: qqAppId, app_secret: qqSecret, group_id: qqGroup };
    }

    await fetch("/api/config/push", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
    });

    if (qqAppId) {
        const webhookEl = document.getElementById("qqWebhookUrl");
        const urlEl = document.getElementById("webhookUrl");
        const host = window.location.origin;
        urlEl.textContent = host + '/webhook/qq';
        webhookEl.style.display = 'block';
    }

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
