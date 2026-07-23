const statusNames = { idle: "未开始", queued: "排队中", running: "运行中", awaiting_human: "待人工确认", succeeded: "已交付", failed: "失败", blocked: "已阻断", needs_review: "待复核", cancelled: "已取消" };
const providerNames = { browser_search: "TikTok 浏览器搜索", tiktok_api: "TikTokApi 备用采集", apify: "Apify 采集", yt_dlp: "视频下载", manual_url: "人工链接", doubao: "豆包文本模型", seedance: "Seedance 视频模型", speech_to_text: "语音转写" };
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
const formatBytes = (bytes) => { const units = ["B", "KB", "MB", "GB", "TB"]; let value = Number(bytes || 0); let index = 0; while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; } return `${value.toFixed(index ? 1 : 0)} ${units[index]}`; };
const chartColors = ["#2563eb", "#7c3aed", "#22c55e", "#f59e0b", "#ef4444", "#06b6d4", "#64748b", "#94a3b8"];
const refreshIcons = () => window.lucide?.createIcons({ attrs: { "stroke-width": 1.8 } });

function failureMessage(value) {
  if (!value) return "未记录错误详情";
  try {
    const payload = typeof value === "string" ? JSON.parse(value) : value;
    return payload.message || payload.detail || payload.error || JSON.stringify(payload);
  } catch (_) {
    return String(value);
  }
}

function renderDailyTrend(items) {
  const rows = items || [];
  const maxProjects = Math.max(1, ...rows.map((item) => Number(item.projects || 0)));
  const maxCost = Math.max(0.01, ...rows.map((item) => Number(item.cost_cny || 0)));
  document.querySelector("#dailyTrend").innerHTML = rows.map((item) => {
    const label = new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(new Date(`${item.date}T00:00:00`));
    const projectHeight = Number(item.projects || 0) / maxProjects * 100;
    const costHeight = Number(item.cost_cny || 0) / maxCost * 100;
    return `<div class="trendDay" title="${escapeHtml(label)}：${Number(item.projects || 0)} 个项目，¥${Number(item.cost_cny || 0).toFixed(2)}">
      <div class="trendBars"><i style="height:${projectHeight}%"></i><i style="height:${costHeight}%"></i></div>
      <strong>${Number(item.projects || 0)}</strong><span>${escapeHtml(label)}</span>
    </div>`;
  }).join("") || '<p class="emptyMessage">暂无趋势数据</p>';
}

function renderDistribution(hostSelector, entries, options = {}) {
  const host = document.querySelector(hostSelector);
  const rows = entries.filter(([, value]) => Number(value || 0) > 0);
  const total = rows.reduce((sum, [, value]) => sum + Number(value || 0), 0);
  if (!total) { host.innerHTML = '<p class="emptyMessage">暂无数据</p>'; return; }
  let cursor = 0;
  const segments = rows.map(([, value], index) => {
    const start = cursor;
    cursor += Number(value) / total * 100;
    return `${chartColors[index % chartColors.length]} ${start}% ${cursor}%`;
  });
  host.innerHTML = `<div class="donutChart" style="--segments:${segments.join(",")}"><strong>${options.center || total}</strong><span>${escapeHtml(options.centerLabel || "合计")}</span></div>
    <div class="chartLegend">${rows.map(([key, value], index) => `<div><i style="background:${chartColors[index % chartColors.length]}"></i><span>${escapeHtml(options.labels?.[key] || key)}</span><strong>${options.format ? options.format(value) : value}</strong></div>`).join("")}</div>`;
}
function installAdminActionIcons() {
  const rules = [[/通过/, "check"], [/拒绝/, "x"], [/重置/, "key-round"], [/停用/, "user-x"], [/启用/, "user-check"]];
  document.querySelectorAll("button:not([data-icon-ready])").forEach((button) => {
    button.dataset.iconReady = "true";
    if (button.querySelector("svg, [data-lucide]")) return;
    const match = rules.find(([pattern]) => pattern.test(button.textContent.trim()));
    if (!match) return;
    button.classList.add("iconAction");
    button.insertAdjacentHTML("afterbegin", `<i data-lucide="${match[1]}"></i>`);
  });
  refreshIcons();
}

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "请求失败");
  return payload;
}

