const STEPS = 16;
const tracks = [
  { id: 'kick', name: 'KICK', detail: 'low punch', color: '#ff7448', pattern: [0, 4, 8, 12] },
  { id: 'snare', name: 'SNARE', detail: 'backbeat', color: '#f7c873', pattern: [4, 12] },
  { id: 'hat', name: 'HI-HAT', detail: 'tight tick', color: '#8ed7d1', pattern: [0, 2, 4, 6, 8, 10, 12, 14] },
  { id: 'clap', name: 'CLAP', detail: 'bright layer', color: '#c19cff', pattern: [4, 12] }
];
const state = { playing: false, step: 0, timer: null, audio: null, tempo: 112 };
const $ = (selector) => document.querySelector(selector);

function render() {
  $('#step-numbers').innerHTML = Array.from({ length: STEPS }, (_, i) => `<span>${i + 1}</span>`).join('');
  $('#tracks').innerHTML = tracks.map((track) => `
    <div class="track" data-track="${track.id}">
      <div class="track-name" style="--track-color:${track.color}"><b></b><span>${track.name}<small>${track.detail}</small></span></div>
      <div class="steps">${Array.from({ length: STEPS }, (_, i) => `<button class="pad ${track.pattern.includes(i) ? 'active' : ''} ${i % 4 === 0 ? 'beat' : ''}" data-step="${i}" style="--track-color:${track.color}" aria-label="${track.name} step ${i + 1}" aria-pressed="${track.pattern.includes(i)}"></button>`).join('')}</div>
    </div>`).join('');
}
function audioContext() {
  if (!state.audio) state.audio = new (window.AudioContext || window.webkitAudioContext)();
  if (state.audio.state === 'suspended') state.audio.resume();
  return state.audio;
}
function tone(type) {
  const context = audioContext(), now = context.currentTime, oscillator = context.createOscillator(), gain = context.createGain(), filter = context.createBiquadFilter();
  oscillator.connect(filter).connect(gain).connect(context.destination); gain.gain.setValueAtTime(.0001, now); gain.gain.exponentialRampToValueAtTime(.45, now + .005);
  const end = now + (type === 'hat' ? .06 : .18); gain.gain.exponentialRampToValueAtTime(.0001, end);
  if (type === 'kick') { oscillator.type = 'sine'; oscillator.frequency.setValueAtTime(130, now); oscillator.frequency.exponentialRampToValueAtTime(45, now + .14); }
  else if (type === 'snare') { oscillator.type = 'triangle'; oscillator.frequency.setValueAtTime(190, now); filter.type = 'highpass'; filter.frequency.value = 1200; }
  else if (type === 'hat') { oscillator.type = 'square'; oscillator.frequency.value = 5800; filter.type = 'highpass'; filter.frequency.value = 4000; gain.gain.exponentialRampToValueAtTime(.08, now + .005); }
  else { oscillator.type = 'sawtooth'; oscillator.frequency.value = 260; filter.type = 'bandpass'; filter.frequency.value = 1800; }
  oscillator.start(now); oscillator.stop(end + .02);
}
function playStep() {
  document.querySelectorAll('.pad.current').forEach((pad) => pad.classList.remove('current'));
  document.querySelectorAll(`.pad[data-step="${state.step}"]`).forEach((pad) => { pad.classList.add('current'); if (pad.classList.contains('active')) tone(pad.closest('.track').dataset.track); });
  state.step = (state.step + 1) % STEPS;
}
function setPlaying(playing) {
  state.playing = playing; $('#play-button').textContent = playing ? 'Ⅱ' : '▶'; $('#transport-label').textContent = playing ? 'Pattern playing' : 'Pattern stopped'; $('#status-text').textContent = playing ? 'PLAYING' : 'READY'; $('.status').classList.toggle('playing', playing);
  if (playing) { audioContext(); state.step = 0; playStep(); state.timer = window.setInterval(playStep, 60000 / state.tempo / 4); }
  else { window.clearInterval(state.timer); state.timer = null; document.querySelectorAll('.pad.current').forEach((pad) => pad.classList.remove('current')); }
}
$('#tracks').addEventListener('click', (event) => {
  const pad = event.target.closest('.pad'); if (!pad) return;
  const track = tracks.find((item) => item.id === pad.closest('.track').dataset.track), step = Number(pad.dataset.step), index = track.pattern.indexOf(step);
  if (index >= 0) track.pattern.splice(index, 1); else track.pattern.push(step); render(); tone(track.id);
});
$('#play-button').addEventListener('click', () => setPlaying(!state.playing));
$('#clear-button').addEventListener('click', () => { tracks.forEach((track) => { track.pattern = []; }); render(); });
$('#random-button').addEventListener('click', () => { tracks.forEach((track, trackIndex) => { track.pattern = Array.from({ length: STEPS }, (_, i) => i).filter(() => Math.random() < (trackIndex === 2 ? .6 : .25)); }); render(); });
$('#tempo').addEventListener('input', (event) => { state.tempo = Number(event.target.value); $('#tempo-value').textContent = state.tempo; if (state.playing) { setPlaying(false); setPlaying(true); } });
document.addEventListener('keydown', (event) => { if (event.code === 'Space' && event.target.tagName !== 'INPUT') { event.preventDefault(); setPlaying(!state.playing); } });
render();
