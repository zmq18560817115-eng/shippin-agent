const state = {
  projects: [],
  materials: [],
  productLibrary: [],
  productLibraryGeneratedAt: null,
  productLibrarySources: [],
  selectedId: null,
  selected: null,
  scriptCopy: null,
  scriptBreakdown: null,
  reviewReport: null,
  shotPlan: null,
  assetManifest: null,
  takeManifest: null,
  renderReport: null,
  runReport: null,
  refreshing: false,
  operation: null,
  currentView: "projects",
  showAllProjects: false,
};

const views = {
  projects: { step: "01 / 06", title: "项目", description: "创建任务，或打开一个在制项目继续工作。" },
  assets: { step: "02 / 06", title: "素材采集", description: "管理产品事实素材，采集并分析参考视频。" },
  script: { step: "03 / 06", title: "脚本", description: "审阅内容策略、脚本拆解与文案，确认后进入分镜。" },
  storyboard: { step: "04 / 06", title: "分镜", description: "调整镜头计划，确认产品关键帧与视觉连续性。" },
  production: { step: "05 / 06", title: "制作", description: "逐镜生成、选择最佳 Take，并合成为 30 秒成片。" },
  delivery: { step: "06 / 06", title: "交付", description: "检查质检结果，下载交付包并记录反馈。" },
};

const $ = (selector) => document.querySelector(selector);
const statusGlyph = {
  idle: "○",
  queued: "●",
  running: "◐",
  awaiting_human: "⏸",
  succeeded: "✓",
  failed: "×",
  blocked: "!",
  needs_review: "?",
};

const stageLabels = {
  analysis: "素材分析", research: "研究洞察", strategy: "内容策略", script: "脚本文案",
  script_breakdown: "脚本拆解", script_review: "脚本审核", script_gate: "脚本确认",
  storyboard: "分镜生成", asset: "产品素材", hero_gate: "分镜确认", production: "视频生成",
  compose: "视频合成", final_qa: "成片质检", archive: "交付归档", succeeded: "已交付",
  failed: "运行失败", awaiting_human: "等待人工确认", running: "运行中", queued: "排队中",
  idle: "未开始", blocked: "已阻塞", needs_review: "需要复核",
};

const agentLabels = {
  collector: "素材采集", analysis: "研究分析", script: "脚本文案", storyboard: "分镜策划",
  asset: "产品素材", media: "视频制作", review: "质量审核",
};

const motionLabels = {
  dolly_in: "推进", dolly_out: "拉远", pan_left: "左移", pan_right: "右移",
  static: "固定", arc: "环绕", crash_zoom: "快速推进",
};

function stageLabel(value) {
  return stageLabels[String(value || "")] || String(value || "未开始");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
    } catch {
      detail = await response.text();
    }
    throw new Error(detail);
  }
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response;
}

function toast(message, kind = "ok") {
  const node = $("#toast");
  node.textContent = message;
  node.dataset.kind = kind;
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => {
    node.textContent = "";
    delete node.dataset.kind;
  }, 2800);
}

function beginOperation(label, estimateSeconds) {
  endOperation();
  const startedAt = Date.now();
  const host = $("#operationStatus");
  const render = () => {
    const elapsed = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
    const remaining = Math.max(0, estimateSeconds - elapsed);
    host.hidden = false;
    host.textContent = `${label}：已运行 ${elapsed}s，预计剩余约 ${remaining}s`;
  };
  render();
  state.operation = { timer: window.setInterval(render, 1000), host };
}

function endOperation() {
  if (!state.operation) return;
  window.clearInterval(state.operation.timer);
  state.operation.host.hidden = true;
  state.operation = null;
}

async function boot() {
  bindEvents();
  const initialView = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("view");
  showView(views[initialView] ? initialView : "projects", { updateUrl: false });
  await checkHealth();
  await loadProductLibrary();
  await loadProducts();
  await refreshProjects();
  window.setInterval(() => refreshProjects({ silent: true }), 3000);
}

async function runFlowCapability(action, button, resultSelector) {
  if (!state.selectedId) {
    toast("请先在项目列表打开一个项目", "error");
    return;
  }
  button.disabled = true;
  beginOperation("正在运行智能体", 35);
  const resultHost = $(resultSelector);
  resultHost.className = "nodeResult";
  resultHost.textContent = `${action} 运行中`;
  try {
    const payload = await api("/api/v2/agents/run", {
      method: "POST",
      body: JSON.stringify({
        project_id: state.selectedId,
        action,
        source_text: action === "research" ? $("#researchSourceText").value.trim() || null : null,
        mock: $("#runtimeMode").value !== "real",
      }),
    });
    resultHost.className = "nodeResult complete";
    resultHost.innerHTML = `<strong>${escapeHtml(payload.artifact_name)}</strong><pre>${escapeHtml(JSON.stringify(payload.artifact, null, 2))}</pre>`;
    toast(`${payload.artifact_name} 已生成`);
    await refreshProjects({ silent: true });
  } catch (error) {
    resultHost.className = "nodeResult error";
    resultHost.textContent = error.message;
    toast(error.message, "error");
  } finally {
    button.disabled = false;
    endOperation();
  }
}

function bindEvents() {
  $("#startForm").addEventListener("submit", startProject);
  $("#collectForm").addEventListener("submit", collectLinks);
  $("#crawlForm").addEventListener("submit", crawlTikTok);
  $("#runtimeMode").addEventListener("change", updateRuntimeModeHint);
  $("#crawlTargetType").addEventListener("change", updateCrawlTargetUI);
  $("#refreshButton").addEventListener("click", () => refreshProjects());
  $("#toggleProjects").addEventListener("click", () => {
    state.showAllProjects = !state.showAllProjects;
    renderProjectRows();
  });
  $("#refreshProductLibrary").addEventListener("click", refreshProductLibrary);
  $("#runResearch").addEventListener("click", (event) => runFlowCapability("research", event.currentTarget, "#researchResult"));
  $("#runStrategy").addEventListener("click", (event) => runFlowCapability("strategy", event.currentTarget, "#strategyResult"));
  $("#runScriptBreakdown").addEventListener("click", (event) => runFlowCapability("script_breakdown", event.currentTarget, "#scriptBreakdownResult"));
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.view));
  });
  $("#continueProject").addEventListener("click", continueCurrentProject);
  window.addEventListener("hashchange", () => {
    const view = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("view");
    if (views[view]) showView(view, { updateUrl: false });
  });
  updateCrawlTargetUI();
  updateRuntimeModeHint();
}