async function loadAdmin() {
  const [payload, users, registrations] = await Promise.all([
    api("/api/v2/admin/summary"),
    api("/api/v2/admin/users"),
    api("/api/v2/admin/registration-requests"),
  ]);
  const projectTotal = Object.values(payload.projects).reduce((sum, value) => sum + Number(value), 0);
  const failedTasks = Number(payload.tasks.failed || 0);
  const storageTotal = Object.values(payload.storage_bytes).reduce((sum, value) => sum + Number(value), 0);
  const humanGates = Number(payload.projects.awaiting_human || 0);
  document.querySelector("#stats").innerHTML = [
    ["folder-kanban", "项目", projectTotal, `${Number(payload.projects.running || 0)} 个运行中`, "blue", "recentProjectsPanel"],
    ["database", "素材", payload.material_count, "参考视频库", "cyan", "backendPanel"],
    ["circle-dollar-sign", "累计成本", `¥${Number(payload.total_cost_cny).toFixed(2)}`, "模型与工具", "violet", "adminAnalytics"],
    ["hard-drive", "存储", formatBytes(storageTotal), `${payload.run_count} 个运行目录`, "orange", "adminAnalytics"],
    ["triangle-alert", "失败任务", failedTasks, failedTasks ? "需要处理" : "运行正常", failedTasks ? "red" : "green", "failuresPanel"],
    ["shield-check", "人工确认", humanGates, humanGates ? "等待确认" : "暂无待办", humanGates ? "orange" : "green", "projectStatusPanel"],
    ["users", "成员", payload.users.active, `共 ${payload.users.total} 个账号`, "blue", "userPanel"],
  ].map(([icon, label, value, note, tone, target]) => `<button type="button" class="metricCard metric-${tone}" data-admin-target="${target}" aria-label="查看${label}详情"><span class="metricIcon"><i data-lucide="${icon}"></i></span><div><span>${label}</span><strong>${value}</strong><small>${note}</small></div></button>`).join("");
  document.querySelectorAll("[data-admin-target]").forEach((button) => button.addEventListener("click", () => {
    document.getElementById(button.dataset.adminTarget)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }));
  document.querySelector("#projectTotal").textContent = `${projectTotal} 个项目`;
  const stateOrder = ["failed", "blocked", "needs_review", "awaiting_human", "running", "queued", "idle", "succeeded"];
  document.querySelector("#projectStates").innerHTML = stateOrder.filter((status) => Number(payload.projects[status] || 0) > 0).map((status) => `<div><span>${statusNames[status] || status}</span><strong>${payload.projects[status]}</strong><i style="--width:${projectTotal ? Math.max(3, Number(payload.projects[status]) / projectTotal * 100) : 0}%"></i></div>`).join("") || "暂无项目";
  renderDailyTrend(payload.analytics?.daily || []);
  document.querySelector("#statusDistributionTotal").textContent = `${projectTotal} 个项目`;
  renderDistribution("#statusDistribution", Object.entries(payload.analytics?.project_status || payload.projects), { labels: statusNames, center: projectTotal, centerLabel: "项目" });
  document.querySelector("#storageDistributionTotal").textContent = formatBytes(storageTotal);
  renderDistribution("#storageDistribution", Object.entries(payload.storage_bytes || {}), { labels: { database: "数据库", materials: "素材库", runs: "运行产物" }, center: formatBytes(storageTotal), centerLabel: "总占用", format: formatBytes });
  const providers = [
    ...(payload.runtime.collector_backends || []),
    ...Object.entries(payload.runtime.providers || {})
      .filter(([id]) => ["doubao", "seedance", "speech_to_text"].includes(id))
      .map(([id, value]) => ({ id, ...value })),
  ];
  const stateLabels = {
    ready: "探针通过",
    configured_unverified: "待验证",
    not_configured: "未配置",
    optional_disabled: "可选未启用",
    dependency_missing: "依赖缺失",
    degraded: "降级可用",
    error: "异常",
  };
  document.querySelector("#backendStates").innerHTML = providers.map((provider) => {
    const state = provider.state || (provider.ready ? "ready" : provider.configured ? "configured_unverified" : "not_configured");
    const tone = state === "ready" ? "ready" : state === "configured_unverified" || state === "degraded" ? "warning" : state === "optional_disabled" ? "optional" : "missing";
    return `<div class="backendState"><span>${escapeHtml(providerNames[provider.id] || provider.id)}<small>${escapeHtml(provider.detail || "")}</small></span><strong class="${tone}">${escapeHtml(stateLabels[state] || state)}</strong></div>`;
  }).join("");
  const deploymentNames = {
    authentication: "登录鉴权",
    session_secret: "会话密钥",
    cookie_secure: "HTTPS Cookie",
    tiktok_cookies: "TikTok Cookies",
    ffmpeg: "FFmpeg",
    playwright: "Playwright",
    visual_ocr: "画面 OCR",
    speech_to_text: "语音转写",
    persistent_data: "数据持久目录",
    persistent_runs: "运行持久目录",
  };
  document.querySelector("#deploymentStates").innerHTML = Object.entries(payload.runtime.deployment || {}).map(([id, item]) => {
    const tone = item.ready ? (item.warning ? "warning" : "ready") : "missing";
    return `<div class="backendState"><span>${escapeHtml(deploymentNames[id] || id)}<small>${escapeHtml(item.detail || "")}</small></span><strong class="${tone}">${item.ready ? (item.warning ? "需确认" : "就绪") : "待处理"}</strong></div>`;
  }).join("") || '<p class="emptyMessage">未获得部署检测结果</p>';
  const runtimeStamp = document.querySelector("#runtimeBuildVersion");
  if (runtimeStamp) runtimeStamp.textContent = `版本 ${payload.runtime.build_version || "unknown"}`;
  document.querySelector("#recentProjects").innerHTML = payload.recent_projects.map((project) => `<tr><td>${escapeHtml(project.id)}</td><td>${escapeHtml(project.product_id || "-")}</td><td><span class="statusTag status-${escapeHtml(project.status)}">${escapeHtml(statusNames[project.status] || project.status)}</span></td><td>${escapeHtml(formatTime(project.updated_at))}</td><td><a href="/workbench#view=projects">查看</a></td></tr>`).join("") || '<tr><td colspan="5">暂无项目</td></tr>';
  const activeUsers = (users.items || []).filter((user) => user.status === "active");
  document.querySelector("#recentFailures").innerHTML = payload.recent_failures.map((failure) => `<article class="failureItem">
    <div class="failureSummary"><div><strong>${escapeHtml(failure.project_id)} · ${escapeHtml(failure.stage)}</strong><span>${escapeHtml(failure.agent)} · ${escapeHtml(formatTime(failure.updated_at))}</span></div><span class="statusTag status-failed">失败</span></div>
    <p>${escapeHtml(failureMessage(failure.error_json))}</p>
    <details><summary>查看原始日志</summary><pre>${escapeHtml(failure.error_json || "无错误详情")}</pre></details>
    <div class="failureAssignment"><label for="failure-assignee-${Number(failure.task_id)}">负责人</label><select id="failure-assignee-${Number(failure.task_id)}" data-task-assignee="${Number(failure.task_id)}"><option value="">待指派</option>${activeUsers.map((user) => `<option value="${escapeHtml(user.username)}" ${failure.assignee === user.username ? "selected" : ""}>${escapeHtml(user.display_name || user.username)}</option>`).join("")}</select><button type="button" class="tableAction" data-admin-assign-task="${Number(failure.task_id)}">保存指派</button></div>
    <div class="failureActions"><a class="tableAction" href="/workbench#view=tasks">进入任务中心</a><button type="button" class="tableAction" data-admin-retry-task="${Number(failure.task_id)}" data-project-id="${escapeHtml(failure.project_id)}">重试</button><button type="button" class="tableAction danger" data-admin-ignore-task="${Number(failure.task_id)}">忽略</button></div>
  </article>`).join("") || '<p class="emptyMessage">当前没有失败节点</p>';
  bindFailureActions();
  renderUsers(users.items || []);
  renderRegistrationRequests(registrations.items || []);
  installAdminActionIcons();
}

