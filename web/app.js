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
  runtime: null,
  refreshing: false,
  operation: null,
  currentView: "home",
  selectedRevision: "",
  showAllProjects: false,
  collectionJobs: [],
  selectedCollectionJobId: null,
  agentContracts: {},
};

const NAV = [
  { key: "home", label: "工作首页", icon: "layout-dashboard", views: ["home"] },
  { key: "project", label: "视频项目", icon: "folder-kanban",
    views: ["proj_overview", "proj_strategy", "proj_script", "proj_storyboard", "proj_production", "proj_qa", "proj_archive"] },
  { key: "tools", label: "快速工具", icon: "wand-sparkles",
    views: ["tool_research", "tool_strategy", "tool_script", "tool_breakdown", "tool_storyboard", "tool_shot"] },
  { key: "materials", label: "素材中心", icon: "database",
    views: ["mat_product", "mat_reference", "mat_collect", "mat_analysis", "mat_favorites"] },
  { key: "tasks", label: "任务中心", icon: "list-checks",
    views: ["task_running", "task_todo", "task_failed", "task_done"] },
  { key: "delivery", label: "交付中心", icon: "package-check",
    views: ["del_pending", "del_passed", "del_archived", "del_downloads"] },
];

const views = {
  home: { group: "home", label: "工作首页", title: "工作首页", description: "继续上次任务，或从这里开始一段新的生产。", sections: ["homeDashboard"] },

  proj_overview: { group: "project", label: "项目概览", title: "项目概览", description: "创建任务，或打开一个在制项目继续工作。", sections: ["projectSetup", "projectQueue"] },
  proj_strategy: { group: "project", label: "内容策略", title: "内容策略", description: "审阅研究简报转化的内容方向与卖点优先级。", sections: ["scriptGate"] },
  proj_script: { group: "project", label: "脚本", title: "脚本", description: "审阅脚本拆解与文案，确认后进入分镜。", sections: ["scriptGate"] },
  proj_storyboard: { group: "project", label: "分镜", title: "分镜", description: "调整镜头计划，确认产品关键帧与视觉连续性。", sections: ["storyboardNode", "heroGate"] },
  proj_production: { group: "project", label: "镜头制作", title: "镜头制作", description: "逐镜生成、选择最佳 Take，并合成为 30 秒成片。", sections: ["productionNode", "composeNode"] },
  proj_qa: { group: "project", label: "成片验收", title: "成片验收", description: "检查质检结果与人工目检，决定是否放行交付。", sections: ["deliveryNode"] },
  proj_archive: { group: "project", label: "交付归档", title: "交付归档", description: "下载交付包，记录反馈并归档。", sections: ["deliveryNode"] },

  tool_research: { group: "tools", label: "视频研究分析", title: "视频研究分析", description: "独立运行研究分析 Agent，不创建生产项目。", sections: ["toolsSection"], tool: "research" },
  tool_strategy: { group: "tools", label: "内容策略生成", title: "内容策略生成", description: "独立运行内容策略 Agent。", sections: ["toolsSection"], tool: "strategy" },
  tool_script: { group: "tools", label: "脚本生成", title: "脚本生成", description: "独立运行脚本生成 Agent。", sections: ["toolsSection"], tool: "script" },
  tool_breakdown: { group: "tools", label: "脚本拆解", title: "脚本拆解", description: "独立运行脚本拆解 Agent。", sections: ["toolsSection"], tool: "script_breakdown" },
  tool_storyboard: { group: "tools", label: "分镜生成", title: "分镜生成", description: "独立运行分镜生成 Agent。", sections: ["toolsSection"], tool: "storyboard" },
  tool_shot: { group: "tools", label: "单镜视频生成", title: "单镜视频生成", description: "独立运行单镜制作 Agent，生成 720P 竖屏 Take。", sections: ["toolsSection"], tool: "production" },

  mat_product: { group: "materials", label: "产品素材", title: "产品素材", description: "管理产品事实素材库。", sections: ["productAssets"] },
  mat_reference: { group: "materials", label: "TikTok参考素材", title: "TikTok 参考素材", description: "浏览已入库的参考视频素材。", sections: ["referenceLibrarySection"] },
  mat_collect: { group: "materials", label: "素材采集", title: "素材采集", description: "设置后台自动采集，或补充导入链接。", sections: ["collectSection"] },
  mat_analysis: { group: "materials", label: "素材分析", title: "素材分析", description: "独立运行研究分析，理解结构与节奏。", sections: ["analysisSection"] },
  mat_favorites: { group: "materials", label: "收藏与项目素材包", title: "收藏与项目素材包", description: "查看当前项目选用的产品与参考素材。", sections: ["favoritesSection"] },

  task_running: { group: "tasks", label: "运行中", title: "运行中", description: "正在排队或执行的任务。", sections: ["taskCenter"], taskFilter: "running" },
  task_todo: { group: "tasks", label: "待我处理", title: "待我处理", description: "等待人工确认的闸门与复核。", sections: ["taskCenter"], taskFilter: "todo" },
  task_failed: { group: "tasks", label: "失败任务", title: "失败任务", description: "失败或被阻塞、需要处理的任务。", sections: ["taskCenter"], taskFilter: "failed" },
  task_done: { group: "tasks", label: "已完成", title: "已完成", description: "已交付或已完成的项目。", sections: ["taskCenter"], taskFilter: "done" },

  del_pending: { group: "delivery", label: "待验收", title: "待验收", description: "等待成片人工验收的项目。", sections: ["deliveryCenter"], deliveryFilter: "pending" },
  del_passed: { group: "delivery", label: "已通过", title: "已通过", description: "通过验收、可交付的项目。", sections: ["deliveryCenter"], deliveryFilter: "passed" },
  del_archived: { group: "delivery", label: "已归档", title: "已归档", description: "已归档的交付项目。", sections: ["deliveryCenter"], deliveryFilter: "archived" },
  del_downloads: { group: "delivery", label: "下载记录", title: "下载记录", description: "可下载的交付包与运行报告。", sections: ["deliveryCenter"], deliveryFilter: "downloads" },
};

const DEFAULT_VIEW = "home";
const MATERIAL_VIEW_SECTIONS = new Set(["referenceLibrarySection", "analysisSection", "favoritesSection"]);

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
  storyboard: "分镜生成", asset: "产品素材", hero_gate: "分镜确认", production: "视频生成", take_gate: "镜头选用",
  compose: "视频合成", final_qa: "成片质检", archive: "交付归档", succeeded: "已交付",
  failed: "运行失败", awaiting_human: "等待人工确认", running: "运行中", queued: "排队中",
  idle: "未开始", blocked: "已阻塞", needs_review: "需要复核",
};

const agentLabels = {
  collector: "素材采集", analysis: "研究分析", script: "脚本文案", storyboard: "分镜策划",
  asset: "产品素材", media: "视频制作", review: "质量审核",
};

const independentActionLabels = {
  orchestrator: "总控规划",
  collector: "素材采集",
  analysis: "素材分析",
  research: "研究洞察",
  strategy: "内容策略",
  script: "脚本生成",
  script_breakdown: "脚本拆解",
  storyboard: "分镜生成",
  asset: "素材匹配",
  production: "单镜制作",
  review: "内容审核",
  feedback: "反馈学习",
};