function updateRuntimeModeHint() {
  const real = $("#runtimeMode").value === "real";
  $("#runtimeModeHint").textContent = real
    ? "真实调用采集、分析和视频模型，耗时与费用以实际任务为准。"
    : "仅用于界面与流程演练：不抓取真实 TikTok 视频，也不会产生可交付成片。";
}

function updateCrawlTargetUI() {
  const type = $("#crawlTargetType").value;
  const input = $("#crawlTarget");
  const presets = {
    keyword: ["关键词", "例如 heated cup"],
    account: ["TikTok 账号主页", "例如 https://www.tiktok.com/@brand"],
    hashtag: ["话题标签", "例如 heatedcup 或 #heatedcup"],
    trending: ["热门视频无需输入目标", "系统将读取当前地区热门公开视频"],
  };
  const [label, placeholder] = presets[type] || presets.keyword;
  $("#crawlTargetText").textContent = label;
  input.placeholder = placeholder;
  input.disabled = type === "trending";
  input.required = type !== "trending";
  if (type === "trending") input.value = "";
}

function showView(view, { updateUrl = true } = {}) {
  const next = views[view] ? view : "projects";
  state.currentView = next;
  document.querySelectorAll("[data-view-section]").forEach((section) => {
    section.hidden = section.dataset.viewSection !== next;
  });
  document.querySelectorAll(".workflowNav [data-view]").forEach((button) => {
    const active = button.dataset.view === next;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  });
  const meta = views[next];
  $("#viewStep").textContent = meta.step;
  $("#viewTitle").textContent = meta.title;
  $("#viewDescription").textContent = meta.description;
  if (updateUrl) history.replaceState(null, "", `#view=${next}`);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function viewForStage(stage) {
  if (["analysis", "research", "strategy", "script", "script_breakdown", "script_review", "script_gate"].includes(stage)) return "script";
  if (["storyboard", "asset", "hero_gate"].includes(stage)) return "storyboard";
  if (["production", "compose", "final_qa"].includes(stage)) return "production";
  if (["archive", "succeeded"].includes(stage)) return "delivery";
  return "projects";
}

function continueCurrentProject() {
  if (!state.selected) return;
  showView(viewForStage(state.selected.current_stage || state.selected.status));
}

async function checkHealth() {
  try {
    const health = await api("/healthz");
    $("#health").textContent = health.status === "ok" ? "在线" : "异常";
    $("#health").dataset.status = health.status;
  } catch (error) {
    $("#health").textContent = "离线";
    $("#health").dataset.status = "offline";
  }
}

async function loadProducts() {
  const select = $("#productSelect");
  try {
    const payload = await api("/api/v2/products");
    select.innerHTML = "";
    payload.items.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = item.ready ? item.label : `${item.label}（素材未齐 ${item.issue_count || 0}）`;
      option.disabled = !item.ready;
      select.appendChild(option);
    });
  } catch (error) {
    select.innerHTML = '<option value="便携恒温杯">便携恒温杯</option>';
  }
}

async function loadProductLibrary({ refresh = false } = {}) {
  const panel = $("#productLibraryPanel");
  try {
    const payload = await api(`/api/v2/product-library${refresh ? "?refresh=true" : ""}`);
    state.productLibrary = payload.products || [];
    state.productLibraryGeneratedAt = payload.generated_at || null;
    state.productLibrarySources = payload.source_roots || [];
  } catch (error) {
    state.productLibrary = [];
    state.productLibraryGeneratedAt = null;
    state.productLibrarySources = [];
    panel.className = "emptyState";
    panel.textContent = error.message;
    return;
  }
  renderProductLibrary();
}

async function refreshProductLibrary() {
  const button = $("#refreshProductLibrary");
  button.disabled = true;
  $("#productLibraryState").textContent = "刷新中";
  try {
    const payload = await api("/api/v2/product-library/refresh", {
      method: "POST",
      body: JSON.stringify({}),
    });
    state.productLibrary = payload.products || [];
    state.productLibraryGeneratedAt = payload.generated_at || null;
    state.productLibrarySources = payload.source_roots || [];
    renderProductLibrary();
    await loadProducts();
    toast("产品素材库已刷新");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
    renderProductLibrary();
  }
}

function renderProductLibrary() {
  const host = $("#productLibraryPanel");
  const readyCount = state.productLibrary.filter((product) => product.ready).length;
  const sourceCount = state.productLibrarySources.filter((source) => source.exists).length;
  $("#productLibraryState").textContent = state.productLibrary.length
    ? `${readyCount}/${state.productLibrary.length} 可生产 · ${sourceCount} 个源在线`
    : "";
  if (!state.productLibrary.length) {
    host.className = "emptyState";
    host.textContent = "暂无产品素材库索引";
    return;
  }
  host.className = "productLibrary";
  host.innerHTML = state.productLibrary.map(renderProductItem).join("");
}

function renderProductItem(product) {
  const issues = product.issues || [];
  const counts = formatCounts(product.counts || {});
  const blockers = issues.filter((issue) => issue.severity === "BLOCKED").length;
  const status = product.ready ? "可生产" : `${blockers || issues.length} 项阻塞`;
  const issueText = issues.length
    ? issues.map((issue) => `${issue.severity}: ${issue.message}`).join(" · ")
    : "素材规则通过";
  const sourceText = product.seedance_source
    ? compactPath(product.seedance_source, 4)
    : "未绑定白底主图";
  return `
    <article class="productItem" data-ready="${product.ready ? "true" : "false"}">
      <div class="productMain">
        <strong>${escapeHtml(product.label || product.id)}</strong>
        <span>${escapeHtml(status)} · ${product.ds223_refreshed ? "DS223 已刷新" : "DS223 待刷新"}</span>
      </div>
      <div class="productMeta">
        <span>${escapeHtml(counts || "暂无图片分类")}</span>
        <span title="${escapeAttr(product.seedance_source || "")}">${escapeHtml(sourceText)}</span>
      </div>
      <p>${escapeHtml(issueText)}</p>
    </article>
  `;
}

function formatCounts(counts) {
  const labels = {
    product_identity: "身份图",
    usage_step: "使用图",
    scene: "场景图",
    detail_proof: "细节图",
    reference_only: "参考图",
    prohibited: "禁用图",
  };
  return Object.entries(counts)
    .map(([key, value]) => `${labels[key] || key} ${value}`)
    .join(" · ");
}

