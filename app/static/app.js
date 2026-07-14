let goldChart = null;

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

document.addEventListener("DOMContentLoaded", () => {
    initTabs();
    loadPrice();
    refreshChart();
    loadTodayPrices();
    loadPnl();
    loadConfig();
    setInterval(loadPrice, 30000);
});

function initTabs() {
    document.querySelectorAll(".tab").forEach(tab => {
        tab.addEventListener("click", () => {
            document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
            document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
            tab.classList.add("active");
            document.getElementById("tab-" + tab.dataset.tab).classList.add("active");
        });
    });
}

async function loadPrice() {
    try {
        const res = await fetch("/api/price");
        const data = await res.json();
        if (data.price) {
            document.getElementById("currentPrice").textContent = data.price.toFixed(2) + " 元/克";
            document.getElementById("priceTime").textContent =
                data.time.replace("T", " ").substring(0, 19) + " (" + data.source + ")";
        }
    } catch (e) { console.error(e); }
}

async function refreshChart() {
    const days = parseInt(document.getElementById("chartDays").value);
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
    const avgPrices = data.map(d => d.avg_price ? d.avg_price.toFixed(2) : null);
    const highPrices = data.map(d => d.high ? d.high.toFixed(2) : null);
    const lowPrices = data.map(d => d.low ? d.low.toFixed(2) : null);

    goldChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: labels,
            datasets: [
                {
                    label: "均价",
                    data: avgPrices,
                    borderColor: "#ffd700",
                    backgroundColor: "rgba(255,215,0,0.1)",
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3,
                    pointRadius: days <= 7 ? 4 : 1,
                },
                {
                    label: "最高价",
                    data: highPrices,
                    borderColor: "#2ed573",
                    borderWidth: 1,
                    borderDash: [4, 4],
                    pointRadius: 0,
                    tension: 0.3,
                },
                {
                    label: "最低价",
                    data: lowPrices,
                    borderColor: "#ff4757",
                    borderWidth: 1,
                    borderDash: [4, 4],
                    pointRadius: 0,
                    tension: 0.3,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: "#aaa", font: { size: 11 } } },
                tooltip: {
                    callbacks: {
                        label: ctx => ctx.dataset.label + ": " + ctx.parsed.y + " 元/克"
                    }
                }
            },
            scales: {
                x: { ticks: { color: "#666", maxRotation: 45 }, grid: { color: "#222" } },
                y: {
                    ticks: { color: "#666", callback: v => v + "元" },
                    grid: { color: "#222" },
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
        if (data.length === 0) {
            el.innerHTML = "<h4>今日金价</h4><p style='color:#666'>暂无数据</p>";
            return;
        }
        let html = "<h4>今日金价 (" + data.length + "条)</h4>";
        data.forEach(p => {
            html += `<div class="price-item"><span>${p.time}</span><span>${p.price} 元/克</span></div>`;
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
            el.innerHTML = "<div class='pnl-card'><p style='color:#666'>暂无买入记录</p></div>";
            return;
        }
        let html = "";
        data.purchases.forEach((p, i) => {
            const isProfit = p.pnl >= 0;
            html += `
            <div class="pnl-card ${isProfit ? 'profit' : 'loss'}">
                <div class="pnl-header">
                    <div>
                        <strong>${escapeHtml(p.note) || '记录 #' + (i+1)}</strong>
                        <div class="pnl-detail">
                            <span>买入: ${p.purchase_price}元/克</span>
                            <span>手续费: ${p.fee}%</span>
                        </div>
                    </div>
                    <div class="pnl-value ${isProfit ? 'profit' : 'loss'}">
                        ${isProfit ? '+' : ''}${p.pnl}元/克
                    </div>
                </div>
                <div class="pnl-detail">
                    <span>当前价: ${p.current_price}元/克</span>
                    <span>盈亏比: ${isProfit ? '+' : ''}${p.pnl_percent}%</span>
                    <button onclick="deletePnl(${i})" class="btn btn-sm btn-danger">删除</button>
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
    showToast("已添加买入记录");
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

async function saveSourceSettings() {
    await fetch("/api/config", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            use_custom_api: document.getElementById("useCustomApi").checked,
            custom_api_url: document.getElementById("customApiUrl").value,
        })
    });
    showToast("数据源设置已保存");
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
    if (qqAppId && qqSecret && qqGroup) {
        payload.qq_bot = { app_id: qqAppId, app_secret: qqSecret, group_id: qqGroup };
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
        showToast(data.ok ? "推送成功" : "推送失败: " + data.msg);
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
    setTimeout(() => toast.remove(), 2200);
}
