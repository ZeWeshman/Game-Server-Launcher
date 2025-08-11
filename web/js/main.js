async function refresh() {
  const list = await eel.list_servers()();
  const container = document.getElementById('servers');
  container.innerHTML = "";
  list.forEach(s => {
    const div = document.createElement('div');
    div.innerHTML = `<strong>${s.name}</strong> [${s.id}] 
      <button data-id="${s.id}" class="start">Start</button>
      <button data-id="${s.id}" class="config">Config</button>`;
    container.appendChild(div);
  });
  document.querySelectorAll('button.start').forEach(b => {
    b.addEventListener('click', (ev) => {
      const id = ev.target.dataset.id;
      eel.start_and_open(id);
    });
  });
  document.querySelectorAll('button.config').forEach(b => {
    b.addEventListener('click', (ev) => {
      const id = ev.target.dataset.id;
      eel.open_control(id);
    });
  });
}

document.getElementById('btn-new').addEventListener('click', () => {
  window.open('server_form.html', '_blank', 'width=600,height=400');
});

refresh();