const portalState = { portal: "operator", authEnabled: false };

const portalCopy = {
  operator: { code: "普通用户入口", title: "进入内容生产工作台" },
  admin: { code: "管理员入口", title: "进入后台管理平台" },
};

document.querySelectorAll("[data-portal]").forEach((button) => {
  button.addEventListener("click", () => {
    portalState.portal = button.dataset.portal;
    document.querySelectorAll("[data-portal]").forEach((item) => item.classList.toggle("active", item === button));
    document.querySelector("#portalCode").textContent = portalCopy[portalState.portal].code;
    document.querySelector("#portalTitle").textContent = portalCopy[portalState.portal].title;
    if (typeof setRegistrationMode === "function") setRegistrationMode(false);
  });
});

async function loadSession() {
  const response = await fetch("/api/v2/auth/session");
  const session = await response.json();
  portalState.authEnabled = Boolean(session.auth_enabled);
  document.querySelector("#authHint").textContent = portalState.authEnabled
    ? "请输入管理员为你创建的内网账号与密码。"
    : "当前为本地开发模式，填写任意账号即可进入。";
}

document.querySelector("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = document.querySelector("#loginError");
  error.textContent = "";
  try {
    const response = await fetch("/api/v2/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.querySelector("#username").value.trim(),
        password: document.querySelector("#password").value,
        portal: portalState.portal,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "登录失败");
    const requestedNext = new URLSearchParams(window.location.search).get("next") || "";
    let safeNext = payload.redirect;
    if (requestedNext) {
      const candidate = new URL(requestedNext, window.location.origin);
      if (candidate.origin === window.location.origin && candidate.pathname === payload.redirect) {
        safeNext = `${candidate.pathname}${candidate.search}${candidate.hash}`;
      }
    }
    window.location.assign(safeNext);
  } catch (cause) {
    error.textContent = cause.message;
  }
});

function setRegistrationMode(showRegistration) {
  document.querySelector("#loginForm").hidden = showRegistration;
  document.querySelector("#registrationPanel").hidden = !showRegistration;
  document.querySelector("#showRegistration").hidden = showRegistration || !portalState.authEnabled || portalState.portal !== "operator";
  document.querySelector("#showLogin").hidden = !showRegistration;
}

document.querySelector("#showRegistration").addEventListener("click", () => setRegistrationMode(true));
document.querySelector("#showLogin").addEventListener("click", () => setRegistrationMode(false));

document.querySelector("#registrationForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const error = document.querySelector("#registrationError");
  error.textContent = "";
  const password = document.querySelector("#registrationPassword").value;
  if (password !== document.querySelector("#registrationConfirmPassword").value) {
    error.textContent = "两次输入的密码不一致";
    return;
  }
  try {
    const response = await fetch("/api/v2/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.querySelector("#registrationUsername").value.trim(),
        display_name: document.querySelector("#registrationDisplayName").value.trim(),
        password,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "账号申请提交失败");
    form.reset();
    error.style.color = "#23734d";
    error.textContent = "申请已提交，请等待管理员审核开通。";
  } catch (cause) {
    error.style.color = "";
    error.textContent = cause.message;
  }
});

loadSession().then(() => setRegistrationMode(false));

loadSession().catch(() => {
  document.querySelector("#loginError").textContent = "无法连接服务器，请检查服务状态。";
});