function bindFailureActions() {
  document.querySelectorAll("[data-admin-assign-task]").forEach((button) => button.addEventListener("click", async () => {
    const taskId = Number(button.dataset.adminAssignTask);
    const assignee = document.querySelector(`[data-task-assignee="${taskId}"]`)?.value || "";
    if (!assignee) { window.alert("请选择负责人"); return; }
    button.disabled = true;
    try {
      await api(`/api/v2/admin/tasks/${taskId}/assign`, { method: "POST", body: JSON.stringify({ assignee }) });
      await loadAdmin();
    } catch (error) {
      window.alert(`指派失败：${error.message}`);
      button.disabled = false;
    }
  }));
  document.querySelectorAll("[data-admin-retry-task]").forEach((button) => button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await api("/api/v2/tasks/retry", { method: "POST", body: JSON.stringify({ project_id: button.dataset.projectId, task_id: Number(button.dataset.adminRetryTask) }) });
      await loadAdmin();
    } catch (error) {
      window.alert(`重试失败：${error.message}`);
      button.disabled = false;
    }
  }));
  document.querySelectorAll("[data-admin-ignore-task]").forEach((button) => button.addEventListener("click", async () => {
    const reason = window.prompt("请填写忽略原因（将保留审计记录）：", "已人工确认，无需继续处理");
    if (reason === null) return;
    button.disabled = true;
    try {
      await api(`/api/v2/admin/tasks/${button.dataset.adminIgnoreTask}/ignore`, { method: "POST", body: JSON.stringify({ reason }) });
      await loadAdmin();
    } catch (error) {
      window.alert(`忽略失败：${error.message}`);
      button.disabled = false;
    }
  }));
}