function compactPath(pathText, keep = 3) {
  const normal = String(pathText || "").replace(/\\/g, "/");
  const parts = normal.split("/").filter(Boolean);
  return parts.slice(-keep).join("/");
}

async function loadMaterials() {
  try {
    const payload = await api("/api/v2/collect/library?limit=50");
    state.materials = payload.items || [];
  } catch {
    state.materials = [];
  }
  renderMaterialLibrary();
}

async function startProject(event) {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  beginOperation("正在创建并分析项目", 50);
  $("#startState").textContent = "提交中";
  try {
    const body = {
      product_id: $("#productSelect").value,
      link_id: $("#linkInput").value.trim() || null,
      mock: $("#runtimeMode").value !== "real",
    };
    const payload = await api("/api/v2/pipeline/run", {
      method: "POST",
      body: JSON.stringify(body),
    });
    state.selectedId = payload.project_id;
    toast(`项目 ${payload.project_id} 已到 ${payload.engine.stage}`);
    await refreshProjects();
    continueCurrentProject();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
    $("#startState").textContent = "";
    endOperation();
  }
}

async function collectLinks(event) {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  const action = button.value || "import";
  beginOperation(action === "analyze" ? "正在采集并分析参考视频" : "正在导入参考素材", action === "analyze" ? 75 : 20);
  $("#collectState").textContent = action === "analyze" ? "采集并分析中" : "导入中";
  try {
    if (action === "analyze") {
      const urls = $("#collectLinksInput").value.match(/https?:\/\/[^\s,;]+/g) || [];
      if (urls.length !== 1) throw new Error("采集并分析每次需要且仅支持一条 TikTok 链接");
      const result = await api("/api/v2/collect/tiktok/run", {
        method: "POST",
        body: JSON.stringify({
          url: urls[0],
          product_id: $("#productSelect").value,
          transcript_text: $("#researchSourceText").value.trim() || null,
          mock: $("#runtimeMode").value !== "real",
        }),
      });
      state.selectedId = result.project_id;
      $("#collectLinksInput").value = "";
      const warning = (result.warnings || [])[0];
      toast(warning || `采集完成，项目已运行到 ${result.engine.stage}`, warning ? "warning" : "success");
      await refreshProjects();
      continueCurrentProject();
      return;
    }
    const official = $("#collectMode").value === "official";
    const payload = await api(official ? "/api/v2/collect/tiktok" : "/api/v2/collect/manual", {
      method: "POST",
      body: JSON.stringify({
        links_text: $("#collectLinksInput").value,
        product_id: $("#productSelect").value,
        source_keyword: $("#sourceKeywordInput").value.trim() || (official ? "tiktok_oembed" : "manual_tiktok"),
      }),
    });
    $("#collectLinksInput").value = "";
    toast(`已导入 ${payload.imported_count} 条素材`);
    await loadMaterials();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
    $("#collectState").textContent = "";
    endOperation();
  }
}

async function crawlTikTok(event) {
  event.preventDefault();
  const button = event.submitter;
  const targetType = $("#crawlTargetType").value;
  const target = $("#crawlTarget").value.trim();
  if (targetType !== "trending" && !target) {
    const names = { keyword: "关键词", account: "TikTok 账号主页", hashtag: "话题标签" };
    toast(`请输入${names[targetType] || "采集目标"}`, "error");
    $("#crawlTarget").focus();
    return;
  }
  button.disabled = true;
  beginOperation("正在发现、下载并分析 TikTok 素材", 150);
  $("#crawlState").textContent = "发现与下载中";
  try {
    const payload = await api("/api/v2/collect/tiktok/crawl", {
      method: "POST",
      body: JSON.stringify({
        target_type: targetType,
        provider: $("#crawlProvider").value,
        target,
        limit: Number($("#crawlLimit").value || 3),
        product_id: $("#productSelect").value,
        mock: $("#runtimeMode").value !== "real",
      }),
    });
    if (payload.results?.length) state.selectedId = payload.results[0].project_id;
    toast(`发现 ${payload.discovered_count} 条，完成 ${payload.completed_count} 条，失败 ${payload.failed_count} 条`);
    await refreshProjects();
    if (payload.results?.length) continueCurrentProject();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
    $("#crawlState").textContent = "";
    endOperation();
  }
}

