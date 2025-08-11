// parse id from URL
const params = new URLSearchParams(window.location.search);
const serverId = params.get('id');

async function init() {
  const list = await eel.list_servers()();
  const s = list.find(x => x.id === serverId);
  if (s) document.getElementById('server-name').innerText = s.name;
  document.getElementById('start').addEventListener('click', () => eel.start_server(serverId));
  document.getElementById('stop').addEventListener('click', () => eel.stop_server(serverId));
  document.getElementById('restart').addEventListener('click', () => eel.restart_server(serverId));
  document.getElementById('edit').addEventListener('click', () => {
    window.open('server_form.html?id=' + serverId, '_blank', 'width=600,height=400');
  });
  document.getElementById('send').addEventListener('click', () => {
    const cmd = document.getElementById('cmd').value;
    eel.send_command(serverId, cmd);
    document.getElementById('cmd').value = "";
  });
}

eel.expose(receive_console_line);
function receive_console_line(id, line) {
  if (id !== serverId) return;
  const pre = document.getElementById('console');
  pre.innerText += line + "\n";
  pre.scrollTop = pre.scrollHeight;
}

eel.expose(notify_server_stopped);
function notify_server_stopped(id, success) {
  if (id !== serverId) return;
  const pre = document.getElementById('console');
  pre.innerText += `[SERVER STOPPED] success=${success}\n`;
}

init();