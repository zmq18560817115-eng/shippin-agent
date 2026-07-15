const state = {
  projects: [],
  materials: [],
  productLibrary: [],
  productLibraryGeneratedAt: null,
  productLibrarySources: [],
  selectedId: null,
  selected: null,
  scriptCopy: null,
  reviewReport: null,
  shotPlan: null,
  assetManifest: null,
  takeManifest: null,
  renderReport: null,
  runReport: null,
  refreshing: false,
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

async function boot() {
  bindEvents();
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
  }
}

function bindEvents() {
  $("#startForm").addEventListener("submit", startProject);
  $("#collectForm").addEventListener("submit", collectLinks);
  $("#crawlForm").addEventListener("submit", crawlTikTok);
  $("#refreshButton").addEventListener("click", () => refreshProjects());
  $("#refreshProductLibrary").addEventListener("click", refreshProductLibrary);
  $("#runResearch").addEventListener("click", (event) => runFlowCapability("research", event.currentTarget, "#researchResult"));
  $("#runStrategy").addEventListener("click", (event) => runFlowCapability("strategy", event.currentTarget, "#strategyResult"));
  $("#runScriptBreakdown").addEventListener("click", (event) => runFlowCapability("script_breakdown", event.currentTarget, "#scriptBreakdownResult"));
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
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
    $("#startState").textContent = "";
  }
}

async function collectLinks(event) {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  const action = button.value || "import";
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
  }
}