const independentActionHints = {
  orchestrator: "输入完整任务目标，由总控 Agent 给出执行路径、闸门、风险和交付清单。",
  collector: "按关键词、账号或话题发现参考视频；可选择下载入库后进入分析。",
  analysis: "输入视频转写、素材说明或参考链接，生成结构、节奏和镜头拆解。",
  research: "输入转写、竞品文案或研究资料，生成结构、节奏与受众洞察。",
  strategy: "输入研究结论、产品事实或内容需求，生成受众、卖点、钩子和 CTA 策略。",
  script: "输入产品、受众、平台和内容需求，生成完整中文脚本。",
  script_breakdown: "输入已有脚本或内容需求，生成逐段意图、画面和连续性拆解。",
  storyboard: "输入场景、人物、动作、镜头运动和风格，生成可编辑分镜。",
  asset: "输入镜头需求或脚本，为产品匹配批准素材并生成可确认的关键帧清单。",
  production: "输入单镜画面 Prompt，使用产品素材库生成 720P 竖屏视频。",
  review: "输入脚本文本或内容需求，生成产品安全与合规审核报告。",
  feedback: "输入人工复盘结论、问题和优化要求，保存为可下载的反馈记录。",
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

function renderAgentResult(host, payload) {
  const download = payload.download_url
    ? `<a class="buttonLink" href="${escapeAttr(payload.download_url)}">下载本节点 JSON</a>`
    : "";
  const promotable = payload.project_id && payload.project_id.startsWith("scratch-")
    && ["analysis_report", "script_copy", "shot_plan"].includes(payload.artifact_name);
  const promote = promotable
    ? `<button type="button" class="promoteStandalone" data-project-id="${escapeAttr(payload.project_id)}" data-artifact-name="${escapeAttr(payload.artifact_name)}">用此产物创建生产项目</button>`
    : "";
  const artifact = payload.artifact || {};
  const contract = payload.meta?.agent_contract || {};
  const brief = payload.meta?.creative_brief || {};
  const executionContext = contract.identity ? `
    <div class="agentExecutionContext">
      <strong>${escapeHtml(contract.identity)}</strong>
      <span>${escapeHtml(brief.style || "自动匹配风格")} · ${escapeHtml(brief.audience || "通用受众")} · ${escapeHtml(brief.freedom_instruction || "平衡创作")}</span>
    </div>` : "";
  host.className = "nodeResult complete";
  host.innerHTML = `
    <div class="resultHead"><strong>${escapeHtml(artifactLabel(payload.artifact_name))}</strong>${download}${promote}</div>
    ${executionContext}
    ${payload.project_id && payload.project_id.startsWith("scratch-") ? "<p>独立工作区产物已保存，不会出现在生产项目列表中。</p>" : ""}
    <div class="agentFriendlyResult">${renderFriendlyArtifact(payload.artifact_name, artifact)}</div>
    <details class="rawArtifact"><summary>查看 JSON</summary><pre>${escapeHtml(JSON.stringify(artifact, null, 2))}</pre></details>
  `;
}

function creativeRequestFields() {
  return {
    creative_style: $("#independentCreativeStyle")?.value || "",
    target_audience: $("#independentTargetAudience")?.value.trim() || "",
    creative_freedom: $("#independentCreativeFreedom")?.value || "balanced",
  };
}

function artifactLabel(name) {
  return {
    tiktok_capture: "TikTok 采集结果",
    tiktok_discovery: "TikTok 发现结果",
    analysis_report: "素材分析",
    research_brief: "研究洞察",
    strategy_brief: "内容策略",
    script_copy: "脚本文案",
    script_breakdown: "脚本拆解",
    shot_plan: "分镜计划",
    shot_report: "单镜制作结果",
    review_report: "内容审核",
    feedback_record: "反馈记录",
  }[name] || name;
}

function renderFriendlyArtifact(name, artifact) {
  if (name === "orchestration_plan") {
    const route = Array.isArray(artifact.route) ? artifact.route : [];
    const gates = Array.isArray(artifact.human_gates) ? artifact.human_gates : [];
    const risks = Array.isArray(artifact.risks) ? artifact.risks : [];
    return `<div class="agentResultStack">
      <section><strong>执行路径</strong><ol>${route.map((item) => `<li>${escapeHtml(typeof item === "string" ? item : item.stage || item.action || JSON.stringify(item))}</li>`).join("") || "<li>暂无执行路径</li>"}</ol></section>
      <section><strong>人工闸门</strong><ul>${gates.map((item) => `<li>${escapeHtml(typeof item === "string" ? item : item.name || item.stage || JSON.stringify(item))}</li>`).join("") || "<li>暂无人工闸门</li>"}</ul></section>
      <section><strong>主要风险</strong><ul>${risks.map((item) => `<li>${escapeHtml(typeof item === "string" ? item : item.message || item.risk || JSON.stringify(item))}</li>`).join("") || "<li>暂无新增风险</li>"}</ul></section>
    </div>`;
  }
  if (name === "script_copy") {
    const sections = Array.isArray(artifact.sections) ? artifact.sections : [];
    return `<div class="agentResultCards">${sections.map((section) => `
      <article class="agentResultCard"><strong>${escapeHtml(section.role || "脚本段落")} · ${escapeHtml(section.timing || "")}</strong>
      <p>${escapeHtml(section.voiceover_zh || section.subtitle_zh || section.voiceover_en || "")}</p>
      <small>场景：${escapeHtml(section.scene_zh || "未填写")}</small><small>动作：${escapeHtml(section.action_zh || "未填写")}</small></article>`).join("") || "<p>未生成脚本段落。</p>"}</div>`;
  }
  if (name === "shot_plan") {
    const shots = Array.isArray(artifact.shots) ? artifact.shots : [];
    return `<div class="agentResultCards">${shots.map((shot) => `
      <article class="agentResultCard"><strong>镜头 ${escapeHtml(shot.number)} · ${escapeHtml(shot.camera_motion?.duration_sec || 6)} 秒</strong>
      <p>${escapeHtml(shot.visual_zh || shot.visual || "")}</p><small>生成提示：${escapeHtml(shot.seedance_prompt_zh || shot.seedance_prompt || "")}</small></article>`).join("") || "<p>未生成镜头。</p>"}</div>`;
  }
  if (name === "review_report") {
    const scores = Object.entries(artifact.scores || {});
    return `<div class="agentReview"><strong class="reviewStatus ${escapeAttr(String(artifact.status || "WARNING").toLowerCase())}">${escapeHtml(reviewStatusLabel(artifact.status))}</strong>
      <div class="scoreChips">${scores.map(([key, value]) => `<span>${escapeHtml(reviewScoreLabel(key))} ${escapeHtml(value)}</span>`).join("")}</div>
      <p>${escapeHtml((artifact.comments || []).join("；") || "暂无审核说明")}</p></div>`;
  }
  if (name === "analysis_report") {
    const structure = Array.isArray(artifact.structure) ? artifact.structure.join(" → ") : "";
    return `<div class="agentResultCard"><strong>3 秒钩子</strong><p>${escapeHtml(artifact.hook_3s || "未生成")}</p><small>内容结构：${escapeHtml(structure || "未生成")}</small></div>`;
  }
  if (name === "tiktok_discovery" || name === "tiktok_capture") {
    const items = Array.isArray(artifact.items) ? artifact.items : artifact.results || [];
    return `<div class="agentResultCards">${items.slice(0, 10).map((item) => `<article class="agentResultCard"><strong>${escapeHtml(item.title || item.video_title || item.url || "TikTok 素材")}</strong><p>${escapeHtml(item.caption || item.description || "")}</p>${item.url ? `<a href="${escapeAttr(item.url)}" target="_blank" rel="noopener">打开来源</a>` : ""}</article>`).join("") || "<p>暂无可展示素材。</p>"}</div>`;
  }
  if (name === "feedback_record") return `<div class="agentResultCard"><p>${escapeHtml(artifact.text || "")}</p></div>`;
  return `<div class="agentResultCard"><p>产物已生成，可下载 JSON 或用于创建生产项目。</p></div>`;
}

function reviewStatusLabel(status) {
  return { PASS: "审核通过", WARNING: "需要关注", BLOCKED: "审核阻止" }[String(status || "").toUpperCase()] || "待审核";
}

function reviewScoreLabel(key) {
  return { hook: "钩子", clarity: "清晰度", compliance: "合规", product_fit: "产品匹配", pacing: "节奏", cta: "行动号召", asset_traceability: "素材可追溯" }[key] || key;
}

async function loadIndependentAgentActions() {
  const select = $("#independentAgentAction");
  try {
    const capabilityMap = await api("/api/v2/agents");
    const actions = [];
    (capabilityMap.agents || []).forEach((agent) => {
      String(agent.independent_action || "").split(",").map((item) => item.trim()).filter(Boolean).forEach((action) => {
        if (independentActionLabels[action] && !actions.includes(action)) actions.push(action);
        if (independentActionLabels[action]) state.agentContracts[action] = agent;
      });
    });
    select.innerHTML = actions.map((action) => `<option value="${escapeAttr(action)}">${escapeHtml(independentActionLabels[action])}</option>`).join("");
  } catch {
    select.innerHTML = '<option value="collector">素材采集</option>';
  }
  updateIndependentAgentUI();
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

function installCommandIcons(root = document) {
  const rules = [
    [/刷新/, "refresh-cw"], [/下载/, "download"], [/(开始|运行|生成|抓取)/, "play"],
    [/(保存|通过|确认|选用)/, "check"], [/(新增|增加)/, "plus"], [/删除/, "trash-2"],
    [/(打开|查看)/, "arrow-up-right"], [/(停止|取消)/, "square"], [/(重试|重跑|重做)/, "rotate-cw"],
    [/合成/, "clapperboard"], [/反馈/, "message-square"], [/(拒绝|退回)/, "undo-2"], [/关闭/, "x"],
  ];
  root.querySelectorAll("button:not([data-icon-ready]), .buttonLink:not([data-icon-ready])").forEach((button) => {
    button.dataset.iconReady = "true";
    if (button.querySelector("svg, [data-lucide]")) return;
    const match = rules.find(([pattern]) => pattern.test(button.textContent.trim()));
    if (!match) return;
    button.classList.add("iconAction");
    button.insertAdjacentHTML("afterbegin", `<i data-lucide="${match[1]}"></i>`);
  });
  window.lucide?.createIcons({ attrs: { "stroke-width": 1.8 } });
}

async function boot() {
  bindEvents();
  installCommandIcons();
  await loadWorkbenchSession();
  const initialView = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("view");
  showView(views[initialView] ? initialView : DEFAULT_VIEW, { updateUrl: false });
  await checkHealth();
  await loadIndependentAgentActions();
  await loadProductLibrary();
  await loadProducts();
  await loadAutoCollector();
  await loadCollectionJobs();
  await refreshProjects();
  installCommandIcons();
  window.setInterval(() => {
    if (!document.hidden) refreshProjects({ silent: true });
  }, 10000);
  window.setInterval(() => loadAutoCollector(), 15000);
  window.setInterval(() => {
    if (!document.hidden) loadCollectionJobs({ silent: true });
  }, 5000);
}

async function loadWorkbenchSession() {
  try {
    const session = await api("/api/v2/auth/session");
    $("#adminEntry").hidden = session.auth_enabled && session.role !== "admin";
  } catch {
    $("#adminEntry").hidden = true;
  }
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
    renderAgentResult(resultHost, payload);
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
  $("#logoutWorkbench").addEventListener("click", async () => {
    await api("/api/v2/auth/logout", { method: "POST" });
    window.location.assign("/login");
  });
  $("#startForm").addEventListener("submit", startProject);
  $("#collectForm").addEventListener("submit", collectLinks);
  $("#crawlForm").addEventListener("submit", crawlTikTok);
  $("#saveAutoCrawl").addEventListener("click", saveAutoCollector);
  $("#stopAutoCrawl").addEventListener("click", stopAutoCollector);
  $("#refreshCollectionJobs").addEventListener("click", () => loadCollectionJobs());
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
  $("#runIndependentAgent").addEventListener("click", runIndependentAgent);
  $("#independentAgentAction").addEventListener("change", updateIndependentAgentUI);
  document.querySelectorAll("[data-run-standalone]").forEach((button) => {
    button.addEventListener("click", () => runStandaloneLauncher(button));
  });
  $("#navToggle")?.addEventListener("click", () => {
    document.body.classList.toggle("navOpen");
    const open = document.body.classList.contains("navOpen");
    $("#navToggle").setAttribute("aria-expanded", open ? "true" : "false");
  });
  $("#refreshTaskCenter")?.addEventListener("click", () => refreshProjects({ force: true }));
  $("#refreshDeliveryCenter")?.addEventListener("click", () => refreshProjects({ force: true }));
  document.addEventListener("click", (event) => {
    const button = event.target.closest(".promoteStandalone");
    if (button) promoteStandaloneArtifact(button);
  });
  $("#continueProject").addEventListener("click", continueCurrentProject);
  window.addEventListener("hashchange", () => {
    const view = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("view");
    if (views[view]) showView(view, { updateUrl: false });
  });
  updateCrawlTargetUI();
  updateIndependentAgentUI();
  updateRuntimeModeHint();
}

async function runStandaloneLauncher(button) {
  const launcher = button.closest("[data-standalone-action]");
  const action = launcher.dataset.standaloneAction;
  const prompt = launcher.querySelector("[data-standalone-prompt]").value.trim();
  const resultHost = launcher.querySelector("[data-standalone-result]");
  if (!prompt) {
    toast("请先输入本功能的需求或 Prompt", "error");
    launcher.querySelector("[data-standalone-prompt]").focus();
    return;
  }
  button.disabled = true;
  resultHost.className = "nodeResult";
  resultHost.textContent = "正在调用真实 Agent，请稍候...";
  beginOperation(`正在独立运行${stageLabel(action)}`, action === "production" ? 90 : 35);
  try {
    const payload = await api("/api/v2/agents/run", {
      method: "POST",
      body: JSON.stringify({
        action,
        product_id: $("#productSelect").value || "便携恒温杯",
        prompt,
        source_text: prompt,
        provider: "auto",
        mock: $("#runtimeMode").value !== "real",
        ...creativeRequestFields(),
      }),
    });
    renderAgentResult(resultHost, payload);
    toast(`${stageLabel(action)}已独立运行完成`);
  } catch (error) {
    resultHost.className = "nodeResult error";
    resultHost.textContent = error.message;
    toast(error.message, "error");
  } finally {
    button.disabled = false;
    endOperation();
  }
}

function updateIndependentAgentUI() {
  const action = $("#independentAgentAction").value;
  const contract = state.agentContracts[action] || {};
  const targetLabel = $("#independentTargetLabel");
  targetLabel.hidden = action !== "collector";
  $("#independentAgentPrompt").placeholder = independentActionHints[action] || "输入需求";
  $("#independentAgentState").textContent = independentActionHints[action] || "";
  const contractHost = $("#independentAgentContract");
  if (contract.identity) {
    contractHost.hidden = false;
    contractHost.innerHTML = `<div class="agentIdentity"><span>当前 Agent</span><strong>${escapeHtml(contract.identity)}</strong><p>${escapeHtml(contract.mission || "")}</p></div>
      <details class="agentContractDetails"><summary>查看能力与质量标准</summary>
        <div><span>核心专长</span><ul>${(contract.expertise || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>
        <div><span>工作方法</span><ul>${(contract.method || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>
        <div><span>交付自检</span><ul>${(contract.quality_gates || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>
      </details>`;
  } else {
    contractHost.hidden = true;
    contractHost.innerHTML = "";
  }
  if (name === "research_brief") {
    return renderNamedLists(artifact, { audience_insights: "受众洞察", viral_patterns: "传播结构", content_risks: "内容风险", pacing_notes: "节奏建议" });
  }
  if (name === "strategy_brief") {
    return renderNamedLists(artifact, { content_direction: "内容方向", hook_options: "钩子方案", cta_options: "行动号召", selling_point_priority: "卖点优先级", target_audience: "目标受众" });
  }
  if (name === "script_breakdown") {
    const beats = Array.isArray(artifact.beats) ? artifact.beats : [];
    return `<div class="agentResultCards">${beats.map((beat, index) => `<article class="agentResultCard"><strong>${escapeHtml(beat.role || `段落 ${index + 1}`)}</strong><p>${escapeHtml(beat.intent_zh || beat.intent || beat.summary || "")}</p><small>${escapeHtml(beat.visual_zh || beat.visual || beat.action_zh || "")}</small></article>`).join("") || "<p>暂无拆解结果。</p>"}</div>`;
  }
  if (name === "asset_manifest") {
    const frames = Array.isArray(artifact.hero_frames) ? artifact.hero_frames : [];
    return `<div class="agentResultCards">${frames.map((frame) => `<article class="agentResultCard"><strong>镜头 ${escapeHtml(frame.number || "-")} 素材</strong><p>${escapeHtml(frame.reference_reason || frame.status || "已匹配")}</p></article>`).join("") || "<p>暂无素材匹配结果。</p>"}</div>`;
  }
  if (name === "shot_report") {
    const shots = Array.isArray(artifact.shots) ? artifact.shots : [];
    return `<div class="agentResultCards">${shots.map((shot) => `<article class="agentResultCard"><strong>镜头 ${escapeHtml(shot.number || "-")}</strong><p>${escapeHtml(takeStatusLabel(shot.status))}</p><small>${escapeHtml(shot.path || "")}</small></article>`).join("") || "<p>暂无镜头结果。</p>"}</div>`;
  }
}

function renderNamedLists(artifact, fields) {
  return `<div class="agentResultStack">${Object.entries(fields).map(([key, label]) => {
    const value = artifact[key];
    const items = Array.isArray(value) ? value : value && typeof value === "object" ? Object.values(value) : [value];
    return `<section><strong>${label}</strong><ul>${items.filter(Boolean).map((item) => `<li>${escapeHtml(typeof item === "string" ? item : JSON.stringify(item))}</li>`).join("") || "<li>暂无内容</li>"}</ul></section>`;
  }).join("")}</div>`;
}

function takeStatusLabel(status) {
  return {
    needs_review: "待单镜质检", qa_pass: "质检通过，待选用", selected: "已选用",
    rejected: "已拒绝，等待重做", succeeded: "生成成功", failed: "生成失败",
  }[String(status || "")] || stageLabel(status);
}

function safeTakeNote(take) {
  if (take?.qa?.note_corrupted) return "历史质检备注编码损坏，请重新执行本镜质检并填写中文备注。";
  const note = String(take?.qa?.notes || "").trim();
  if (note && (note.match(/\?/g) || []).length >= Math.max(4, Math.floor(note.length * 0.35))) {
    return "历史质检备注编码损坏，请重新执行本镜质检并填写中文备注。";
  }
  return note;
}

async function runIndependentAgent() {
  const action = $("#independentAgentAction").value;
  const resultHost = $("#independentAgentResult");
  const target = $("#independentAgentTarget").value.trim();
  if (action === "collector" && !target) {
    toast("请输入关键词或账号主页 URL", "error");
    $("#independentAgentTarget").focus();
    return;
  }
  const button = $("#runIndependentAgent");
  button.disabled = true;
  beginOperation(`正在独立运行${stageLabel(action)}`, action === "production" ? 90 : 35);
  try {
    const payload = await api("/api/v2/agents/run", {
      method: "POST",
      body: JSON.stringify({
        action,
        product_id: $("#productSelect").value || "便携恒温杯",
        prompt: $("#independentAgentPrompt").value.trim() || null,
        source_text: $("#independentAgentPrompt").value.trim() || null,
        target,
        target_type: "keyword",
        provider: "auto",
        mock: $("#runtimeMode").value !== "real",
        ...creativeRequestFields(),
      }),
    });
    renderAgentResult(resultHost, payload);
    toast(`${action} 已独立运行完成`);
    await loadMaterials();
  } catch (error) {
    resultHost.className = "nodeResult error";
    resultHost.textContent = error.message;
    toast(error.message, "error");
  } finally {
    button.disabled = false;
    endOperation();
  }
}

async function promoteStandaloneArtifact(button) {
  button.disabled = true;
  beginOperation("正在创建生产项目", 20);
  try {
    const payload = await api("/api/v2/agents/promote", {
      method: "POST",
      body: JSON.stringify({
        source_project_id: button.dataset.projectId,
        artifact_name: button.dataset.artifactName,
        product_id: $("#productSelect").value || "便携恒温杯",
        mock: $("#runtimeMode").value !== "real",
      }),
    });
    await refreshProjects({ silent: true });
    await loadSelectedProject(payload.project_id);
    showView(viewForStage(payload.project.current_stage || payload.engine.stage));
    toast("生产项目已创建，已保留后续人工闸门");
  } catch (error) {
    toast(error.message, "error");
    button.disabled = false;
  } finally {
    endOperation();
  }
}

function updateRuntimeModeHint() {
  const real = $("#runtimeMode").value === "real";
  $("#runtimeModeHint").textContent = real
    ? "真实调用采集、分析和视频模型，会产生实际耗时与费用；缺少密钥时系统会拒绝创建。"
    : "用于完整流程演练：生成带演练标记的可播放 720P 成片，不调用外部模型。";
  renderStoryboardNode();
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
  const next = views[view] ? view : DEFAULT_VIEW;
  const meta = views[next];
  state.currentView = next;
  const visible = new Set(meta.sections);
  document.querySelectorAll("[data-section]").forEach((section) => {
    section.hidden = !visible.has(section.dataset.section);
  });
  renderNav();
  $("#viewStep").textContent = "";
  $("#viewTitle").textContent = meta.title;
  $("#viewDescription").textContent = meta.description;
  if (updateUrl) history.replaceState(null, "", `#view=${next}`);
  if (meta.tool) presetToolAction(meta.tool);
  renderPanels();
  if (meta.sections.some((section) => MATERIAL_VIEW_SECTIONS.has(section))) loadMaterials();
  document.body.classList.remove("navOpen");
  $("#navToggle")?.setAttribute("aria-expanded", "false");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderNav() {
  const host = $("#appNav");
  if (!host) return;
  const current = state.currentView;
  const activeGroup = views[current]?.group || "home";
  host.innerHTML = NAV.map((group) => {
    const isActive = group.key === activeGroup;
    const hasItems = group.views.length > 1;
    const items = isActive && hasItems
      ? `<div class="navGroupItems">${group.views.map((view) => `
          <button type="button" data-nav-view="${view}" class="navItem ${view === current ? "active" : ""}" aria-current="${view === current ? "page" : "false"}">${views[view].label}</button>`).join("")}</div>`
      : "";
    return `
      <div class="navGroup ${isActive ? "open" : ""}">
        <button type="button" data-nav-group="${group.key}" class="navGroupHead ${isActive ? "active" : ""}">
          <i data-lucide="${group.icon}"></i><strong>${group.label}</strong>
        </button>
        ${items}
      </div>`;
  }).join("");
  host.querySelectorAll("[data-nav-group]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = NAV.find((entry) => entry.key === button.dataset.navGroup);
      if (target) showView(target.views[0]);
    });
  });
  host.querySelectorAll("[data-nav-view]").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.navView));
  });
  window.lucide?.createIcons({ attrs: { "stroke-width": 1.8 } });
}