async function startFromMaterial(materialId) {
  try {
    const payload = await api("/api/v2/pipeline/run", {
      method: "POST",
      body: JSON.stringify({
        product_id: $("#productSelect").value,
        source_material_id: materialId,
        mock: $("#runtimeMode").value !== "real",
      }),
    });
    state.selectedId = payload.project_id;
    toast(`素材 ${materialId} 已发起：${payload.engine.stage}`);
    await refreshProjects();
    continueCurrentProject();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function refreshProjects({ silent = false } = {}) {
  if (state.refreshing) return;
  state.refreshing = true;
  try {
    const payload = await api("/api/v2/pipeline?limit=50");
    state.projects = payload.items;
    if (!state.selectedId && state.projects.length) {
      state.selectedId = state.projects[0].project_id;
    }
    renderProjectRows();
    const activeEditor = document.activeElement?.matches("input, textarea, select");
    if (state.selectedId && !(silent && activeEditor)) {
      await loadSelectedProject(state.selectedId);
    } else if (!state.selectedId) {
      renderPanels();
    }
    if (!(silent && activeEditor)) await loadMaterials();
  } catch (error) {
    if (!silent) toast(error.message, "error");
  } finally {
    state.refreshing = false;
  }
}

function renderMaterialLibrary() {
  const host = $("#materialLibrary");
  if (!state.materials.length) {
    host.className = "emptyState";
    host.textContent = "暂无人工导入素材";
    return;
  }
  host.className = "materialList";
  host.innerHTML = state.materials.map(renderMaterialItem).join("");
  host.querySelectorAll("[data-start-material]").forEach((button) => {
    button.addEventListener("click", () => startFromMaterial(button.dataset.startMaterial));
  });
}

function renderMaterialItem(item) {
  const meta = item.material_meta || {};
  const title = meta.video_title || meta.caption || meta.source_url || "未命名 TikTok 素材";
  const caption = meta.caption || "未取得视频简介";
  const analysis = materialAnalysisSummary(meta);
  const sourceUrl = meta.source_url || meta.video_url || "";
  const cover = meta.cover_url
    ? `<img class="materialCover" src="${escapeAttr(meta.cover_url)}" alt="${escapeAttr(title)} 封面" loading="lazy" />`
    : `<div class="materialCover placeholder">无封面</div>`;
  return `
    <article class="materialItem">
      ${cover}
      <div class="materialBody">
        <strong>${escapeHtml(title)}</strong>
        <span>${escapeHtml(meta.author_name || "未知创作者")} · ${escapeHtml(meta.source_keyword || "manual_tiktok")} · ${escapeHtml(meta.processing_status || item.status || "待处理")}</span>
        <p>${escapeHtml(caption)}</p>
        <p class="materialAnalysis">${escapeHtml(analysis)}</p>
        ${sourceUrl ? `<a href="${escapeAttr(sourceUrl)}" target="_blank" rel="noopener">打开 TikTok 来源</a>` : ""}
      </div>
      <button type="button" data-start-material="${escapeAttr(item.material_id)}">发起项目</button>
    </article>
  `;
}

function materialAnalysisSummary(meta) {
  try {
    const analysis = JSON.parse(meta.ai_analysis_json || "{}").analysis || {};
    const structure = Array.isArray(analysis.structure) ? analysis.structure.join(" - ") : "";
    return analysis.hook_3s
      ? `已分析：3 秒钩子“${analysis.hook_3s}”；结构：${structure || "待补充"}`
      : "已采集，等待分析拆解";
  } catch {
    return "已采集，等待分析拆解";
  }
}

async function loadSelectedProject(projectId) {
  state.selected = await api(`/api/v2/pipeline/${encodeURIComponent(projectId)}`);
  state.scriptCopy = null;
  state.scriptBreakdown = null;
  state.reviewReport = null;
  state.shotPlan = null;
  state.assetManifest = null;
  state.takeManifest = null;
  state.renderReport = null;
  state.runReport = null;

  state.scriptCopy = await safeArtifact(projectId, "script_copy");
  state.scriptBreakdown = await safeArtifact(projectId, "script_breakdown");
  state.reviewReport = await safeArtifact(projectId, "review_report");
  state.shotPlan = await safeArtifact(projectId, "shot_plan");
  state.assetManifest = await safeArtifact(projectId, "asset_manifest");
  state.takeManifest = await safeArtifact(projectId, "take_manifest");
  if (state.selected.status === "succeeded") {
    state.renderReport = await safeArtifact(projectId, "render_report");
    state.runReport = await safeRunReport(projectId);
  }
  renderPanels();
}

async function safeArtifact(projectId, artifactName) {
  try {
    return await api(`/api/v2/artifacts/${encodeURIComponent(projectId)}/${artifactName}`);
  } catch {
    return null;
  }
}

async function safeRunReport(projectId) {
  try {
    return await api(`/api/v2/reports/${encodeURIComponent(projectId)}`);
  } catch {
    return null;
  }
}

function renderProjectRows() {
  const tbody = $("#projectRows");
  tbody.innerHTML = "";
  const visibleProjects = state.showAllProjects ? state.projects : state.projects.slice(0, 10);
  $("#projectCount").textContent = `${Math.min(visibleProjects.length, state.projects.length)} / ${state.projects.length}`;
  $("#toggleProjects").textContent = state.showAllProjects ? "收起列表" : "显示全部";
  $("#toggleProjects").hidden = state.projects.length <= 10;
  if (!state.projects.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="muted">暂无项目</td></tr>';
    return;
  }
  visibleProjects.forEach((project) => {
    const row = document.createElement("tr");
    row.className = project.project_id === state.selectedId ? "selected" : "";
    row.dataset.projectRow = project.project_id;
    row.title = "右键可删除已停止或已完成的项目";
    row.innerHTML = `
      <td>
        <button type="button" class="linkButton" data-open="${escapeAttr(project.project_id)}">
          ${escapeHtml(project.project_id)}
        </button>
        <div class="subline">${escapeHtml(project.product_id || "")}</div>
      </td>
      <td>${renderNodes(project.nodes)}</td>
      <td>
        <span class="stageTag ${statusClass(project.status)}">${escapeHtml(stageLabel(project.current_stage || project.status))}</span>
      </td>
      <td>¥${Number(project.cost.total_cost_cny || 0).toFixed(2)}</td>
      <td>${renderProjectActions(project)}</td>
    `;
    tbody.appendChild(row);

    const errors = project.tasks.filter((task) => task.error_json && isUnresolvedTask(project, task));
    if (errors.length) {
      const errorRow = document.createElement("tr");
      errorRow.className = "errorRow";
      errorRow.innerHTML = `<td colspan="5">${renderErrors(project.project_id, errors)}</td>`;
      tbody.appendChild(errorRow);
    }
  });

  tbody.querySelectorAll("[data-open]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedId = button.dataset.open;
      await refreshProjects();
      continueCurrentProject();
    });
  });
  tbody.querySelectorAll("[data-retry-shot]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedId = button.dataset.project;
      retryShot(Number(button.dataset.retryShot));
    });
  });
  tbody.querySelectorAll("[data-retry-task]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedId = button.dataset.project;
      retryTask(Number(button.dataset.retryTask));
    });
  });
  tbody.querySelectorAll("[data-delete-project]").forEach((button) => {
    button.addEventListener("click", () => deleteProject(button.dataset.deleteProject));
  });
  tbody.querySelectorAll("[data-project-row]").forEach((row) => {
    row.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      deleteProject(row.dataset.projectRow);
    });
  });
}

function renderNodes(nodes) {
  return `<div class="nodes">${nodes
    .map((node) => `<span class="node ${statusClass(node.status)}" title="${escapeAttr(agentLabels[node.agent] || node.agent)}：${escapeAttr(stageLabel(node.status))}">${statusGlyph[node.status] || "·"} ${escapeHtml(agentLabels[node.agent] || node.agent)}</span>`)
    .join("")}</div>`;
}

function renderProjectActions(project) {
  const failedShot = project.tasks.find(
    (task) => task.stage === "production" && task.status === "failed" && isUnresolvedTask(project, task),
  );
  if (failedShot) {
    const shot = failedShot.payload_json.shot_index;
    return `<button type="button" data-project="${escapeAttr(project.project_id)}" data-retry-shot="${shot}">重试镜头 ${shot}</button>`;
  }
  return `<div class="projectActions"><button type="button" data-open="${escapeAttr(project.project_id)}">打开</button><button type="button" class="dangerButton" data-delete-project="${escapeAttr(project.project_id)}">删除</button></div>`;
}

