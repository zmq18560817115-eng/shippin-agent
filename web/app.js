fetch("/healthz")
  .then((response) => response.json())
  .then((data) => {
    document.body.dataset.health = data.status || "unknown";
  })
  .catch(() => {
    document.body.dataset.health = "offline";
  });