function presetToolAction(action) {
  const select = $("#independentAgentAction");
  if (!select) return;
  if ([...select.options].some((option) => option.value === action)) {
    select.value = action;
    updateIndependentAgentUI();
  }
}

function viewForStage(stage) {
  if (["analysis", "research", "strategy", "script", "script_breakdown", "script_review", "script_gate"].includes(stage)) return "proj_script";
  if (["storyboard", "asset", "hero_gate"].includes(stage)) return "proj_storyboard";
  if (["production", "take_gate", "compose", "final_qa"].includes(stage)) return "proj_production";
  if (["archive", "succeeded"].includes(stage)) return "proj_archive";
  return "proj_overview";
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
    const runtime = await api("/api/v2/runtime");
    state.runtime = runtime;
    const backendHost = $("#collectorBackendState");
    if (backendHost) {
      const backends = runtime.collector_backends || [];
      backendHost.innerHTML = backends.map((backend) => `
        <span class="${backend.ready ? "ready" : "missing"}">${escapeHtml(backend.id)} · ${backend.ready ? "可用" : "未配置"}</span>
      `).join("");
    }
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

function severityLabel(severity) {
  return { BLOCKED: "⛔ 阻断", WARNING: "⚠ 提醒", INFO: "提示" }[String(severity || "").toUpperCase()] || String(severity || "提示");
}

function renderProductItem(product) {
  const issues = product.issues || [];
  const counts = formatCounts(product.counts || {});
  const blockers = issues.filter((issue) => issue.severity === "BLOCKED").length;
  const status = product.ready ? "可生产" : `${blockers || issues.length} 项阻塞`;
  const issueText = issues.length
    ? issues.map((issue) => `${severityLabel(issue.severity)}：${issue.message}`).join(" · ")
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

function severityLabel(severity) {
  return ({ BLOCKED: "阻断", WARNING: "提醒", INFO: "信息" })[severity] || "提示";
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
  beginOperation("正在创建后台采集任务", 5);
  $("#crawlState").textContent = "正在创建任务";
  try {
    const payload = await api("/api/v2/collect/jobs", {
      method: "POST",
      body: JSON.stringify({
        target_type: targetType,
        provider: $("#crawlProvider").value,
        target,
        requested_count: Number($("#crawlLimit").value || 6),
        product_id: $("#productSelect").value,
        mock: $("#runtimeMode").value !== "real",
      }),
    });
    state.selectedCollectionJobId = payload.job.id;
    toast(`采集任务 #${payload.job.id} 已进入后台队列`);
    await loadCollectionJobs();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
    $("#crawlState").textContent = "";
    endOperation();
  }
}

const collectionStatusLabels = {
  queued: "排队中",
  running: "采集中",
  paused: "已暂停",
  succeeded: "已完成",
  partial: "部分完成",
  failed: "失败",
  cancelled: "已取消",
  discovered: "已发现",
  filtered: "已过滤",
  downloading: "下载中",
  downloaded: "已下载",
  transcribing: "转写中",
  analyzing: "分析中",
  ready: "可用",
};

function collectionStatusLabel(value) {
  return collectionStatusLabels[String(value || "")] || String(value || "未知");
}

async function loadCollectionJobs({ silent = false } = {}) {
  try {
    const payload = await api("/api/v2/collect/jobs?limit=12");
    state.collectionJobs = payload.jobs || [];
    renderCollectionJobs();
    if (state.selectedCollectionJobId) await loadCollectionJobDetail(state.selectedCollectionJobId);
  } catch (error) {
    if (!silent) toast(`无法读取采集任务：${error.message}`, "error");
  }
}

function renderCollectionJobs() {
  const host = $("#collectionJobList");
  if (!state.collectionJobs.length) {
    host.className = "collectionJobList emptyState";
    host.textContent = "暂无采集任务。输入关键词后点击“立即抓取并分析”即可创建。";
    return;
  }
  host.className = "collectionJobList";
  host.innerHTML = state.collectionJobs.map((job) => {
    const progress = job.progress || {};
    const requested = Number(progress.requested || job.requested_count || 0);
    const analyzed = Number(progress.analyzed || 0);
    const percent = requested ? Math.min(100, Math.round(analyzed / requested * 100)) : 0;
    return `<article class="collectionJobCard ${job.id === state.selectedCollectionJobId ? "active" : ""}">
      <button type="button" class="collectionJobOpen" data-collection-job="${job.id}" aria-label="查看采集任务 ${job.id}">
        <span><strong>${escapeHtml(job.target || "热门视频")}</strong><small>#${job.id} · ${escapeHtml(collectionStatusLabel(job.status))}</small></span>
        <span class="collectionJobNumbers">相关 ${Number(progress.relevant || 0)} · 已分析 ${analyzed}/${requested} · 失败 ${Number(progress.failed || 0)}</span>
        <span class="collectionProgress"><i style="width:${percent}%"></i></span>
      </button>
      ${["queued", "paused"].includes(job.status) ? `<button type="button" class="collectionCancel" data-cancel-job="${job.id}">取消</button>` : ""}
    </article>`;
  }).join("");
  host.querySelectorAll("[data-collection-job]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedCollectionJobId = Number(button.dataset.collectionJob);
      renderCollectionJobs();
      await loadCollectionJobDetail(state.selectedCollectionJobId);
    });
  });
  host.querySelectorAll("[data-cancel-job]").forEach((button) => {
    button.addEventListener("click", () => cancelCollectionJob(Number(button.dataset.cancelJob)));
  });
}