async function deleteProject(projectId) {
  const project = state.projects.find((item) => item.project_id === projectId);
  if (!project || !window.confirm(`删除项目“${projectId}”？\n这会删除该项目的运行记录和成片，不会删除共享素材库。`)) return;
  try {
    await api(`/api/v2/pipeline/${encodeURIComponent(projectId)}`, { method: "DELETE" });
    if (state.selectedId === projectId) state.selectedId = null;
    toast("项目已删除，共享素材库未受影响");
    await refreshProjects();
  } catch (error) {
    toast(error.message, "error");
  }
}

function isUnresolvedTask(project, task) {
  const shot = task.payload_json?.shot_index ?? null;
  const revision = task.payload_json?.revision ?? null;
  const laterEquivalent = project.tasks.some((candidate) =>
    candidate.id > task.id
    && candidate.stage === task.stage
    && (candidate.payload_json?.shot_index ?? null) === shot
    && (candidate.payload_json?.revision ?? null) === revision
    && candidate.status === "succeeded"
  );
  return !laterEquivalent;
}

function renderErrors(projectId, errors) {
  return errors
    .map((task) => {
      const shot = task.shot_index || task.payload_json?.shot_index || "";
      const retry = task.stage === "production" && shot
        ? `<button type="button" data-project="${escapeAttr(projectId)}" data-retry-shot="${shot}">重试镜头 ${shot}</button>`
        : `<button type="button" data-project="${escapeAttr(projectId)}" data-retry-task="${task.id}">重试此节点</button>`;
      return `
        <details>
          <summary>${escapeHtml(task.stage)} ${shot ? `shot ${shot}` : ""} failed</summary>
          <pre>${escapeHtml(JSON.stringify(task.error_json, null, 2))}</pre>
          ${retry}
        </details>
      `;
    })
    .join("");
}

function renderPanels() {
  const label = state.selected
    ? `${state.selected.project_id} · ${state.selected.current_stage || state.selected.status}`
    : "未选择项目";
  $("#activeProject").textContent = label;
  const continueButton = $("#continueProject");
  continueButton.disabled = !state.selected;
  $("#currentStage").textContent = state.selected
    ? `当前节点：${state.selected.current_stage || state.selected.status}`
    : "暂无在制项目";
  renderScriptGate();
  renderHeroGate();
  renderStoryboardNode();
  renderProductionNode();
  renderComposeNode();
  renderDelivery();
}

function renderScriptGate() {
  const host = $("#scriptEditor");
  $("#scriptGateState").textContent = state.selected?.current_gate === "script_gate" ? "待确认" : "";
  if (!state.selected || !state.scriptCopy) {
    host.className = "emptyState";
    host.textContent = "等待脚本闸门项目";
    return;
  }
  host.className = "editor";
  const comments = state.reviewReport?.comments || [];
  const scores = state.reviewReport?.scores || {};
  host.innerHTML = `
    <div class="reviewStrip">
      <span>Review: ${escapeHtml(state.reviewReport?.status || "PASS")}</span>
      <span>${Object.entries(scores).map(([key, value]) => `${escapeHtml(key)} ${escapeHtml(String(value))}`).join(" · ")}</span>
      <span>${comments.map(escapeHtml).join(" · ")}</span>
    </div>
    ${state.scriptBreakdown ? `<div class="scriptBreakdown"><strong>脚本拆解</strong><span>${escapeHtml((state.scriptBreakdown.beats || []).map((beat) => `${beat.timing} ${beat.role}：${beat.intent}`).join("；"))}</span></div>` : ""}
    <div class="tableWrap">
      <table class="scriptTable narrativeTable">
        <thead><tr><th>#</th><th>角色</th><th>时长</th><th>场景与环境</th><th>动作与剧情推进</th><th>中文旁白</th></tr></thead>
        <tbody>
          ${state.scriptCopy.sections.map(renderScriptRow).join("")}
        </tbody>
      </table>
    </div>
    <div class="actionBar">
      <button type="button" id="saveScript">保存</button>
      ${state.selected.current_gate === "script_gate" ? '<button type="button" id="approveScript">保存并通过</button>' : ""}
      <button type="button" id="regenerateScript">单独重新生成脚本</button>
      ${state.selected.current_gate === "script_gate" ? '<button type="button" id="rewriteScript">退回重写</button>' : ""}
    </div>
  `;
  $("#saveScript").addEventListener("click", () => {
    saveScript().catch((error) => toast(error.message, "error"));
  });
  $("#approveScript")?.addEventListener("click", approveScriptGate);
  $("#rewriteScript")?.addEventListener("click", rewriteScript);
  $("#regenerateScript").addEventListener("click", () => runManualStage("script"));
}

function renderScriptRow(section) {
  const fallback = scriptNarrativeFallback(section.number);
  return `
    <tr>
      <td>${section.number}</td>
      <td>${escapeHtml(section.role || "")}</td>
      <td><input data-section="${section.number}" data-field="timing" value="${escapeAttr(section.timing || "")}" /></td>
      <td><textarea class="sceneField" data-section="${section.number}" data-field="scene_zh">${escapeHtml(section.scene_zh || fallback.scene)}</textarea></td>
      <td><textarea class="actionField" data-section="${section.number}" data-field="action_zh">${escapeHtml(section.action_zh || fallback.action)}</textarea><textarea class="storyField" data-section="${section.number}" data-field="story_beat_zh">${escapeHtml(section.story_beat_zh || fallback.beat)}</textarea></td>
      <td><textarea class="copyField" data-section="${section.number}" data-field="voiceover_zh">${escapeHtml(section.voiceover_zh || section.subtitle_zh || section.voiceover_en || "")}</textarea></td>
    </tr>
  `;
}

function scriptNarrativeFallback(number) {
  const defaults = {
    1: { scene: "夜间卧室、暖光、床头柜与同一位照护者。", action: "建立喂养准备场景。", beat: "让观众识别熟悉时刻。" },
    2: { scene: "保持同一场景与人物状态，奶瓶在旁等待。", action: "用停顿和准备动作体现等待。", beat: "具体化痛点，为方案出现建立动机。" },
    3: { scene: "恒温杯与独立干净奶瓶并排，产品外观匹配身份图。", action: "奶液入杯，准备后经出液口倒入独立奶瓶。", beat: "以正确使用流程完成解决方案转折。" },
    4: { scene: "床头柜细节或同一人物的随身包，光线与服装一致。", action: "展示收纳和允许的产品细节。", beat: "用细节证明适配情境。" },
    5: { scene: "回到整洁床头柜全景，产品与准备完成的奶瓶同框。", action: "照护者收好物品并停留在产品上。", beat: "从混乱回到有序，自然收束。" },
  };
  return defaults[number] || defaults[1];
}

