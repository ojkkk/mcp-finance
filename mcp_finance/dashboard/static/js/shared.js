// Shared utilities for all dashboard pages
var D = {
  // Robust data extraction from API responses
  arr: function(data) {
    if (Array.isArray(data)) return data;
    if (data && data.data && Array.isArray(data.data)) return data.data;
    if (data && data["数据"] && Array.isArray(data["数据"])) return data["数据"];
    if (data && data.results && Array.isArray(data.results)) return data.results;
    if (data && data["上榜数"] && Array.isArray(data["数据"])) return data["数据"];
    return [];
  },
  // Get field value with fallbacks: tries Chinese, then English, then snake_case
  get: function(obj, keys) {
    if (!obj) return undefined;
    for (var i = 0; i < keys.length; i++) {
      var v = obj[keys[i]];
      if (v !== undefined && v !== null) return v;
    }
    return undefined;
  },
  name: function(obj) { return D.get(obj, ["名称","name","股票名称","板块名称","概念名称"]) || ""; },
  code: function(obj) { return D.get(obj, ["代码","code","板块代码","股票代码"]) || ""; },
  price: function(obj) { return D.get(obj, ["最新价","price","close","现价","收盘价","最新价格"]); },
  change: function(obj) { return D.get(obj, ["涨跌幅","change","pct_change","涨幅","涨跌比例","change_pct"]); },
  changeAmt: function(obj) { return D.get(obj, ["涨跌额","change_amount"]); },
  open: function(obj) { return D.get(obj, ["今开","open","开盘价"]); },
  high: function(obj) { return D.get(obj, ["最高","high","最高价"]); },
  low: function(obj) { return D.get(obj, ["最低","low","最低价"]); },
  preClose: function(obj) { return D.get(obj, ["昨收","pre_close","preclose","昨日收盘价"]); },
  volume: function(obj) { 
    return D.get(obj, ["成交额","amount","成交额(元)","成交金额","volume","成交量","成交量(手)"]);
  },
  turnover: function(obj) { return D.get(obj, ["换手率","turnover","turnover_rate","换手"]); },
  pe: function(obj) { return D.get(obj, ["市盈率","pe","市盈率(动)","动态市盈率"]); },
  pb: function(obj) { return D.get(obj, ["市净率","pb"]); },
  marketCap: function(obj) { return D.get(obj, ["总市值","market_cap","total_market_cap","流通市值"]); },
  volumeRatio: function(obj) { return D.get(obj, ["量比","volume_ratio","vol_ratio"]); },
  date: function(obj) { return D.get(obj, ["日期","date","时间","trade_date"]) || ""; },
  close: function(obj) { return D.get(obj, ["收盘价","close","收盘"]) || 0; },
  score: function(obj) { return D.get(obj, ["综合评分","score","总分","评级"]); },
  roe: function(obj) { return D.get(obj, ["ROE","roe","净资产收益率"]); },
};

// Number formatting
function fmt(n, d) { d = d || 2; if (n == null || isNaN(n)) return "--"; return Number(n).toFixed(d); }
function fmtVol(n) {
  if (n == null || isNaN(n)) return "--";
  n = Math.abs(n); // normalize
  if (n >= 1e8) return (n / 1e8).toFixed(2) + "亿";
  if (n >= 1e4) return (n / 1e4).toFixed(2) + "万";
  return n.toFixed(0);
}
function pctClass(v) { if (v == null) return ""; return v > 0 ? "up" : v < 0 ? "down" : "text-slate-400"; }
function pctSign(v) { if (v == null) return "--"; return (v > 0 ? "+" : "") + fmt(v) + "%"; }

// Nav highlight
(function() {
  var links = document.querySelectorAll('.nav-link');
  var p = window.location.pathname;
  links.forEach(function(l) {
    var href = l.getAttribute('href');
    var active = (p === '/' && href === '/') || (p !== '/' && href !== '/' && p === href);
    if (active) {
      l.className = 'nav-link px-3 py-1.5 rounded-md text-sm bg-accent/20 text-accent font-medium cursor-pointer transition-colors duration-200';
    } else {
      l.className = 'nav-link px-3 py-1.5 rounded-md text-sm text-slate-400 hover:text-slate-200 hover:bg-bg-hover cursor-pointer transition-colors duration-200';
    }
  });
})();