async function loadCollectionJobDetail(jobId) {
  const host = $("#collectionJobDetail");
  try {
    const payload = await api(`/api/v2/collect/jobs/${jobId}`);
    const items = payload.items || [];
    host.hidden = false;
    host.innerHTML = `<div class="collectionDetailHead"><strong>任务 #${jobId} 素材明细</strong><span>${items.length} 条候选</span></div>
      ${items.length ? `<div class="collectionItems">${items.map((item) => `<article>
        ${item.cover_url ? `<img src="${escapeAttr(item.cover_url)}" alt="" loading="lazy" />` : `<span class="collectionCoverPlaceholder">无封面</span>`}
        <div><strong>${escapeHtml(item.title || "未命名 TikTok 素材")}</strong><small>${escapeHtml(item.author_name || "未知作者")} · 相关度 ${Math.round(Number(item.relevance_score || 0) * 100)}%</small><a href="${escapeAttr(item.source_url)}" target="_blank" rel="noopener">查看来源</a></div>
        <span class="collectionItemStatus ${statusClass(item.status)}">${escapeHtml(collectionStatusLabel(item.status))}</span>
        ${item.error_message ? `<p>${escapeHtml(item.error_message)}</p>` : ""}
      </article>`).join("")}</div>` : `<div class="emptyState">任务已创建，等待发现候选素材。</div>`}`;
  } catch (error) {
    host.hidden = false;
    host.innerHTML = `<div class="emptyState">无法读取任务详情：${escapeHtml(error.message)}</div>`;
  }
}

async function cancelCollectionJob(jobId) {
  try {
    await api(`/api/v2/collect/jobs/${jobId}/cancel`, { method: "POST" });
    toast(`采集任务 #${jobId} 已取消`);
    await loadCollectionJobs();
  } catch (error) {
    toast(error.message, "error");
  }
}

function autoCollectorPayload(enabled) {
  return {
    enabled,
    target_type: $("#crawlTargetType").value,
    provider: $("#crawlProvider").value,
    target: $("#crawlTarget").value.trim(),
    limit: Number($("#crawlLimit").value || 3),
    interval_minutes: Number($("#autoCrawlInterval").value || 60),
    product_id: $("#productSelect").value,
    mock: $("#runtimeMode").value !== "real",
  };
}

function renderAutoCollector(settings) {
  const host = $("#autoCrawlStatus");
  const startButton = $("#saveAutoCrawl");
  const stopButton = $("#stopAutoCrawl");
  startButton.textContent = settings.enabled ? "更新后台自动采集" : "启动后台自动采集";
  stopButton.hidden = !settings.enabled;
  if (!settings.enabled) {
    host.className = "autoCrawlStatus";
    host.textContent = "后台自动采集未启动。填写目标后点击“启动后台自动采集”，服务器将按设定频率持续运行。";
    return;
  }
  const mode = settings.mock ? "演练模式" : "真实运行";
  const last = settings.last_message ? `最近结果：${settings.last_message}` : "等待首轮执行";
  const retry = settings.next_run_at
    ? `连续失败 ${settings.failure_count || 0} 次；下次重试：${new Date(settings.next_run_at).toLocaleString("zh-CN", { hour12: false })}。`
    : "";
  host.className = `autoCrawlStatus ${settings.status === "failed" ? "error" : "active"}`;
  host.textContent = `后台自动采集已启动：每 ${settings.interval_minutes} 分钟，${mode}。${last}${retry}`;
}

async function loadAutoCollector() {
  try {
    const settings = await api("/api/v2/collect/tiktok/auto");
    $("#crawlTargetType").value = settings.target_type;
    $("#crawlProvider").value = settings.provider;
    $("#crawlTarget").value = settings.target || "";
    $("#crawlLimit").value = settings.limit;
    $("#autoCrawlInterval").value = String(settings.interval_minutes);
    updateCrawlTargetUI();
    renderAutoCollector(settings);
  } catch (error) {
    $("#autoCrawlStatus").className = "autoCrawlStatus error";
    $("#autoCrawlStatus").textContent = `无法读取后台采集状态：${error.message}`;
  }
}

