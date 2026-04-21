const DASHBOARD_HEADER_MODE_CONFIG = {
    off:         { label: '🛑 off', cls: 'bg-gray-600/30 text-gray-400' },
    signal_only: { label: '📡 signal_only', cls: 'bg-blue-600/20 text-blue-400' },
    paper_trade: { label: '🧪 paper_trade', cls: 'bg-emerald-600/20 text-emerald-400' },
    live_trade:  { label: '🔴 live_trade', cls: 'bg-red-600/20 text-red-300' },
};

function dashboardHeaderAgo(value) {
    if (!value) return '刚刚';
    const timestamp = new Date(value).getTime();
    if (Number.isNaN(timestamp)) return String(value);
    const diffSec = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
    if (diffSec < 5) return '刚刚';
    if (diffSec < 60) return `${diffSec}秒前`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}分钟前`;
    const diffHour = Math.floor(diffMin / 60);
    if (diffHour < 24) return `${diffHour}小时前`;
    const diffDay = Math.floor(diffHour / 24);
    return `${diffDay}天前`;
}

function dashboardHeaderCanonicalMode(modeData) {
    if (modeData?.canonical_mode) return modeData.canonical_mode;
    if (modeData?.mode === 'signals') return 'signal_only';
    if (modeData?.mode === 'trade') return 'paper_trade';
    return 'off';
}

function dashboardHeaderSetRefreshState(label, tone = 'neutral') {
    const el = document.getElementById('refresh-status');
    if (!el) return;
    const tones = {
        active: ['bg-green-500 pulse-dot', 'text-gray-400'],
        ok: ['bg-green-500', 'text-gray-400'],
        warn: ['bg-yellow-500', 'text-yellow-300'],
        error: ['bg-red-500', 'text-red-400'],
        neutral: ['bg-gray-500', 'text-gray-400'],
    };
    const [dotCls, textCls] = tones[tone] || tones.neutral;
    el.innerHTML = `<span class="w-2 h-2 rounded-full ${dotCls}"></span><span class="${textCls}">${label}</span>`;
}

function dashboardHeaderSetLastUpdate(value, fallbackValue = null) {
    const el = document.getElementById('last-update');
    if (!el) return;
    const effective = value || fallbackValue;
    el.textContent = '上次更新: ' + dashboardHeaderAgo(effective);
}

function dashboardHeaderRenderMarketStatus(data) {
    const usEl = document.getElementById('market-status-us');
    const sessionEl = document.getElementById('market-session');
    const timeEl = document.getElementById('et-time');
    if (!usEl && !sessionEl && !timeEl) return;

    let color = 'bg-gray-500';
    let label = '美股';
    let sessionLabel = '--';

    if (data?.session) {
        const sessionMap = {
            regular: ['bg-green-500', '开盘中'],
            premarket: ['bg-yellow-500', '盘前'],
            afterhours: ['bg-orange-500', '盘后'],
            closed: ['bg-gray-500', '已收盘'],
        };
        const entry = sessionMap[data.session] || sessionMap.closed;
        color = entry[0];
        sessionLabel = data.session_label || entry[1];
    } else if (data?.US) {
        const us = data.US;
        if (us.open) { color = 'bg-green-500'; sessionLabel = '开盘中'; }
        else if (us.pre_market) { color = 'bg-yellow-500'; sessionLabel = '盘前'; }
        else if (us.post_market) { color = 'bg-orange-500'; sessionLabel = '盘后'; }
        else { color = 'bg-gray-500'; sessionLabel = '已收盘'; }
    }

    if (usEl) {
        usEl.innerHTML = `<span class="w-2 h-2 rounded-full ${color}"></span><span class="text-gray-400">${label}</span>`;
    }
    if (sessionEl) {
        const sessionColors = {
            开盘中: 'text-green-400',
            盘前: 'text-yellow-400',
            盘后: 'text-blue-400',
            已收盘: 'text-gray-500',
        };
        sessionEl.innerHTML = `<span class="${sessionColors[sessionLabel] || 'text-gray-500'} font-medium">${sessionLabel}</span>`;
    }
    if (timeEl && data?.now_et) {
        timeEl.textContent = '🕐 ' + String(data.now_et).replace(' EDT', ' ET').replace(' EST', ' ET');
    }
}

function dashboardHeaderRenderMode(modeData) {
    const badge = document.getElementById('trading-mode-badge');
    if (!badge) return;
    const canonical = dashboardHeaderCanonicalMode(modeData);
    const config = DASHBOARD_HEADER_MODE_CONFIG[canonical] || DASHBOARD_HEADER_MODE_CONFIG.off;
    badge.textContent = config.label;
    badge.className = 'text-xs px-2 py-0.5 rounded font-medium ' + config.cls;
}

async function dashboardRefreshHeaderStatus(apiBase = '', options = {}) {
    const [modeData, marketData, systemData] = await Promise.all([
        fetch(apiBase + '/api/trading/mode').then(r => r.json()).catch(() => ({})),
        fetch(apiBase + '/api/market-status').then(r => r.json()).catch(() => ({})),
        fetch(apiBase + '/api/system').then(r => r.json()).catch(() => ({})),
    ]);
    dashboardHeaderRenderMode(modeData);
    dashboardHeaderRenderMarketStatus(marketData);
    dashboardHeaderSetLastUpdate(systemData?.last_updated, options.lastUpdatedFallback || null);
    return { modeData, marketData, systemData };
}