function collectScriptDraft() {
  const draft = structuredClone(state.scriptCopy);
  draft.sections.forEach((section) => {
    const timing = $(`[data-section="${section.number}"][data-field="timing"]`);
    const voiceover = $(`[data-section="${section.number}"][data-field="voiceover_zh"]`);
    const scene = $(`[data-section="${section.number}"][data-field="scene_zh"]`);
    const action = $(`[data-section="${section.number}"][data-field="action_zh"]`);
    const storyBeat = $(`[data-section="${section.number}"][data-field="story_beat_zh"]`);
    section.timing = timing.value.trim();
    section.voiceover_zh = voiceover.value.trim();
    section.subtitle_zh = section.voiceover_zh;
    section.scene_zh = scene.value.trim();
    section.action_zh = action.value.trim();
    section.story_beat_zh = storyBeat.value.trim();
  });
  return draft;
}

async function saveScript() {
  const draft = collectScriptDraft();
  const saved = await api(`/api/v2/artifacts/${encodeURIComponent(state.selectedId)}/script_copy`, {
    method: "PUT",
    body: JSON.stringify(draft),
  });
  state.scriptCopy = saved.artifact;
  toast(`已保存，stale 镜头：${saved.stale_sections.join(",") || "无"}`);
  await refreshProjects({ silent: true });
  return saved;
}

async function approveScriptGate() {
  try {
    await saveScript();
    const payload = await api("/api/v2/gates/approve", {
      method: "POST",
      body: JSON.stringify({ project_id: state.selectedId, stage: "script_gate", approver: "operator" }),
    });
    toast(`已进入 ${payload.engine.stage}`);
    await refreshProjects();
    showView("storyboard");
  } catch (error) {
    toast(error.message, "error");
  }
}

async function rewriteScript() {
  try {
    const payload = await api("/api/v2/gates/rewrite", {
      method: "POST",
      body: JSON.stringify({ project_id: state.selectedId, stage: "script_gate", reason: "human rewrite requested" }),
    });
    toast(`已退回，当前 ${payload.engine.stage}`);
    await refreshProjects();
  } catch (error) {
    toast(error.message, "error");
  }
}

function renderStoryboardNode() {
  const host = $("#shotEditor");
  const currentDuration = plannedDuration();
  $("#storyboardNodeState").textContent = state.shotPlan
    ? `${state.shotPlan.shots.length} 镜 · 当前 ${currentDuration} 秒 · 目标 30 秒`
    : "";
  if (!state.selected || !state.shotPlan) {
    host.className = "emptyState";
    const storyboardErrors = state.selected?.stages?.storyboard?.errors || [];
    host.textContent = storyboardErrors.length
      ? `分镜生成失败：${storyboardErrors.map((item) => item.error_json?.message || "未知错误").join("；")}`
      : "脚本通过后将在这里生成并展示可编辑分镜";
    return;
  }
  host.className = "editor";
  host.innerHTML = `
    <div class="tableWrap">
      <table class="scriptTable storyboardTable">
        <thead><tr><th>#</th><th>画面</th><th>生成提示词</th><th>时长</th></tr></thead>
        <tbody>${state.shotPlan.shots.map(renderShotRow).join("")}</tbody>
      </table>
    </div>
    <div class="actionBar">
      <button type="button" id="saveShots">保存分镜</button>
      <button type="button" id="saveShotsAndContinue" class="primary">保存并进入视频制作</button>
      <button type="button" id="regenerateStoryboard">根据当前脚本重新生成分镜</button>
    </div>
  `;
  $("#saveShots").addEventListener("click", () => saveShotPlan().catch((error) => toast(error.message, "error")));
  $("#saveShotsAndContinue").addEventListener("click", async () => {
    try { await saveShotPlan(); showView("production"); } catch (error) { toast(error.message, "error"); }
  });
  $("#regenerateStoryboard").addEventListener("click", () => runManualStage("storyboard"));
}

function renderShotRow(shot) {
  const duration = shot.camera_motion?.duration_sec || 6;
  return `
    <tr>
      <td>${Number(shot.number)}</td>
      <td><textarea class="copyField" data-shot="${shot.number}" data-shot-field="visual_zh">${escapeHtml(shot.visual_zh || shot.visual || "")}</textarea></td>
      <td><textarea class="promptField" data-shot="${shot.number}" data-shot-field="seedance_prompt_zh">${escapeHtml(shot.seedance_prompt_zh || shot.seedance_prompt || shot.visual_prompt || "")}</textarea></td>
      <td><input type="number" min="3" max="10" data-shot="${shot.number}" data-shot-field="duration" value="${Number(duration)}" /></td>
    </tr>
  `;
}

function renderProductionNode() {
  const host = $("#productionPanel");
  $("#productionNodeState").textContent = state.shotPlan ? "逐镜独立运行" : "";
  if (!state.selected || !state.shotPlan) {
    host.className = "emptyState";
    host.textContent = "等待分镜";
    return;
  }
  host.className = "editor";
  const takeByShot = new Map((state.takeManifest?.shots || []).map((item) => [Number(item.number), item]));
  host.innerHTML = `<div class="takeList">${state.shotPlan.shots.map((shot) => {
    const entry = takeByShot.get(Number(shot.number));
    const candidates = (entry?.takes || []).map((take) => `
      <div class="takeCandidate">
        ${take.playable
          ? `<video controls preload="metadata" data-video-state src="${escapeAttr(take.media_url || runFileUrl(state.selectedId, take.path))}"></video><span class="mediaState" data-media-state>正在读取镜头预览...</span>`
          : `<div class="mediaUnavailable">${escapeHtml(take.media_message || "无可播放视频：请以真实运行模式重新生成此 Take。")}</div>`}
        <span>Take ${escapeHtml(take.take_id)} · ${escapeHtml(take.status)}</span>
        <button type="button" data-select-shot="${shot.number}" data-select-take="${escapeAttr(take.take_id)}" ${take.status === "selected" || !take.playable ? "disabled" : ""}>${take.status === "selected" ? "已选用" : take.playable ? "选用此 Take" : "请重新生成"}</button>
      </div>
    `).join("");
    return `<section class="takeShot">
      <strong>镜头 ${shot.number} · ${shot.camera_motion?.duration_sec || 6}s</strong>
      <div class="actionBar">
        <button type="button" data-run-shot="${shot.number}" data-take-id="A">生成 Take A</button>
        <button type="button" data-run-shot="${shot.number}" data-take-id="B">生成 Take B</button>
      </div>
      <div class="takeCandidates">${candidates || "尚未生成候选"}</div>
    </section>`;
  }).join("")}</div>`;
  host.querySelectorAll("[data-run-shot]").forEach((button) => {
    button.addEventListener("click", async () => {
      await saveShotPlan();
      await runManualStage("production", Number(button.dataset.runShot), button.dataset.takeId);
    });
  });
  host.querySelectorAll("[data-select-take]").forEach((button) => {
    button.addEventListener("click", () => selectTake(Number(button.dataset.selectShot), button.dataset.selectTake));
  });
  bindVideoPreviewStates(host, "镜头预览不可播放，请重新生成该 Take 后再选用。");
}