async function saveAutoCollector(event) {
  const button = event.currentTarget;
  const targetType = $("#crawlTargetType").value;
  if (targetType !== "trending" && !$("#crawlTarget").value.trim()) {
    toast("请先填写自动采集目标", "error");
    $("#crawlTarget").focus();
    return;
  }
  button.disabled = true;
  $("#crawlState").textContent = "正在保存后台任务";
  try {
    const settings = await api("/api/v2/collect/tiktok/auto", {
      method: "PUT",
      body: JSON.stringify(autoCollectorPayload(true)),
    });
    renderAutoCollector(settings);
    toast("后台自动采集已启动，服务器将持续发现并分析素材");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
    $("#crawlState").textContent = "";
  }
}

async function stopAutoCollector(event) {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const settings = await api("/api/v2/collect/tiktok/auto", {
      method: "PUT",
      body: JSON.stringify(autoCollectorPayload(false)),
    });
    renderAutoCollector(settings);
    toast("后台自动采集已停止，已入库素材不受影响");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
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

async function refreshProjects({ silent = false, force = false } = {}) {
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
    const summary = state.projects.find((item) => item.project_id === state.selectedId);
    const revision = projectRevision(summary);
    if (state.selectedId && !(silent && activeEditor) && (force || !silent || revision !== state.selectedRevision)) {
      await loadSelectedProject(state.selectedId);
    } else if (!state.selectedId) {
      renderPanels();
    }
    if (views[state.currentView]?.group === "materials" && !(silent && activeEditor)) await loadMaterials();
  } catch (error) {
    if (!silent) toast(error.message, "error");
  } finally {
    state.refreshing = false;
  }
}

function projectRevision(project) {
  if (!project) return "";
  return JSON.stringify([
    project.status, project.current_stage, project.current_gate, project.updated_at,
    project.artifacts, (project.tasks || []).map((task) => [task.id, task.status, task.updated_at]),
  ]);
}

function renderMaterialLibrary() {
  const host = $("#materialLibrary");
  if (!state.materials.length) {
    host.className = "emptyState";
    host.textContent = "暂无人工导入素材";
    return;
  }
  host.className = "materialLibraryView";
  host.innerHTML = `<div class="materialFilters">
      <input id="materialSearch" type="search" placeholder="搜索标题、作者或关键词" aria-label="搜索素材" />
      <select id="materialReadiness" aria-label="筛选素材状态"><option value="all">全部素材</option><option value="ready">可生产</option><option value="cleanup">待清洗</option></select>
      <span id="materialCount"></span>
    </div><div class="materialList" id="materialListInner"></div>`;
  const draw = () => {
    const query = $("#materialSearch").value.trim().toLowerCase();
    const readiness = $("#materialReadiness").value;
    const filtered = state.materials.filter((item) => {
      const meta = item.material_meta || {};
      const searchable = [meta.video_title, meta.caption, meta.author_name, meta.source_keyword].join(" ").toLowerCase();
      const ready = Boolean(meta.production_readiness?.ready);
      return (!query || searchable.includes(query)) && (readiness === "all" || (readiness === "ready" ? ready : !ready));
    });
    $("#materialCount").textContent = `${filtered.length} / ${state.materials.length} 条`;
    $("#materialListInner").innerHTML = filtered.map(renderMaterialItem).join("") || '<div class="emptyState">没有符合条件的素材</div>';
    bindMaterialActions($("#materialListInner"));
  };
  $("#materialSearch").addEventListener("input", draw);
  $("#materialReadiness").addEventListener("change", draw);
  draw();
}

function bindMaterialActions(host) {
  host.querySelectorAll("[data-start-material]").forEach((button) => {
    button.addEventListener("click", () => startFromMaterial(button.dataset.startMaterial));
  });
  host.querySelectorAll("[data-material-detail]").forEach((button) => {
    button.addEventListener("click", () => showMaterialDetail(button.dataset.materialDetail));
  });
}

function renderMaterialItem(item) {
  const meta = item.material_meta || {};
  const title = meta.video_title || meta.caption || meta.source_url || "未命名 TikTok 素材";
  const caption = meta.caption || "未取得视频简介";
  const analysis = materialAnalysisSummary(meta);
  const readiness = meta.production_readiness || {};
  const ready = Boolean(readiness.ready);
  const sourceUrl = meta.source_url || meta.video_url || "";
  const videoName = String(meta.local_video_path || "").split(/[\\/]/).pop();
  const localVideo = videoName
    ? `/api/v2/collect/materials/${encodeURIComponent(item.material_id)}/file/${encodeURIComponent(videoName)}`
    : "";
  const localCover = meta.local_cover_path
    ? `/api/v2/collect/materials/${encodeURIComponent(item.material_id)}/file/${encodeURIComponent(String(meta.local_cover_path).split(/[\\/]/).pop())}`
    : "";
  const cover = localCover || meta.cover_url
    ? `<img class="materialCover" src="${escapeAttr(localCover || meta.cover_url)}" alt="${escapeAttr(title)} 封面" loading="lazy" />`
    : `<div class="materialCover placeholder">无封面</div>`;
  return `
    <article class="materialItem">
      ${cover}
      <div class="materialBody">
        <strong>${escapeHtml(title)}</strong>
        <span>${escapeHtml(meta.author_name || "未知创作者")} · ${escapeHtml(meta.source_keyword || "manual_tiktok")} · ${escapeHtml(materialStatusLabel(meta.processing_status || item.status))}</span>
        <span class="materialReadiness ${ready ? "ready" : "cleanup"}">${ready ? "可生产" : "待清洗"}${Number.isFinite(Number(readiness.relevance_score)) ? ` · 相关度 ${Math.round(Number(readiness.relevance_score) * 100)}%` : ""}</span>
        <p>${escapeHtml(caption)}</p>
        <p class="materialAnalysis">${escapeHtml(analysis)}</p>
        ${sourceUrl ? `<a href="${escapeAttr(sourceUrl)}" target="_blank" rel="noopener">打开 TikTok 来源</a>` : ""}
        <div class="materialActions">
          <button type="button" data-material-detail="${escapeAttr(item.material_id)}">查看转写与拆解</button>
          ${localVideo ? `<a class="buttonLink" href="${escapeAttr(localVideo)}" download>下载原视频</a>` : ""}
        </div>
      </div>
      <button type="button" data-start-material="${escapeAttr(item.material_id)}" ${ready ? "" : "disabled"} title="${ready ? "使用该素材创建生产项目" : escapeAttr((readiness.missing || []).join("、") || "素材尚未完成下载、转写与分析")}">${ready ? "发起项目" : "补齐后可生产"}</button>
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

function materialStatusLabel(value) {
  return {
    raw: "已入库，待处理",
    metadata_only: "仅元数据",
    captured: "已下载，待分析",
    analyzed: "已完成分析",
  }[String(value || "")] || String(value || "待处理");
}

function materialDetailHtml(meta) {
  let analysis = {};
  try {
    analysis = JSON.parse(meta.ai_analysis_json || "{}").analysis || {};
  } catch {
    analysis = {};
  }
  const breakdown = Array.isArray(analysis.shot_breakdown) ? analysis.shot_breakdown : [];
  const keyframes = Array.isArray(analysis.keyframes) ? analysis.keyframes : [];
  const transcript = String(meta.transcript_text || "").trim();
  const files = Array.isArray(meta.files) ? meta.files : [];
  const video = files.find((file) => /(^|\/)source\.(mp4|mov|webm|mkv)$/i.test(String(file.path || "")));
  const frameFiles = files.filter((file) => /(^|\/)frames\/.*\.(jpg|jpeg|png)$/i.test(String(file.path || "")));
  return `
    <div class="materialDetailGrid">
      <section><h4>采集状态</h4><p>${escapeHtml(materialStatusLabel(meta.processing_status))}</p><p>${transcript ? "转写已就绪" : "未取得字幕或转写，请补充文本后再运行分析"}</p></section>
      <section><h4>视频转写</h4>
        <textarea class="materialTranscriptInput" placeholder="粘贴或修订视频转写，用于研究分析和脚本拆解">${escapeHtml(transcript)}</textarea>
        <div class="materialActions"><button type="button" class="saveMaterialTranscript" data-material-id="${escapeAttr(meta.material_id)}">保存转写并重新分析</button></div>
      </section>
      <section><h4>结构与镜头拆解</h4>
        <p>${escapeHtml(analysis.hook_3s ? `3 秒钩子：${analysis.hook_3s}` : "尚未生成结构分析")}</p>
        ${breakdown.length ? `<ol>${breakdown.map((shot) => `<li>${escapeHtml(typeof shot === "string" ? shot : shot.description || shot.action || JSON.stringify(shot))}</li>`).join("")}</ol>` : "<p>尚未生成逐镜拆解</p>"}
        ${keyframes.length ? `<p>关键帧：${escapeHtml(keyframes.map((frame) => typeof frame === "string" ? frame : frame.description || frame.time || "关键帧").join("；"))}</p>` : ""}
      </section>
      <section><h4>本地文件</h4>
        ${video ? `<a class="buttonLink" href="${escapeAttr(video.download_url)}" download>下载原视频</a>` : "<p>未下载本地原视频</p>"}
        ${frameFiles.length ? `<div class="materialFrames">${frameFiles.map((file) => `<a href="${escapeAttr(file.download_url)}" target="_blank" rel="noopener"><img src="${escapeAttr(file.download_url)}" alt="视频抽帧" loading="lazy"></a>`).join("")}</div>` : ""}
      </section>
    </div>`;
}

async function showMaterialDetail(materialId) {
  try {
    const meta = await api(`/api/v2/collect/materials/${encodeURIComponent(materialId)}`);
    const host = $("#materialLibrary");
    host.querySelector(".materialDetailPanel")?.remove();
    const panel = document.createElement("section");
    panel.className = "materialDetailPanel";
    panel.innerHTML = `<div class="resultHead"><strong>素材详情</strong><button type="button" class="closeMaterialDetail">关闭</button></div>${materialDetailHtml(meta)}`;
    panel.querySelector(".closeMaterialDetail").addEventListener("click", () => panel.remove());
    panel.querySelector(".saveMaterialTranscript").addEventListener("click", () => saveMaterialTranscript(panel, materialId));
    host.prepend(panel);
  } catch (error) {
    toast(error.message, "error");
  }
}

async function saveMaterialTranscript(panel, materialId) {
  const button = panel.querySelector(".saveMaterialTranscript");
  const transcript = panel.querySelector(".materialTranscriptInput").value.trim();
  if (!transcript) {
    toast("请先填写视频转写", "error");
    return;
  }
  button.disabled = true;
  beginOperation("正在保存转写并启动研究分析", 35);
  try {
    await api(`/api/v2/collect/materials/${encodeURIComponent(materialId)}/transcript`, {
      method: "PUT",
      body: JSON.stringify({ transcript_text: transcript }),
    });
    toast("转写已保存，正在创建分析项目");
    await startFromMaterial(materialId);
    await loadMaterials();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
    endOperation();
  }
}

async function loadSelectedProject(projectId) {
  state.selected = await api(`/api/v2/pipeline/${encodeURIComponent(projectId)}`);
  state.selectedRevision = projectRevision(state.selected);
  state.scriptCopy = null;
  state.scriptBreakdown = null;
  state.reviewReport = null;
  state.shotPlan = null;
  state.assetManifest = null;
  state.takeManifest = null;
  state.renderReport = null;
  state.runReport = null;

  [state.scriptCopy, state.scriptBreakdown, state.reviewReport, state.shotPlan,
    state.assetManifest, state.takeManifest, state.renderReport, state.runReport] = await Promise.all([
    safeArtifact(projectId, "script_copy"), safeArtifact(projectId, "script_breakdown"),
    safeArtifact(projectId, "review_report"), safeArtifact(projectId, "shot_plan"),
    safeArtifact(projectId, "asset_manifest"), safeArtifact(projectId, "take_manifest"),
    safeArtifact(projectId, "render_report"), safeRunReport(projectId),
  ]);
  renderPanels();
}

async function safeArtifact(projectId, artifactName) {
  if (!state.selected?.artifacts?.[artifactName]) return null;
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
  const total = nodes.length;
  const completed = nodes.filter((node) => node.status === "succeeded").length;
  const current = nodes.find((node) => ["running", "awaiting_human", "failed", "blocked"].includes(node.status));
  const status = current?.status || (completed === total ? "succeeded" : "idle");
  const label = current ? agentLabels[current.agent] || current.agent : completed === total ? "全部完成" : "等待开始";
  return `<div class="nodeSummary ${statusClass(status)}" title="${escapeAttr(nodes.map((node) => `${agentLabels[node.agent] || node.agent}：${stageLabel(node.status)}`).join("；"))}">${completed}/${total} 已完成 · ${statusGlyph[status] || "○"} ${escapeHtml(label)}</div>`;
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
          <summary>${escapeHtml(stageLabel(task.stage))}${shot ? ` · 镜头 ${shot}` : ""}失败：${escapeHtml(explainTaskError(task.error_json))}</summary>
          <pre>${escapeHtml(JSON.stringify(task.error_json, null, 2))}</pre>
          ${retry}
        </details>
      `;
    })
    .join("");
}