function renderRegistrationRequests(items) {
  const pending = items.filter((item) => item.status === "pending");
  document.querySelector("#registrationRequestCount").textContent = pending.length ? `${pending.length} 个待审核` : "暂无待审核";
  document.querySelector("#registrationRequestRows").innerHTML = items.map((item) => `<tr>
    <td><strong>${escapeHtml(item.username)}</strong></td>
    <td>${escapeHtml(item.display_name || "-")}</td>
    <td>${escapeHtml(formatTime(item.requested_at))}</td>
    <td><span class="statusTag status-${item.status === "approved" ? "succeeded" : item.status === "rejected" ? "blocked" : "running"}">${item.status === "pending" ? "待审核" : item.status === "approved" ? "已开通" : "已拒绝"}</span></td>
    <td>${item.status === "pending" ? `<button type="button" class="tableAction" data-registration-approve="${item.id}">通过</button> <button type="button" class="tableAction" data-registration-reject="${item.id}">拒绝</button>` : escapeHtml(item.reviewed_by || "-")}</td>
  </tr>`).join("") || '<tr><td colspan="5">暂无账号申请</td></tr>';
  document.querySelectorAll("[data-registration-approve], [data-registration-reject]").forEach((button) => {
    button.addEventListener("click", async () => {
      const approved = Boolean(button.dataset.registrationApprove);
      const requestId = button.dataset.registrationApprove || button.dataset.registrationReject;
      const note = window.prompt(approved ? "审核备注（可选）" : "拒绝原因（可选）") || "";
      button.disabled = true;
      try {
        await api(`/api/v2/admin/registration-requests/${requestId}/${approved ? "approve" : "reject"}`, {
          method: "POST",
          body: JSON.stringify({ note }),
        });
        await loadAdmin();
      } catch (error) {
        window.alert(error.message);
      } finally {
        button.disabled = false;
      }
    });
  });
}