function renderComposeNode() {
  const host = $("#composePanel");
  if (!state.selected || !state.shotPlan) {
    host.className = "emptyState";
    host.textContent = "等待成功镜头";
    return;
  }
  host.className = "editor";
  const currentDuration = plannedDuration();
  const ready = Math.abs(currentDuration - 30) <= 2;
  host.innerHTML = `<div class="actionBar"><button type="button" id="composeVideo" ${ready ? "" : "disabled"}>${
    ready ? "使用现有成功镜头合成 30 秒视频" : `当前仅 ${currentDuration} 秒，请先更新分镜并重跑镜头`
  }</button></div>`;
  $("#composeVideo").addEventListener("click", () => runManualStage("compose"));
}

function plannedDuration() {
  return (state.shotPlan?.shots || []).reduce(
    (total, shot) => total + Number(shot.camera_motion?.duration_sec || 0),
    0,
  );
}

async function saveShotPlan() {
  const draft = structuredClone(state.shotPlan);
  draft.shots.forEach((shot) => {
    shot.visual_zh = $(`[data-shot="${shot.number}"][data-shot-field="visual_zh"]`).value.trim();
    shot.seedance_prompt_zh = $(`[data-shot="${shot.number}"][data-shot-field="seedance_prompt_zh"]`).value.trim();
    shot.camera_motion = shot.camera_motion || {};
    shot.camera_motion.duration_sec = Number($(`[data-shot="${shot.number}"][data-shot-field="duration"]`).value || 6);
  });
  const saved = await api(`/api/v2/artifacts/${encodeURIComponent(state.selectedId)}/shot_plan`, {
    method: "PUT",
    body: JSON.stringify(draft),
  });
  state.shotPlan = saved.artifact;
  toast(`分镜已保存，变更镜头：${saved.stale_sections.join(",") || "无"}`);
  return saved;
}

async function runManualStage(stage, shotIndex = null, takeId = null) {
  try {
    const estimates = { analysis: 30, research: 30, strategy: 25, script: 35, storyboard: 45, production: 100, compose: 35 };
    beginOperation(shotIndex ? `正在生成镜头 ${shotIndex} Take ${takeId || "A"}` : `正在运行${stageLabel(stage)}`, estimates[stage] || 40);
    const payload = await api("/api/v2/manual/run", {
      method: "POST",
      body: JSON.stringify({
        project_id: state.selectedId,
        stage,
        shot_index: shotIndex,
        take_id: takeId,
        mock: $("#runtimeMode").value !== "real",
      }),
    });
    toast(`${stage}${shotIndex ? ` 镜头 ${shotIndex}` : ""} 已运行到 ${payload.engine.stage}`);
    await refreshProjects();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    endOperation();
  }
}

async function selectTake(shotIndex, takeId) {
  try {
    await api("/api/v2/takes/select", {
      method: "POST",
      body: JSON.stringify({ project_id: state.selectedId, shot_index: shotIndex, take_id: takeId }),
    });
    toast(`镜头 ${shotIndex} 已选用 Take ${takeId}`);
    await refreshProjects();
  } catch (error) {
    toast(error.message, "error");
  }
}

function renderHeroGate() {
  const host = $("#heroEditor");
  $("#heroGateState").textContent = state.selected?.current_gate === "hero_gate" ? "待确认" : "";
  if (!state.selected || state.selected.current_gate !== "hero_gate" || !state.assetManifest) {
    host.className = "emptyState";
    host.textContent = "等待关键帧闸门项目";
    return;
  }
  host.className = "heroReview";
  const shots = new Map((state.shotPlan?.shots || []).map((shot) => [Number(shot.number), shot]));
  const identityFrame = state.assetManifest.hero_frames[0];
  host.innerHTML = `
    <div class="identityAnchor">
      <div class="nodeToolHead"><div><strong>产品身份锚点</strong><span>所有镜头锁定同一产品外观，不代表场景关键帧</span></div></div>
      <div class="thumb"><img src="${escapeAttr(identityFrame?.preview_url || "")}" alt="产品身份参考" /></div>
    </div>
    <div class="shotContactSheet">
      <div class="nodeToolHead"><div><strong>逐镜核对表</strong><span>确认场景、动作、温标与前后连续性</span></div></div>
      ${state.assetManifest.hero_frames.map((frame) => renderHeroFrame(frame, shots.get(Number(frame.number)))).join("")}
    </div>
    <div class="actionBar wide"><button type="button" id="approveHero">全部确认</button></div>
  `;
  host.querySelectorAll("[data-regen]").forEach((button) => {
    button.addEventListener("click", () => regenHero(Number(button.dataset.regen)));
  });
  $("#approveHero").addEventListener("click", approveHeroGate);
}

function renderHeroFrame(frame, shot) {
  const camera = shot?.camera_motion
    ? `${motionLabels[shot.camera_motion.type] || shot.camera_motion.type || ""} · ${shot.camera_motion.duration_sec || 3}s`
    : "";
  return `
    <article class="contactShot">
      <div class="heroMeta">
        <strong>镜头 ${frame.number}</strong>
        <span>${escapeHtml(camera)}</span>
        <p>${escapeHtml(shot?.visual || "")}</p>
      </div>
      <button type="button" data-regen="${frame.number}">重建锚点</button>
    </article>
  `;
}