function explainTaskError(error) {
  const message = String(error?.message || error?.detail || "任务执行失败");
  if (/DOUBAO_API_KEY|SEEDANCE_API_KEY|not configured|missing/i.test(message)) return "缺少模型密钥或模型未配置";
  if (/timeout|timed out/i.test(message)) return "调用超时，可重试";
  if (/quota|balance|insufficient/i.test(message)) return "模型余额或配额不足";
  return message;
}

function renderPanels() {
  const stage = state.selected?.current_stage || state.selected?.status;
  const label = state.selected
    ? `${state.selected.project_id} · ${stageLabels[stage] || stage}`
    : "未选择项目";
  $("#activeProject").textContent = label;
  const continueButton = $("#continueProject");
  continueButton.disabled = !state.selected;
  $("#currentStage").textContent = state.selected
    ? `当前节点：${stageLabels[stage] || stage}`
    : "暂无在制项目";
  const sections = new Set(views[state.currentView]?.sections || []);
  if (sections.has("scriptGate")) renderScriptGate();
  if (sections.has("storyboardNode")) renderStoryboardNode();
  if (sections.has("heroGate")) renderHeroGate();
  if (sections.has("productionNode")) renderProductionNode();
  if (sections.has("composeNode")) renderComposeNode();
  if (sections.has("deliveryNode")) renderDelivery();
  if (sections.has("projectQueue")) renderProjectRows();
  if (sections.has("homeDashboard")) renderHome();
  if (sections.has("taskCenter")) renderTaskCenter();
  if (sections.has("deliveryCenter")) renderDeliveryCenter();
  if (sections.has("favoritesSection")) renderFavorites();
  installCommandIcons();
}

function projectStageLabel(project) {
  return stageLabel(project.current_gate || project.current_stage || project.status);
}

function renderHome() {
  const host = $("#homeDashboard");
  if (!host) return;
  const projects = state.projects || [];
  const active = projects.filter((project) => !["succeeded", "failed", "cancelled"].includes(project.status));
  const awaiting = projects.filter((project) => project.status === "awaiting_human" || project.current_gate);
  const delivered = projects.filter((project) => project.status === "succeeded");
  const recent = delivered.slice(0, 5);
  const resume = state.selected || active[0] || null;
  $("#homeState").textContent = projects.length ? `${projects.length} 个项目 · ${active.length} 在制` : "";
  host.className = "homeGrid";
  host.innerHTML = `
    <button type="button" class="homeCard" data-home="resume">
      <span class="homeCardIcon"><i data-lucide="arrow-right"></i></span>
      <strong>继续上次任务</strong>
      <small>${resume ? `${escapeHtml(resume.project_id)} · ${escapeHtml(projectStageLabel(resume))}` : "暂无在制项目"}</small>
    </button>
    <button type="button" class="homeCard" data-home="new">
      <span class="homeCardIcon"><i data-lucide="plus"></i></span>
      <strong>新建视频项目</strong>
      <small>选择产品与运行模式，开始一条新的生产链路</small>
    </button>
    <button type="button" class="homeCard" data-home="tools">
      <span class="homeCardIcon"><i data-lucide="wand-sparkles"></i></span>
      <strong>使用快速工具</strong>
      <small>不建项目，直接运行研究、脚本、分镜或单镜生成</small>
    </button>
    <button type="button" class="homeCard" data-home="review">
      <span class="homeCardIcon"><i data-lucide="clipboard-check"></i></span>
      <strong>我的待审核</strong>
      <small>${awaiting.length ? `${awaiting.length} 项等待人工确认` : "暂无待审核项目"}</small>
    </button>
    <button type="button" class="homeCard" data-home="delivery">
      <span class="homeCardIcon"><i data-lucide="package-check"></i></span>
      <strong>最近交付</strong>
      <small>${delivered.length ? `${delivered.length} 个已交付，查看下载与报告` : "暂无已交付成片"}</small>
    </button>
    <div class="homeRecent">
      <strong>最近交付明细</strong>
      ${recent.length ? recent.map((project) => `
        <button type="button" class="homeRecentRow" data-open="${escapeAttr(project.project_id)}">
          <span>${escapeHtml(project.product_id || "未命名产品")}</span>
          <small>${escapeHtml(project.project_id)} · ${escapeHtml(formatProjectTime(project.updated_at))}</small>
        </button>`).join("") : '<small class="muted">完成一条成片后会显示在这里。</small>'}
    </div>
  `;
  host.querySelectorAll("[data-home]").forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.dataset.home;
      if (action === "resume") {
        if (resume) { state.selectedId = resume.project_id; refreshProjects().then(continueCurrentProject); }
        else showView("proj_overview");
      } else if (action === "new") showView("proj_overview");
      else if (action === "tools") showView("tool_research");
      else if (action === "review") showView("task_todo");
      else if (action === "delivery") showView("del_passed");
    });
  });
  host.querySelectorAll("[data-open]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedId = button.dataset.open;
      await refreshProjects();
      continueCurrentProject();
    });
  });
}

function taskCenterBuckets() {
  const projects = state.projects || [];
  return {
    running: projects.filter((project) => ["running", "queued"].includes(project.status)),
    todo: projects.filter((project) => project.status === "awaiting_human" || (project.current_gate && project.status !== "succeeded")),
    failed: projects.filter((project) => ["failed", "blocked"].includes(project.status)),
    done: projects.filter((project) => project.status === "succeeded"),
  };
}

function renderTaskCenter() {
  const host = $("#taskCenter");
  if (!host) return;
  const filter = views[state.currentView]?.taskFilter || "running";
  const buckets = taskCenterBuckets();
  const list = buckets[filter] || [];
  $("#taskCenterTitle").textContent = views[state.currentView]?.title || "任务中心";
  $("#taskCenterCount").textContent = `${list.length} 项`;
  if (!list.length) {
    host.className = "emptyState";
    host.textContent = "该分类暂无任务。";
    return;
  }
  host.className = "taskCenterList";
  host.innerHTML = list.map((project) => `
    <button type="button" class="taskCenterRow" data-open="${escapeAttr(project.project_id)}">
      <span class="stageTag ${statusClass(project.status)}">${escapeHtml(projectStageLabel(project))}</span>
      <span class="taskCenterMain">
        <strong>${escapeHtml(project.project_id)}</strong>
        <small>${escapeHtml(project.product_id || "")} · ${escapeHtml(formatProjectTime(project.updated_at))} · ¥${Number(project.cost.total_cost_cny || 0).toFixed(2)}</small>
      </span>
      <i data-lucide="chevron-right"></i>
    </button>`).join("");
  host.querySelectorAll("[data-open]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedId = button.dataset.open;
      await refreshProjects();
      continueCurrentProject();
    });
  });
  installCommandIcons();
}

