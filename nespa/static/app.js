const $ = s => document.querySelector(s);
let taskId = null;
async function api(path, init = {}) {
  const res = await fetch(path, {headers: {"Content-Type": "application/json"}, ...init});
  if (!res.ok) throw new Error("Request failed: " + res.status);
  return res.json();
}
function appendMessage(message, role) {
  const div = document.createElement("article");
  div.className = role;
  div.textContent = message;
  $("#messages").append(div);
  $("#messages").scrollTop = $("#messages").scrollHeight;
}
async function refresh() {
  try {
    if (!taskId) {
      const tasks = await api("/api/tasks");
      if (tasks.length) taskId = tasks[0].id;
    }
    if (taskId) {
      const [task, events] = await Promise.all([api("/api/tasks/" + taskId),api("/api/tasks/" + taskId + "/events")]);
      $("#status").textContent = task.status.toUpperCase();
      $("#task-title").textContent = task.title;
      $("#count").textContent = task.completed_steps + " / " + task.total_steps;
      $("#bar").style.width = (100 * task.completed_steps / task.total_steps) + "%";
      $("#start").disabled = ["queued","running"].includes(task.status);
      $("#events").replaceChildren();
      events.slice(-12).reverse().forEach(e => {
        const row = document.createElement("div");
        row.textContent = "• " + e.message;
        $("#events").append(row);
      });
    }
    const notes = await api("/api/notes");
    $("#notes").textContent = notes.length ? notes.slice(0,6).map(n => "• " + n.content).join("\n") : "暂无笔记";
  } catch (err) { console.warn(err); }
}
$("#start").addEventListener("click", async () => {
  $("#start").disabled = true;
  try {
    const task = await api("/api/tasks", {method:"POST",body:JSON.stringify({title:"Literature review (simulation)",total_steps:12,interval_ms:750})});
    taskId = task.id;
    await refresh();
  } catch(err) { appendMessage(err.message, "assistant"); $("#start").disabled = false; }
});
$("#chat").addEventListener("submit", async event => {
  event.preventDefault();
  const message = $("#prompt").value.trim();
  if (!message) return;
  $("#prompt").value = "";
  appendMessage(message, "user");
  try {
    const result = await api("/api/chat",{method:"POST",body:JSON.stringify({message,task_id:taskId})});
    appendMessage(result.reply,"assistant");
    await refresh();
  } catch(err) { appendMessage(err.message,"assistant"); }
});
refresh();
setInterval(refresh,1000);