function formatTime(value) {
  if (!value) return "尚未登录";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function renderUsers(users) {
  document.querySelector("#userRows").innerHTML = users.map((user) => `<tr><td><strong>${escapeHtml(user.username)}</strong></td><td>${escapeHtml(user.display_name || "-")}</td><td>${user.role === "admin" ? "管理员" : "操作员"}</td><td><span class="statusTag status-${user.status === "active" ? "succeeded" : "blocked"}">${user.status === "active" ? "启用" : "停用"}</span></td><td>${escapeHtml(formatTime(user.last_login_at))}</td><td><button type="button" class="tableAction" data-user-id="${user.id}" data-next-status="${user.status === "active" ? "disabled" : "active"}">${user.status === "active" ? "停用" : "启用"}</button><button type="button" class="tableAction" data-reset-user="${user.id}">重置密码</button></td></tr>`).join("") || '<tr><td colspan="6">暂无成员账号</td></tr>';
  document.querySelectorAll("[data-user-id]").forEach((button) => button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await api(`/api/v2/admin/users/${button.dataset.userId}`, { method: "PATCH", body: JSON.stringify({ status: button.dataset.nextStatus }) });
      await loadAdmin();
    } catch (error) {
      window.alert(error.message);
    } finally {
      button.disabled = false;
    }
  }));
  document.querySelectorAll("[data-reset-user]").forEach((button) => button.addEventListener("click", async () => {
    const password = window.prompt("输入新的登录密码（至少 8 位）：");
    if (!password) return;
    if (password.length < 8) { window.alert("密码至少需要 8 位"); return; }
    try {
      await api(`/api/v2/admin/users/${button.dataset.resetUser}`, { method: "PATCH", body: JSON.stringify({ password }) });
      window.alert("密码已重置");
    } catch (error) { window.alert(error.message); }
  }));
}

document.querySelector("#refreshAdmin").addEventListener("click", () => loadAdmin());
document.querySelector("#probeTikTok")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = "检测中…";
  try {
    const result = await api("/api/v2/admin/runtime/probe", { method: "POST", body: JSON.stringify({ provider: "browser_search" }) });
    window.alert(result.ok ? "TikTok 浏览器搜索探针通过" : `采集探针失败：${result.probe?.detail || "未知错误"}`);
    await loadAdmin();
  } catch (error) {
    window.alert(`采集探针失败：${error.message}`);
  } finally {
    button.disabled = false;
    button.textContent = "检测采集";
  }
});
const cookiesFile = document.querySelector("#cookiesFile");
document.querySelector("#uploadCookies")?.addEventListener("click", () => cookiesFile?.click());
cookiesFile?.addEventListener("change", async () => {
  const file = cookiesFile.files?.[0];
  if (!file) return;
  const button = document.querySelector("#uploadCookies");
  button.disabled = true;
  button.innerHTML = '<i data-lucide="loader-circle"></i>正在更新…';
  window.lucide?.createIcons();
  try {
    const cookiesText = await file.text();
    await api("/api/v2/admin/runtime/cookies", {
      method: "POST",
      body: JSON.stringify({ cookies_text: cookiesText }),
    });
    window.alert("TikTok Cookies 已安全替换，请继续点击“检测采集”验证会话。");
    await loadAdmin();
  } catch (error) {
    window.alert(`Cookies 更新失败：${error.message}`);
  } finally {
    cookiesFile.value = "";
    button.disabled = false;
    button.innerHTML = '<i data-lucide="upload"></i>更新 Cookies';
    window.lucide?.createIcons();
  }
});
const userDialog = document.querySelector("#userDialog");
document.querySelector("#openUserDialog").addEventListener("click", () => userDialog.showModal());
["#closeUserDialog", "#cancelUserDialog"].forEach((selector) => document.querySelector(selector).addEventListener("click", () => userDialog.close()));
document.querySelector("#userForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const errorHost = document.querySelector("#userFormError");
  errorHost.textContent = "";
  try {
    await api("/api/v2/admin/users", { method: "POST", body: JSON.stringify({ username: document.querySelector("#newUsername").value.trim(), display_name: document.querySelector("#newDisplayName").value.trim(), role: document.querySelector("#newUserRole").value, password: document.querySelector("#newUserPassword").value }) });
    form.reset();
    userDialog.close();
    await loadAdmin();
  } catch (error) {
    errorHost.textContent = error.message;
  }
});
document.querySelector("#logout").addEventListener("click", async () => { await api("/api/v2/auth/logout", { method: "POST" }); window.location.assign("/login"); });
api("/api/v2/auth/session").then((session) => { document.querySelector("#adminUser").textContent = session.username || "本地管理员"; });
installAdminActionIcons();
loadAdmin().catch((error) => { document.querySelector("#stats").innerHTML = `<p class="loginError">${escapeHtml(error.message)}</p>`; });