function deliveryCenterBuckets() {
  const projects = state.projects || [];
  const succeeded = projects.filter((project) => project.status === "succeeded");
  return {
    pending: projects.filter((project) => project.current_gate === "take_gate" || project.current_stage === "final_qa" || project.current_stage === "compose"),
    passed: succeeded.filter((project) => project.delivery_ready),
    archived: succeeded,
    downloads: succeeded.filter((project) => project.delivery_ready),
  };
}

function renderDeliveryCenter() {
  const host = $("#deliveryCenter");
  if (!host) return;
  const filter = views[state.currentView]?.deliveryFilter || "pending";
  const list = deliveryCenterBuckets()[filter] || [];
  $("#deliveryCenterTitle").textContent = views[state.currentView]?.title || "交付中心";
  $("#deliveryCenterCount").textContent = `${list.length} 项`;
  if (!list.length) {
    host.className = "emptyState";
    host.textContent = "该分类暂无记录。";
    return;
  }
  host.className = "deliveryCenterList";
  const downloads = filter === "downloads";
  host.innerHTML = list.map((project) => `
    <div class="deliveryCenterRow">
      <button type="button" class="deliveryCenterOpen" data-open="${escapeAttr(project.project_id)}">
        <strong>${escapeHtml(project.product_id || "未命名产品")}</strong>
        <small>${escapeHtml(project.project_id)} · ${escapeHtml(formatProjectTime(project.updated_at))} · ${project.mock ? "演练" : "真实"}</small>
      </button>
      <div class="deliveryCenterActions">
        ${downloads
          ? `<a class="buttonLink" href="/api/v2/download/${encodeURIComponent(project.project_id)}">下载 zip</a>
             <a class="buttonLink" target="_blank" rel="noopener" href="/api/v2/reports/${encodeURIComponent(project.project_id)}">运行报告</a>`
          : `<span class="stageTag ${statusClass(project.status)}">${escapeHtml(projectStageLabel(project))}</span>`}
      </div>
    </div>`).join("");
  host.querySelectorAll("[data-open]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedId = button.dataset.open;
      await refreshProjects();
      showView("proj_archive");
    });
  });
}

function renderFavorites() {
  const host = $("#favoritesPanel");
  if (!host) return;
  const project = state.selected;
  if (!project) {
    host.className = "emptyState";
    host.textContent = "从项目列表打开一个项目后，这里汇总它选用的产品素材与参考素材。";
    return;
  }
  const assets = state.assetManifest?.assets || state.assetManifest?.items || [];
  host.className = "favoritesPanel";
  host.innerHTML = `
    <div class="favoritesHead"><strong>${escapeHtml(project.project_id)}</strong><small>${escapeHtml(project.product_id || "")}</small></div>
    <div class="favoritesBody">
      ${assets.length
        ? assets.map((asset) => `<span class="favoriteTag">${escapeHtml(asset.name || asset.title || asset.material_id || "素材")}</span>`).join("")
        : '<small class="muted">该项目暂无已选用的素材记录。</small>'}
    </div>`;
}