async function regenHero(shotIndex) {
  try {
    await api("/api/v2/hero/regen", {
      method: "POST",
      body: JSON.stringify({ project_id: state.selectedId, shot_index: shotIndex }),
    });
    toast(`Shot ${shotIndex} 已重生成`);
    await loadSelectedProject(state.selectedId);
  } catch (error) {
    toast(error.message, "error");
  }
}

async function approveHeroGate() {
  try {
    const payload = await api("/api/v2/gates/approve", {
      method: "POST",
      body: JSON.stringify({ project_id: state.selectedId, stage: "hero_gate", approver: "operator" }),
    });
    toast(`已完成到 ${payload.engine.stage}`);
    await refreshProjects();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function retryShot(shotIndex) {
  try {
    const payload = await api("/api/v2/tasks/retry", {
      method: "POST",
      body: JSON.stringify({ project_id: state.selectedId, shot_index: shotIndex }),
    });
    toast(`镜头 ${shotIndex} 已重试：${payload.engine.status}`);
    await refreshProjects();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function retryTask(taskId) {
  try {
    const payload = await api("/api/v2/tasks/retry", {
      method: "POST",
      body: JSON.stringify({ project_id: state.selectedId, task_id: taskId, mock: $("#runtimeMode").value !== "real" }),
    });
    toast(`节点已重试：${payload.engine.stage} · ${payload.engine.status}`);
    await refreshProjects();
  } catch (error) {
    toast(error.message, "error");
  }
}

function renderDelivery() {
  const host = $("#deliveryPanel");
  const delivered = state.projects.filter((project) => project.status === "succeeded" && project.delivery_ready);
  $("#deliveryState").textContent = delivered.length ? `${delivered.length} 个可交付` : "";
  if (!delivered.length) {
    host.className = "emptyState";
    host.textContent = "暂无可交付项目";
    return;
  }
  host.className = "delivery";
  const selectedDelivered = delivered.find((project) => project.project_id === state.selectedId) || null;
  const renderUrl = selectedDelivered && state.renderReport?.output_path
    ? runFileUrl(selectedDelivered.project_id, state.renderReport.output_path)
    : "";
  const report = selectedDelivered ? state.runReport : null;
  const probe = report?.render_report?.ffprobe || {};
  const qaStatus = report?.qa_report?.status || "待生成";
  const elapsed = report?.elapsed_s == null ? "--" : `${Number(report.elapsed_s).toFixed(1)}s`;
  const failureCount = report?.failures?.length || 0;
  host.innerHTML = `
    <div class="deliveryList">
      ${delivered.map((project) => `
        <button type="button" data-open="${escapeAttr(project.project_id)}" class="${project.project_id === selectedDelivered?.project_id ? "active" : ""}" title="${escapeAttr(project.project_id)}">
          ${escapeHtml(project.project_id)} · ¥${Number(project.cost.total_cost_cny || 0).toFixed(2)}
        </button>
      `).join("")}
    </div>
    <div class="deliveryDetail">
      ${selectedDelivered ? (renderUrl
        ? `<video controls preload="metadata" data-video-state src="${escapeAttr(renderUrl)}"></video><p class="mediaState" data-media-state>正在读取交付成片...</p>`
        : `<p class="mediaState error">当前项目没有可播放的交付成片，请回到“生产”完成合成与质检。</p>`
      ) : `<p class="mediaState">请从左侧选择一个可交付项目。</p>`}
      <div class="runSummary">
        <span>耗时 ${escapeHtml(elapsed)}</span>
        <span>画面 ${escapeHtml(probe.resolution || "--")}</span>
        <span>QA ${escapeHtml(qaStatus)}</span>
        <span>失败 ${failureCount}</span>
      </div>
      <div class="actionBar">
        ${selectedDelivered ? `<a class="buttonLink" href="/api/v2/download/${encodeURIComponent(selectedDelivered.project_id)}">下载 zip</a>
        <a class="buttonLink" target="_blank" rel="noopener" href="/api/v2/reports/${encodeURIComponent(selectedDelivered.project_id)}">运行报告</a>` : ""}
        <input id="feedbackInput" placeholder="一句话反馈" />
        <button type="button" id="sendFeedback">写入反馈</button>
      </div>
    </div>
  `;
  host.querySelectorAll("[data-open]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedId = button.dataset.open;
      refreshProjects();
    });
  });
  if (selectedDelivered) {
    $("#sendFeedback").addEventListener("click", () => sendFeedback(selectedDelivered.project_id));
  }
  bindVideoPreviewStates(host, "交付成片不可播放。该项目已被识别为无效媒体，请重新合成并通过质检。");
}

async function sendFeedback(projectId) {
  const input = $("#feedbackInput");
  try {
    await api("/api/v2/feedback", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, text: input.value.trim() }),
    });
    input.value = "";
    toast("反馈已写入");
  } catch (error) {
    toast(error.message, "error");
  }
}

function runFileUrl(projectId, pathText) {
  const normal = String(pathText || "").replace(/\\/g, "/");
  const marker = `/data/runs/${projectId}/`.toLowerCase();
  const position = normal.toLowerCase().lastIndexOf(marker);
  const relative = position >= 0
    ? normal.slice(position + marker.length)
    : /^(artifacts|shots)\//.test(normal)
      ? normal
      : `artifacts/${normal.split("/").pop()}`;
  const encodedPath = relative.split("/").filter(Boolean).map(encodeURIComponent).join("/");
  return `/api/v2/runs/${encodeURIComponent(projectId)}/${encodedPath}`;
}

function bindVideoPreviewStates(host, errorMessage) {
  host.querySelectorAll("video[data-video-state]").forEach((video) => {
    const stateLabel = video.parentElement.querySelector("[data-media-state]");
    if (!stateLabel) return;
    video.addEventListener("loadedmetadata", () => {
      const seconds = Number(video.duration);
      stateLabel.className = "mediaState ok";
      stateLabel.textContent = Number.isFinite(seconds) && seconds > 0
        ? `媒体已就绪：${seconds.toFixed(1)} 秒`
        : "媒体已就绪";
    });
    video.addEventListener("error", () => {
      stateLabel.className = "mediaState error";
      stateLabel.textContent = errorMessage;
    });
  });
}

function statusClass(status) {
  return `status-${String(status || "idle").replace(/_/g, "-")}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

boot();