async function crawlTikTok(event) {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  $("#crawlState").textContent = "发现与下载中";
  try {
    const payload = await api("/api/v2/collect/tiktok/crawl", {
      method: "POST",
      body: JSON.stringify({
        target_type: $("#crawlTargetType").value,
        target: $("#crawlTarget").value.trim(),
        limit: Number($("#crawlLimit").value || 3),
        product_id: $("#productSelect").value,
        mock: $("#runtimeMode").value !== "real",
      }),
    });
    if (payload.results?.length) state.selectedId = payload.results[0].project_id;
    toast(`发现 ${payload.discovered_count} 条，完成 ${payload.completed_count} 条，失败 ${payload.failed_count} 条`);
    await refreshProjects();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
    $("#crawlState").textContent = "";
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
    if (state.selectedId) {
      await loadSelectedProject(state.selectedId);
    } else {
      renderPanels();
    }
    await loadMaterials();
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
  const caption = meta.caption || meta.source_url || "";
  return `
    <article class="materialItem">
      <div>
        <strong>${escapeHtml(item.material_id)}</strong>
        <span>${escapeHtml(meta.source_keyword || "manual_tiktok")} · ${escapeHtml(item.status || "raw")}</span>
        <p>${escapeHtml(caption)}</p>
      </div>
      <button type="button" data-start-material="${escapeAttr(item.material_id)}">发起项目</button>
    </article>
  `;
}

async function loadSelectedProject(projectId) {
  state.selected = await api(`/api/v2/pipeline/${encodeURIComponent(projectId)}`);
  state.scriptCopy = null;
  state.reviewReport = null;
  state.shotPlan = null;
  state.assetManifest = null;
  state.takeManifest = null;
  state.renderReport = null;
  state.runReport = null;

  state.scriptCopy = await safeArtifact(projectId, "script_copy");
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
  if (!state.projects.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="muted">暂无项目</td></tr>';
    return;
  }
  state.projects.forEach((project) => {
    const row = document.createElement("tr");
    row.className = project.project_id === state.selectedId ? "selected" : "";
    row.innerHTML = `
      <td>
        <button type="button" class="linkButton" data-open="${escapeAttr(project.project_id)}">
          ${escapeHtml(project.project_id)}
        </button>
        <div class="subline">${escapeHtml(project.product_id || "")}</div>
      </td>
      <td>${renderNodes(project.nodes)}</td>
      <td>
        <span class="stageTag ${statusClass(project.status)}">${escapeHtml(project.current_stage || project.status)}</span>
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
    button.addEventListener("click", () => {
      state.selectedId = button.dataset.open;
      refreshProjects();
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
}

function renderNodes(nodes) {
  return `<div class="nodes">${nodes
    .map((node) => `<span class="node ${statusClass(node.status)}" title="${node.agent}: ${node.status}">${statusGlyph[node.status] || "·"} ${node.agent}</span>`)
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
  return `<button type="button" data-open="${escapeAttr(project.project_id)}">打开</button>`;
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
    <div class="tableWrap">
      <table class="scriptTable">
        <thead><tr><th>#</th><th>角色</th><th>时长</th><th>英文台词</th></tr></thead>
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
  return `
    <tr>
      <td>${section.number}</td>
      <td>${escapeHtml(section.role || "")}</td>
      <td><input data-section="${section.number}" data-field="timing" value="${escapeAttr(section.timing || "")}" /></td>
      <td><textarea data-section="${section.number}" data-field="voiceover_en">${escapeHtml(section.voiceover_en || "")}</textarea></td>
    </tr>
  `;
}

function collectScriptDraft() {
  const draft = structuredClone(state.scriptCopy);
  draft.sections.forEach((section) => {
    const timing = $(`[data-section="${section.number}"][data-field="timing"]`);
    const voiceover = $(`[data-section="${section.number}"][data-field="voiceover_en"]`);
    section.timing = timing.value.trim();
    section.voiceover_en = voiceover.value.trim();
    section.subtitle_en = section.voiceover_en;
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
      <table class="scriptTable">
        <thead><tr><th>#</th><th>画面</th><th>生成提示词</th><th>时长</th></tr></thead>
        <tbody>${state.shotPlan.shots.map(renderShotRow).join("")}</tbody>
      </table>
    </div>
    <div class="actionBar">
      <button type="button" id="saveShots">保存分镜</button>
      <button type="button" id="regenerateStoryboard">根据当前脚本重新生成分镜</button>
    </div>
  `;
  $("#saveShots").addEventListener("click", () => saveShotPlan().catch((error) => toast(error.message, "error")));
  $("#regenerateStoryboard").addEventListener("click", () => runManualStage("storyboard"));
}

function renderShotRow(shot) {
  const duration = shot.camera_motion?.duration_sec || 6;
  return `
    <tr>
      <td>${Number(shot.number)}</td>
      <td><textarea data-shot="${shot.number}" data-shot-field="visual">${escapeHtml(shot.visual || "")}</textarea></td>
      <td><textarea data-shot="${shot.number}" data-shot-field="seedance_prompt">${escapeHtml(shot.seedance_prompt || shot.visual_prompt || "")}</textarea></td>
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
        <video controls preload="metadata" src="${runFileUrl(state.selectedId, take.path)}"></video>
        <span>Take ${escapeHtml(take.take_id)} · ${escapeHtml(take.status)}</span>
        <button type="button" data-select-shot="${shot.number}" data-select-take="${escapeAttr(take.take_id)}" ${take.status === "selected" ? "disabled" : ""}>${take.status === "selected" ? "已选用" : "选用此 Take"}</button>
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
    shot.visual = $(`[data-shot="${shot.number}"][data-shot-field="visual"]`).value.trim();
    shot.seedance_prompt = $(`[data-shot="${shot.number}"][data-shot-field="seedance_prompt"]`).value.trim();
    shot.visual_prompt = shot.seedance_prompt;
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
  host.className = "heroGrid";
  const shots = new Map((state.shotPlan?.shots || []).map((shot) => [Number(shot.number), shot]));
  host.innerHTML = `
    ${state.assetManifest.hero_frames.map((frame) => renderHeroFrame(frame, shots.get(Number(frame.number)))).join("")}
    <div class="actionBar wide"><button type="button" id="approveHero">全部确认</button></div>
  `;
  host.querySelectorAll("[data-regen]").forEach((button) => {
    button.addEventListener("click", () => regenHero(Number(button.dataset.regen)));
  });
  $("#approveHero").addEventListener("click", approveHeroGate);
}

function renderHeroFrame(frame, shot) {
  const camera = shot?.camera_motion
    ? `${shot.camera_motion.type || ""} · ${shot.camera_motion.duration_sec || 3}s`
    : "";
  return `
    <article class="heroItem">
      <div class="thumb">
        <img src="${escapeAttr(frame.preview_url || "")}" alt="shot ${frame.number}" />
      </div>
      <div class="heroMeta">
        <strong>Shot ${frame.number}</strong>
        <span>${escapeHtml(camera)}</span>
        <p>${escapeHtml(shot?.visual || "")}</p>
      </div>
      <button type="button" data-regen="${frame.number}">单镜重生成</button>
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
  const delivered = state.projects.filter((project) => project.status === "succeeded");
  $("#deliveryState").textContent = delivered.length ? `${delivered.length} 个可交付` : "";
  if (!delivered.length) {
    host.className = "emptyState";
    host.textContent = "暂无可交付项目";
    return;
  }
  host.className = "delivery";
  const selectedDelivered = state.selected?.status === "succeeded" ? state.selected : delivered[0];
  const renderUrl = state.renderReport?.output_path
    ? runFileUrl(selectedDelivered.project_id, state.renderReport.output_path)
    : "";
  const report = state.runReport;
  const probe = report?.render_report?.ffprobe || {};
  const qaStatus = report?.qa_report?.status || "待生成";
  const elapsed = report?.elapsed_s == null ? "--" : `${Number(report.elapsed_s).toFixed(1)}s`;
  const failureCount = report?.failures?.length || 0;
  host.innerHTML = `
    <div class="deliveryList">
      ${delivered.map((project) => `
        <button type="button" data-open="${escapeAttr(project.project_id)}" class="${project.project_id === selectedDelivered.project_id ? "active" : ""}">
          ${escapeHtml(project.project_id)} · ¥${Number(project.cost.total_cost_cny || 0).toFixed(2)}
        </button>
      `).join("")}
    </div>
    <div class="deliveryDetail">
      ${renderUrl ? `<video controls src="${escapeAttr(renderUrl)}"></video>` : ""}
      <div class="runSummary">
        <span>耗时 ${escapeHtml(elapsed)}</span>
        <span>画面 ${escapeHtml(probe.resolution || "--")}</span>
        <span>QA ${escapeHtml(qaStatus)}</span>
        <span>失败 ${failureCount}</span>
      </div>
      <div class="actionBar">
        <a class="buttonLink" href="/api/v2/download/${encodeURIComponent(selectedDelivered.project_id)}">下载 zip</a>
        <a class="buttonLink" target="_blank" rel="noopener" href="/api/v2/reports/${encodeURIComponent(selectedDelivered.project_id)}">运行报告</a>
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
  $("#sendFeedback").addEventListener("click", () => sendFeedback(selectedDelivered.project_id));
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
  const parts = normal.split("/");
  const file = parts[parts.length - 1];
  return `/api/v2/runs/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(file)}`;
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