function renderScriptGate() {
  const host = $("#scriptEditor");
  $("#scriptGateState").textContent = state.selected?.current_gate === "script_gate" ? "待确认" : "";
  if (!state.selected || !state.scriptCopy) {
    host.className = "emptyState";
    host.innerHTML = renderPipelineProgress(state.selected, "脚本生成中，完成后可在此逐段编辑并确认。");
    return;
  }
  host.className = "editor";
  const comments = state.reviewReport?.comments || [];
  const scores = state.reviewReport?.scores || {};
  host.innerHTML = `
    ${renderCreativeQuality(state.scriptCopy.quality_assessment)}
    <div class="reviewStrip">
      <span>脚本审核：${escapeHtml(reviewStatusLabel(state.reviewReport?.status || "PASS"))}</span>
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
      <a class="buttonLink" href="/api/v2/artifacts/${encodeURIComponent(state.selectedId)}/script_copy/download">下载脚本 JSON</a>
      ${state.scriptBreakdown ? `<a class="buttonLink" href="/api/v2/artifacts/${encodeURIComponent(state.selectedId)}/script_breakdown/download">下载脚本拆解</a>` : ""}
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

function renderPipelineProgress(project, fallback) {
  if (!project) return `<span>${escapeHtml(fallback)}</span>`;
  const order = ["analysis", "research", "strategy", "script", "script_breakdown", "script_review", "script_gate"];
  const stages = project.stages || {};
  return `<div class="pipelineProgress"><strong>${escapeHtml(fallback)}</strong><div>${order.map((stage) => {
    const status = stages[stage]?.status || "idle";
    return `<span class="progressStep ${statusClass(status)}">${status === "succeeded" ? "✓" : status === "running" ? "◐" : status === "failed" ? "×" : "○"} ${escapeHtml(stageLabel(stage))}</span>`;
  }).join("")}</div><small>当前：${escapeHtml(stageLabel(project.current_stage || project.status))}</small></div>`;
}

function renderCreativeQuality(assessment) {
  if (!assessment) return "";
  const passed = assessment.status === "PASS";
  const issues = assessment.issues || [];
  return `<div class="creativeQuality ${passed ? "pass" : "needsRewrite"}">
    <div><span>创意质量自检</span><strong>${escapeHtml(String(assessment.score ?? 0))} 分 · ${passed ? "通过" : "需要修改"}</strong></div>
    <p>${issues.length ? escapeHtml(issues.join("；")) : "结构、连续性、产品事实与可执行性检查均已通过。"}</p>
  </div>`;
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
      body: JSON.stringify({ project_id: state.selectedId, gate: "script_gate", approver: "operator" }),
    });
    toast(`已进入 ${payload.engine.stage}`);
    await refreshProjects();
    showView("proj_storyboard");
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
  const realMode = $("#runtimeMode").value === "real";
  const doubaoReady = Boolean(state.runtime?.providers?.doubao?.configured);
  const modelState = realMode ? (doubaoReady ? "真实豆包分镜模型已配置" : "真实分镜不可用：缺少豆包模型密钥") : "演练模式";
  $("#storyboardNodeState").textContent = state.shotPlan
    ? `${state.shotPlan.shots.length} 镜 · 当前 ${currentDuration} 秒 · 目标 30 秒 · ${modelState}`
    : modelState;
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
    ${renderCreativeQuality(state.shotPlan.quality_assessment)}
    <div class="tableWrap">
      <table class="scriptTable storyboardTable">
        <thead><tr><th>#</th><th>画面</th><th>生成提示词</th><th>镜头时长（3-10 秒）</th></tr></thead>
        <tbody>${state.shotPlan.shots.map(renderShotRow).join("")}</tbody>
      </table>
    </div>
    <div class="actionBar">
      <button type="button" id="saveShots">保存分镜</button>
      <button type="button" id="saveShotsAndContinue" class="primary">保存并进入视频制作</button>
      <button type="button" id="regenerateStoryboard">根据当前脚本重新生成分镜</button>
      <a class="buttonLink" href="/api/v2/artifacts/${encodeURIComponent(state.selectedId)}/shot_plan/download">下载分镜 JSON</a>
    </div>
  `;
  $("#saveShots").addEventListener("click", () => saveShotPlan().catch((error) => toast(error.message, "error")));
  $("#saveShotsAndContinue").addEventListener("click", async () => {
    try { await saveShotPlan(); showView("proj_production"); } catch (error) { toast(error.message, "error"); }
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
    const takes = entry?.takes || [];
    const existingTakeIds = new Set(takes.map((take) => String(take.take_id)));
    let nextTakeIndex = 0;
    while (existingTakeIds.has(String.fromCharCode(65 + nextTakeIndex))) nextTakeIndex += 1;
    const nextTakeId = String.fromCharCode(65 + nextTakeIndex);
    const prompt = shot.seedance_prompt_zh || shot.seedance_prompt || shot.visual_prompt || "";
    const candidates = takes.map((take) => {
      const status = String(take.status || "needs_review");
      const note = safeTakeNote(take);
      const canReview = take.playable && ["needs_review", "succeeded", "qa_pass"].includes(status);
      const canSelect = take.playable && status === "qa_pass";
      return `
      <div class="takeCandidate">
        ${take.playable
          ? `<video controls preload="metadata" data-video-state src="${escapeAttr(take.media_url || runFileUrl(state.selectedId, take.path))}"></video><span class="mediaState" data-media-state>正在读取镜头预览...</span><a class="buttonLink" download href="${escapeAttr(take.media_url || runFileUrl(state.selectedId, take.path))}">下载此 Take</a>`
          : `<div class="mediaUnavailable">${escapeHtml(take.media_message || "无可播放视频：请以真实运行模式重新生成此 Take。")}</div>`}
        <span class="takeStatus ${statusClass(status)}">Take ${escapeHtml(take.take_id)} · ${escapeHtml(takeStatusLabel(status))}</span>
        <div class="actionBar takeActions">
          ${canReview ? `<button type="button" data-review-pass-shot="${shot.number}" data-review-pass-take="${escapeAttr(take.take_id)}">通过单镜质检</button><button type="button" data-review-reject-shot="${shot.number}" data-review-reject-take="${escapeAttr(take.take_id)}">不通过并重做</button>` : ""}
          ${canSelect ? `<button type="button" class="primary" data-select-shot="${shot.number}" data-select-take="${escapeAttr(take.take_id)}">选用此 Take</button>` : ""}
          ${status === "selected" ? '<span class="takeResolved">该镜头已选用</span>' : ""}
          ${status === "rejected" ? '<span class="takeRejected">请修改上方提示词或返工说明后生成新候选</span>' : ""}
        </div>
        ${note ? `<small class="takeNote">质检备注：${escapeHtml(note)}</small>` : ""}
      </div>
    `; }).join("");
    return `<section class="takeShot">
      <strong>镜头 ${shot.number} · ${shot.camera_motion?.duration_sec || 6}s</strong>
      <label class="takePromptLabel">生成提示词（可针对本镜修改后再生成）<textarea class="promptField" data-production-prompt="${shot.number}">${escapeHtml(prompt)}</textarea></label>
      <label class="takePromptLabel">返工说明（仅在“不通过并重做”时写入新 Take）<textarea data-rework-notes="${shot.number}" placeholder="例如：删除虚构 Logo；温度只显示 98°F；杯嘴向独立奶瓶倒液。"></textarea></label>
      <div class="actionBar"><button type="button" data-run-shot="${shot.number}" data-take-id="${escapeAttr(nextTakeId)}">${takes.length ? `生成新的候选 Take ${escapeHtml(nextTakeId)}` : "生成第一个候选 Take"}</button></div>
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
  host.querySelectorAll("[data-review-pass-take]").forEach((button) => {
    button.addEventListener("click", () => reviewTake(Number(button.dataset.reviewPassShot), button.dataset.reviewPassTake, true));
  });
  host.querySelectorAll("[data-review-reject-take]").forEach((button) => {
    button.addEventListener("click", () => rejectAndRegenerate(Number(button.dataset.reviewRejectShot), button.dataset.reviewRejectTake));
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
  const takeEntries = state.takeManifest?.shots || [];
  const missingShots = (state.shotPlan.shots || []).filter((shot) => !takeEntries.find((entry) => Number(entry.number) === Number(shot.number))?.selected_take_id).map((shot) => Number(shot.number));
  const durationReady = Math.abs(currentDuration - 30) <= 2;
  const ready = durationReady && missingShots.length === 0;
  const visualReview = state.renderReport?.output_path ? renderVisualReview() : "";
  const finalVideoLink = state.renderReport?.output_path
    ? `<a class="buttonLink" download href="${escapeAttr(runFileUrl(state.selectedId, state.renderReport.output_path))}">下载 720P 成片</a>`
    : "";
  host.innerHTML = `<div class="actionBar"><button type="button" id="composeVideo" ${ready ? "" : "disabled"}>${
    ready ? "使用已选镜头合成 30 秒视频" : missingShots.length ? `还差 ${missingShots.length} 个镜头未选用：镜头 ${missingShots.join("、")}` : `当前 ${currentDuration} 秒，请调整为 30 秒`
  }</button>${finalVideoLink}</div>${visualReview}`;
  $("#composeVideo").addEventListener("click", () => runManualStage("compose"));
  $("#submitVisualReview")?.addEventListener("click", submitVisualReview);
}

function renderVisualReview() {
  const qa = state.runReport?.qa_report;
  const blocked = qa?.failed_checks?.includes("human_visual_review");
  return `
    <section class="visualReview">
      <div class="nodeToolHead"><div><strong>成片人工视觉验收</strong><span>${blocked ? "技术质检已完成，必须完成以下人工验收后才会交付。" : "合成完成后，请确认成片中没有产品、温标和场景错误。"}</span></div></div>
      <div class="reviewChecklist">
        <label><input id="reviewProductIdentity" type="checkbox" /> 产品外观与素材库一致</label>
        <label><input id="reviewNoInventedBrand" type="checkbox" /> 无虚构品牌、文字或 Logo</label>
        <label><input id="reviewTemperature" type="checkbox" /> 温标为 98°F（华氏），非摄氏</label>
        <label><input id="reviewUsageFlow" type="checkbox" /> 倒液方向和使用流程正确</label>
        <label><input id="reviewContinuity" type="checkbox" /> 人物、服装、场景连续</label>
      </div>
      <textarea id="visualReviewNotes" class="visualReviewNotes" placeholder="可填写需要返工的镜头、产品或画面问题"></textarea>
      <div class="actionBar"><button type="button" id="submitVisualReview" class="primary">确认视觉验收并进入交付</button></div>
    </section>
  `;
}

async function submitVisualReview() {
  const checks = {
    product_identity: $("#reviewProductIdentity").checked,
    no_invented_brand: $("#reviewNoInventedBrand").checked,
    temperature_display: $("#reviewTemperature").checked,
    usage_flow: $("#reviewUsageFlow").checked,
    person_scene_continuity: $("#reviewContinuity").checked,
  };
  if (Object.values(checks).some((value) => !value)) {
    toast("请逐项确认；任一项不通过时应返回对应镜头重新生成", "error");
    return;
  }
  try {
    beginOperation("正在执行最终质检与归档", 25);
    await api("/api/v2/review/final-visual", {
      method: "POST",
      body: JSON.stringify({ project_id: state.selectedId, ...checks, notes: $("#visualReviewNotes").value.trim() }),
    });
    toast("视觉验收已记录，成片已进入交付检查");
    await refreshProjects();
    showView("proj_archive");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    endOperation();
  }
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
    const visualField = $(`[data-shot="${shot.number}"][data-shot-field="visual_zh"]`);
    const promptField = $(`[data-shot="${shot.number}"][data-shot-field="seedance_prompt_zh"]`);
    const productionPromptField = $(`[data-production-prompt="${shot.number}"]`);
    const durationField = $(`[data-shot="${shot.number}"][data-shot-field="duration"]`);
    if (visualField) shot.visual_zh = visualField.value.trim();
    if (promptField) shot.seedance_prompt_zh = promptField.value.trim();
    if (productionPromptField) {
      shot.seedance_prompt_zh = productionPromptField.value.trim();
      shot.seedance_prompt = productionPromptField.value.trim();
    }
    shot.camera_motion = shot.camera_motion || {};
    if (durationField) shot.camera_motion.duration_sec = Number(durationField.value || 6);
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
    await refreshProjects({ silent: true });
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

async function reviewTake(shotIndex, takeId, approved, notes = "") {
  try {
    await api("/api/v2/takes/review", {
      method: "POST",
      body: JSON.stringify({
        project_id: state.selectedId,
        shot_index: shotIndex,
        take_id: takeId,
        product_identity: approved,
        no_invented_brand: approved,
        temperature_display: approved,
        usage_flow: approved,
        continuity: approved,
        notes,
      }),
    });
    toast(approved ? `镜头 ${shotIndex} Take ${takeId} 已通过单镜质检` : `镜头 ${shotIndex} Take ${takeId} 已退回重做`);
    await refreshProjects();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function rejectAndRegenerate(shotIndex, takeId) {
  const notes = $(`[data-rework-notes="${shotIndex}"]`)?.value?.trim();
  if (!notes) {
    toast("请先在本镜的“返工说明”中写明产品、温标、动作或连续性问题", "error");
    return;
  }
  if (!notes) return;
  const shot = state.shotPlan?.shots?.find((item) => Number(item.number) === shotIndex);
  if (!shot) return;
  const currentPrompt = $(`[data-production-prompt="${shotIndex}"]`)?.value?.trim() || shot.seedance_prompt_zh || shot.seedance_prompt || "";
  const revisedPrompt = `${currentPrompt}\n返工要求：${notes}`.trim();
  shot.seedance_prompt = revisedPrompt;
  shot.seedance_prompt_zh = revisedPrompt;
  try {
    await reviewTake(shotIndex, takeId, false, notes);
    await saveShotPlan();
    const takeIds = new Set((state.takeManifest?.shots || []).find((item) => Number(item.number) === shotIndex)?.takes?.map((take) => String(take.take_id)) || []);
    let index = 0;
    while (takeIds.has(String.fromCharCode(65 + index))) index += 1;
    await runManualStage("production", shotIndex, String.fromCharCode(65 + index));
  } catch (error) {
    toast(error.message, "error");
  }
}

function renderHeroGate() {
  const host = $("#heroEditor");
  $("#heroGateState").textContent = state.selected?.current_gate === "hero_gate" ? "待确认" : "";
  if (!state.selected || !state.assetManifest) {
    host.className = "emptyState";
    host.textContent = "当前项目尚未生成可核对的关键帧。";
    return;
  }
  if (state.selected.current_gate !== "hero_gate") {
    host.className = "gateHistory";
    host.innerHTML = `<strong>关键帧闸门已完成</strong><span>当前项目已进入“${escapeHtml(stageLabel(state.selected.current_gate || state.selected.current_stage))}”，可回看产品身份锚点，无需重复确认。</span>`;
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
    toast(`镜头 ${shotIndex} 已重新生成`);
    await loadSelectedProject(state.selectedId);
  } catch (error) {
    toast(error.message, "error");
  }
}

async function approveHeroGate() {
  try {
    const payload = await api("/api/v2/gates/approve", {
      method: "POST",
      body: JSON.stringify({ project_id: state.selectedId, gate: "hero_gate", approver: "operator" }),
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
    const current = state.selected;
    const nextView = current?.current_gate === "take_gate" || current?.current_stage === "production" ? "proj_production" : current?.current_gate === "script_gate" ? "proj_script" : "proj_storyboard";
    host.innerHTML = `<div class="emptyGuide"><strong>暂无可交付项目</strong><span>${current ? `当前项目停在“${escapeHtml(stageLabel(current.current_gate || current.current_stage || current.status))}”。完成该节点后即可继续交付。` : "请先创建或打开一个项目。"}</span>${current ? `<button type="button" data-go-next>前往下一步</button>` : ""}</div>`;
    host.querySelector("[data-go-next]")?.addEventListener("click", () => showView(nextView));
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
          <strong>${escapeHtml(project.product_id || "未命名产品")}</strong><span>${escapeHtml(formatProjectTime(project.updated_at))} · ${project.mock ? "演练" : "真实"} · QA 通过</span><small>${escapeHtml(project.project_id)} · ¥${Number(project.cost.total_cost_cny || 0).toFixed(2)}</small>
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
  const feedbackButton = $("#sendFeedback");
  if (!selectedDelivered && feedbackButton) {
    feedbackButton.disabled = true;
    feedbackButton.title = "请先选择一个可交付项目";
  }
  if (selectedDelivered) {
    $("#sendFeedback").addEventListener("click", () => sendFeedback(selectedDelivered.project_id));
  }
  bindVideoPreviewStates(host, "交付成片不可播放。该项目已被识别为无效媒体，请重新合成并通过质检。");
}

function formatProjectTime(value) {
  if (!value) return "时间未知";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
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
