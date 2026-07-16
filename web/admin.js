const statusNames = { queued: "排队", running: "运行中", awaiting_human: "等待人工", succeeded: "成功", failed: "失败", blocked: "阻断", needs_review: "待复核", cancelled: "已取消" };
const providerNames = { tiktok_api: "TikTok 自建采集", apify: "Apify 采集", yt_dlp: "视频下载", manual_url: "人工链接", doubao: "豆包文本模型", seedance: "Seedance 视频模型", speech_to_text: "语音转写" };
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
const formatBytes = (bytes) => { const units = ["B", "KB", "MB", "GB", "TB"]; let value = Number(bytes || 0); let index = 0; while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; } return `${value.toFixed(index ? 1 : 0)} ${units[index]}`; };

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
  document.querySelector("#stats").innerHTML = [
    ["项目总数", projectTotal, "数据库中的全部生产任务"],
    ["素材数量", payload.material_count, "已进入素材库的参考视频"],
    ["累计成本", `¥${Number(payload.total_cost_cny).toFixed(2)}`, "模型与工具记账"],
    ["存储占用", formatBytes(storageTotal), `运行目录 ${payload.run_count} 个`],
    ["失败任务", failedTasks, failedTasks ? "需要管理员处理" : "当前无失败任务"],
    ["成员账号", payload.users.active, `共 ${payload.users.total} 个账号`],
  ].map(([label, value, note]) => `<article><span>${label}</span><strong>${value}</strong><small>${note}</small></article>`).join("");
  document.querySelector("#projectTotal").textContent = `${projectTotal} 个项目`;
  document.querySelector("#projectStates").innerHTML = Object.entries(payload.projects).map(([status, count]) => `<div><span>${statusNames[status] || status}</span><strong>${count}</strong><i style="--width:${projectTotal ? Math.max(3, Number(count) / projectTotal * 100) : 0}%"></i></div>`).join("") || "暂无项目";
  const providers = [...(payload.runtime.collector_backends || []), ...Object.entries(payload.runtime.providers || {}).filter(([id]) => ["doubao", "seedance", "speech_to_text"].includes(id)).map(([id, value]) => ({ id, ready: value.configured }))];
  document.querySelector("#backendStates").innerHTML = providers.map((provider) => `<div><span>${escapeHtml(providerNames[provider.id] || provider.id)}</span><strong class="${provider.ready ? "ready" : "missing"}">${provider.ready ? "可用" : "未配置"}</strong></div>`).join("");
  document.querySelector("#recentProjects").innerHTML = payload.recent_projects.map((project) => `<tr><td>${escapeHtml(project.id)}</td><td>${escapeHtml(project.product_id || "-")}</td><td><span class="statusTag status-${escapeHtml(project.status)}">${escapeHtml(statusNames[project.status] || project.status)}</span></td><td>${escapeHtml(project.updated_at)}</td><td><a href="/workbench#view=projects">查看</a></td></tr>`).join("") || '<tr><td colspan="5">暂无项目</td></tr>';
  document.querySelector("#recentFailures").innerHTML = payload.recent_failures.map((failure) => `<details><summary>${escapeHtml(failure.project_id)} · ${escapeHtml(failure.stage)} · ${escapeHtml(failure.agent)}</summary><pre>${escapeHtml(failure.error_json || "无错误详情")}</pre></details>`).join("") || '<p class="emptyMessage">当前没有失败节点</p>';
  renderUsers(users.items || []);
  renderRegistrationRequests(registrations.items || []);
}

function renderRegistrationRequests(items) {
  const pending = items.filter((item) => item.status === "pending");
  document.querySelector("#registrationRequestCount").textContent = pending.length ? `${pending.length} 个待审核` : "暂无待审核";
  document.querySelector("#registrationRequestRows").innerHTML = items.map((item) => `<tr>
    <td><strong>${escapeHtml(item.username)}</strong></td>
    <td>${escapeHtml(item.display_name || "-")}</td>
    <td>${escapeHtml(item.requested_at)}</td>
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

function renderUsers(users) {
  document.querySelector("#userRows").innerHTML = users.map((user) => `<tr><td><strong>${escapeHtml(user.username)}</strong></td><td>${escapeHtml(user.display_name || "-")}</td><td>${user.role === "admin" ? "管理员" : "操作员"}</td><td><span class="statusTag status-${user.status === "active" ? "succeeded" : "blocked"}">${user.status === "active" ? "启用" : "停用"}</span></td><td>${escapeHtml(user.last_login_at || "尚未登录")}</td><td><button type="button" class="tableAction" data-user-id="${user.id}" data-next-status="${user.status === "active" ? "disabled" : "active"}">${user.status === "active" ? "停用" : "启用"}</button></td></tr>`).join("") || '<tr><td colspan="6">暂无成员账号</td></tr>';
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
}

document.querySelector("#refreshAdmin").addEventListener("click", () => loadAdmin());
const userDialog = document.querySelector("#userDialog");
document.querySelector("#openUserDialog").addEventListener("click", () => userDialog.showModal());
["#closeUserDialog", "#cancelUserDialog"].forEach((selector) => document.querySelector(selector).addEventListener("click", () => userDialog.close()));
document.querySelector("#userForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const errorHost = document.querySelector("#userFormError");
  errorHost.textContent = "";
  try {
    await api("/api/v2/admin/users", { method: "POST", body: JSON.stringify({ username: document.querySelector("#newUsername").value.trim(), display_name: document.querySelector("#newDisplayName").value.trim(), role: document.querySelector("#newUserRole").value, password: document.querySelector("#newUserPassword").value }) });
    event.currentTarget.reset();
    userDialog.close();
    await loadAdmin();
  } catch (error) {
    errorHost.textContent = error.message;
  }
});
document.querySelector("#logout").addEventListener("click", async () => { await api("/api/v2/auth/logout", { method: "POST" }); window.location.assign("/login"); });
api("/api/v2/auth/session").then((session) => { document.querySelector("#adminUser").textContent = session.username || "本地管理员"; });
loadAdmin().catch((error) => { document.querySelector("#stats").innerHTML = `<p class="loginError">${escapeHtml(error.message)}</p>`; });
