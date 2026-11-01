/* The client observes the server-side orchestrator. It never invents agent results. */
document.addEventListener("DOMContentLoaded", () => {
  const $ = (selector) => document.querySelector(selector);
  const state = { runId: null, timer: null, schedule: false, currentScene: "" };
  const apiBase = String(window.PINRIN_API_BASE || "").replace(/\/$/, "");
  const apiUrl = (path) => `${apiBase}${path}`;
  const sceneFor = { queued: "run", running: "run", awaiting_approval: "approval", awaiting_publish_approval: "approval", publishing: "publish", completed: "optimize", blocked: "run" };
  const agentScene = { trend_scout: "research", opportunity_analyst: "research", product_builder: "product", marketing_assistant: "product", commerce_agent: "publish", performance_analyst: "optimize" };

  function scrollTo(id) { document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" }); }
  function updatePresenter(status, task) { $("#agent-state").textContent = status.toUpperCase(); $("#agent-task").textContent = task || "Autonomous workflow"; const labels = { IDLE: ["Ready to run.", "The operator is waiting for a configured campaign."], QUEUED: ["The campaign is queued.", "I am preparing the agent sequence."], RUNNING: ["I am operating the campaign.", "Specialists are executing observable tasks."], AWAITING_APPROVAL: ["I need your decision.", "The next irreversible step is paused."], PUBLISHING: ["The campaign is moving.", "External adapters are returning verified results."], COMPLETED: ["The loop is complete.", "Observed results are ready for the next experiment."], BLOCKED: ["I found a blocker.", "I will not turn missing capability into a success."], OPTIMIZING: ["I am learning from records.", "Metrics are shown only when an adapter returns them."] }; const message = labels[status.toUpperCase()] || labels.RUNNING; $("#agent-name").textContent = message[0]; $("#agent-says").textContent = message[1]; $("#phase-count").textContent = status.toUpperCase(); }

  function setLine(id, event) { const node = $(`#${id}`); if (!node || !event) return; node.classList.toggle("active", ["started", "running"].includes(event.status)); node.classList.toggle("done", event.status === "completed"); node.innerHTML = `<b>${node.querySelector("b")?.textContent || "AGENT"}</b> ${escapeHtml(event.summary)} <small>${escapeHtml(event.status)}</small>`; }
  function renderRun(run) {
    if (!run) return;
    const status = run.status || "queued"; const task = run.events?.at(-1)?.summary || "Waiting for agent event"; updatePresenter(status, task);
    $("#run-headline").textContent = status === "blocked" ? "The run is blocked." : status === "completed" ? "The campaign completed." : "The operator is working.";
    $("#run-copy").textContent = run.error || "The orchestrator is routing the campaign across specialized agents.";
    const stream = $("#event-stream"); stream.innerHTML = (run.events || []).slice(-9).map((event) => `<span class="${event.status === "completed" ? "done" : event.status === "started" ? "active" : ""}"><b>${escapeHtml(event.agent)}</b> ${escapeHtml(event.summary)}</span>`).join("") || "<span>Waiting for run</span>";
    (run.events || []).forEach((event) => { const id = { trend_scout: "trend-status", opportunity_analyst: "opportunity-status", product_builder: "builder-status", marketing_assistant: "marketing-status", commerce_agent: "commerce-status", performance_analyst: "performance-status" }[event.agent]; if (id) setLine(id, event); if (event.agent === "pinterest_adapter") setLine("pin-status", event); });
    const latestAgentScene = agentScene[run.events?.at(-1)?.agent]; const scene = run.status === "awaiting_approval" || run.status === "awaiting_publish_approval" ? "approval" : latestAgentScene || sceneFor[run.status] || "run"; if (scene !== state.currentScene) { state.currentScene = scene; scrollTo(scene); }
    $("#approve-opportunity").classList.toggle("hidden", status !== "awaiting_approval"); $("#approve-publish").classList.toggle("hidden", status !== "awaiting_publish_approval");
    $("#approval-headline").textContent = status === "awaiting_publish_approval" ? "The product is ready to publish." : "The system will pause for your approval.";
    $("#approval-copy").textContent = status === "awaiting_publish_approval" ? "Review the generated product and marketing queue in the server run record, then authorize external publication." : "The opportunity recommendation is waiting for your approval before product and marketing agents run.";
    if (status === "completed") { const publication = run.artifacts?.publication; $("#publication-result").innerHTML = publication ? `Verified product: ${publication.product_url ? `<a href="${escapeHtml(publication.product_url)}" target="_blank" rel="noopener">open URL</a>` : "no URL"}. Pins: ${publication.pins?.length || 0}.` : "Completed without a publication artifact."; loadRecords(); stopPolling(); }
    if (status === "blocked") { $("#run-retry").classList.remove("hidden"); stopPolling(); }
  }
  async function poll() { if (!state.runId) return; try { const response = await fetch(apiUrl(`/api/agent/runs/${encodeURIComponent(state.runId)}`)); if (!response.ok) throw new Error("Run not found"); renderRun(await response.json()); } catch (error) { $("#run-copy").textContent = error.message; } }
  function startPolling() { stopPolling(); state.timer = window.setInterval(poll, 1600); poll(); }
  function stopPolling() { if (state.timer) window.clearInterval(state.timer); state.timer = null; }
  async function startRun() { const button = $("#run-button"); button.disabled = true; button.textContent = "Starting..."; try { const response = await fetch(apiUrl("/api/agent/run"), { method: "POST" }); const run = await response.json(); if (!run.id) { $("#configuration-note").textContent = run.message || "An active campaign already exists."; return; } state.runId = run.id; renderRun(run); startPolling(); } catch (error) { updatePresenter("BLOCKED", error.message); } finally { button.disabled = false; button.innerHTML = "Start campaign <span>↓</span>"; } }
  $("#run-button").addEventListener("click", startRun); $("#run-retry").addEventListener("click", startRun); $("#new-run").addEventListener("click", startRun);
  $("#approve-opportunity").addEventListener("click", () => approve("approve-opportunity")); $("#approve-publish").addEventListener("click", () => approve("approve-publish"));
  async function approve(kind) { if (!state.runId) return; const button = $(`#${kind}`); button.disabled = true; const endpoint = kind === "approve-opportunity" ? "approve-opportunity" : "approve-publish"; try { const response = await fetch(apiUrl(`/api/agent/runs/${encodeURIComponent(state.runId)}/${endpoint}`), { method: "POST" }); renderRun(await response.json()); startPolling(); } finally { button.disabled = false; } }
  $("#schedule-button").addEventListener("click", async () => { const endpoint = state.schedule ? "stop" : "start"; const response = await fetch(apiUrl(`/api/agent/schedule/${endpoint}`), { method: "POST" }); const result = await response.json(); state.schedule = Boolean(result.running); $("#schedule-button").textContent = state.schedule ? "Stop schedule" : "Start schedule"; });
  async function loadRecords() { try { const response = await fetch(apiUrl("/api/products")); const data = await response.json(); const products = data.products || []; $("#metric-products").textContent = products.length; $("#metric-pins").textContent = products.reduce((sum, item) => sum + (item.pins || []).filter((pin) => pin.status === "published").length, 0); } catch (_) {} }
  async function checkStatus() { try { const response = await fetch(apiUrl("/api/status")); const data = await response.json(); $("#connection-dot").style.background = data.status === "ok" ? "var(--green)" : "var(--amber)"; $("#connection-text").textContent = data.status === "ok" ? "SERVER CONNECTED" : "SERVER ATTENTION"; $("#configuration-note").textContent = data.agent?.campaign_configured ? `Configured goal ready. Hugging Face: ${data.agent.huggingface_configured ? "available" : "unavailable"}.` : "No AGENT_CAMPAIGN_GOAL configured on the server."; state.schedule = Boolean(data.agent?.schedule?.running); $("#schedule-button").textContent = state.schedule ? "Stop schedule" : "Start schedule"; } catch (_) { $("#connection-text").textContent = apiBase ? "BACKEND OFFLINE" : "FRONTEND ONLY"; $("#configuration-note").textContent = apiBase ? "The backend is unavailable." : "Set PINRIN_API_BASE to connect the autonomous backend."; } }
  function initCharacter() {
    const target = $("#guide-canvas");
    if (!target || !window.THREE) return;
    const scene = new THREE.Scene();
    let bat = null;
    let batMixer = null;

    // Portrait focal length (26 deg) eliminates wide-angle distortion and slims proportions
    const camera = new THREE.PerspectiveCamera(29, target.clientWidth / target.clientHeight, .1, 100);
    camera.position.set(0, 1.32, 5.2);
    camera.lookAt(0, 1.18, 0);

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.setSize(target.clientWidth, target.clientHeight);
    renderer.outputEncoding = THREE.sRGBEncoding;
    target.appendChild(renderer.domElement);

    scene.add(new THREE.AmbientLight(0xffffff, 1.8));
    const keyLight = new THREE.PointLight(0xffffff, 4, 10);
    keyLight.position.set(2.5, 3.5, 4);
    scene.add(keyLight);

    // --- Floating Atmospheric Glowing Ember Motes ---
    const emberCount = 0;
    const emberGeo = new THREE.BufferGeometry();
    const emberPositions = new Float32Array(emberCount * 3);
    const emberSpeeds = new Float32Array(emberCount);
    for (let i = 0; i < emberCount; i++) {
      emberPositions[i * 3] = (Math.random() - 0.5) * 3.5;
      emberPositions[i * 3 + 1] = Math.random() * 2.8;
      emberPositions[i * 3 + 2] = (Math.random() - 0.5) * 2.5;
      emberSpeeds[i] = 0.2 + Math.random() * 0.4;
    }
    emberGeo.setAttribute("position", new THREE.BufferAttribute(emberPositions, 3));
    const emberMat = new THREE.PointsMaterial({
      color: 0xff3f76,
      size: 0.045,
      transparent: true,
      opacity: 0.75,
      blending: THREE.AdditiveBlending
    });
    const embers = new THREE.Points(emberGeo, emberMat);
    scene.add(embers);

    // Root pivot for natural centered rotations and parallax
    const characterPivot = new THREE.Group();
    const modelHolder = new THREE.Group();
    characterPivot.add(modelHolder);
    scene.add(characterPivot);

    let mixer = null;
    // Perfect vertical portrait alignment: eyes at upper third, waist at lower third
    let baseY = -0.22;
    characterPivot.position.set(0, baseY, 0);

    // Keep the source model's original front-facing orientation.
    const baseYaw = 0;
    const basePitch = 0;
    const baseRoll = 0;

    // Fallback mesh while model loads
    const fallback = new THREE.Mesh(
      new THREE.IcosahedronGeometry(.72, 2),
      new THREE.MeshStandardMaterial({ color: 0x9c7bff, roughness: .3, metalness: .4 })
    );
    fallback.position.y = 1.1;
    modelHolder.add(fallback);

    // Load GLB character
    if (THREE.GLTFLoader) {
      new THREE.GLTFLoader().load(
        "/static/guide-model/source/ip-chainsaw-man__makima__real__sexy.glb",
        (loaded) => {
          modelHolder.remove(fallback);
          const characterMesh = loaded.scene;
          const bounds = new THREE.Box3().setFromObject(characterMesh);
          const size = bounds.getSize(new THREE.Vector3());
          const center = bounds.getCenter(new THREE.Vector3());
          const scale = 3.8 / Math.max(size.x, size.y, size.z, 0.01);

          // Refined silhouette proportions: sleek waist, statuesque posture, graceful neck
          characterMesh.scale.set(scale * 0.95, scale * 1.025, scale * 0.96);

          // Center the mesh precisely around the pivot origin
          characterMesh.position.set(-center.x * scale, -center.y * scale, -center.z * scale);

          modelHolder.add(characterMesh);
          baseY = -0.22;
          characterPivot.position.set(0, baseY, 0);

          if (loaded.animations?.length) {
            mixer = new THREE.AnimationMixer(characterMesh);
            mixer.clipAction(loaded.animations[0]).play();
          }
        },
        undefined,
        () => {}
      );
    }

    if (THREE.FBXLoader) {
      const loadBat = (path, fallbackPath) => new THREE.FBXLoader().load(
        path,
        (loaded) => {
          const bounds = new THREE.Box3().setFromObject(loaded);
          const size = bounds.getSize(new THREE.Vector3());
          const scale = 0.72 / Math.max(size.x, size.y, size.z, 0.01);
          loaded.scale.setScalar(scale);
          loaded.position.set(-1.9, 2.15, 0.35);
          loaded.visible = true;
          loaded.traverse((child) => {
            if (child.isMesh) {
              child.frustumCulled = false;
              const materials = Array.isArray(child.material) ? child.material : [child.material];
              materials.forEach((material) => {
                if (material) {
                  material.transparent = false;
                  material.opacity = 1;
                  material.depthWrite = true;
                }
              });
            }
          });
          bat = loaded;
          scene.add(bat);
          if (loaded.animations?.length) {
            batMixer = new THREE.AnimationMixer(loaded);
            loaded.animations.forEach((clip) => batMixer.clipAction(clip).play());
          }
        },
        undefined,
        () => {
          console.warn("Primary bat asset failed to load", path);
          if (fallbackPath) loadBat(fallbackPath, null);
        }
      );
      loadBat("/static/guide-model/bat/Bat_morph.FBX", "/static/guide-model/bat/bat.FBX");
    }

    // Interactive mouse tracking state
    let targetMouseX = 0, targetMouseY = 0;
    let currentMouseX = 0, currentMouseY = 0;
    let isDragging = false;
    let dragStartX = 0, dragStartY = 0;
    let dragRotX = 0, dragRotY = 0;
    let targetDragRotX = 0, targetDragRotY = 0;

    function onPointerMove(e) {
      const rect = target.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;

      // Normalized coordinates relative to the canvas center (-1 to 1)
      const nx = (e.clientX - centerX) / (window.innerWidth * 0.5);
      const ny = (e.clientY - centerY) / (window.innerHeight * 0.5);
      targetMouseX = Math.max(-1.0, Math.min(1.0, nx));
      targetMouseY = Math.max(-1.0, Math.min(1.0, ny));

      if (isDragging) {
        const deltaX = e.clientX - dragStartX;
        const deltaY = e.clientY - dragStartY;
        targetDragRotY += deltaX * 0.007;
        targetDragRotX += deltaY * 0.004;
        // Restrict drag pitch strictly to a flattering portrait range
        targetDragRotX = Math.max(-0.16, Math.min(0.16, targetDragRotX));
        dragStartX = e.clientX;
        dragStartY = e.clientY;
      }
    }

    function onPointerDown(e) {
      unlockAudio();
      if (e.target.closest("button, a, input, select, textarea, .event-stream, .topbar")) return;
      isDragging = true;
      dragStartX = e.clientX;
      dragStartY = e.clientY;
    }

    function onPointerUp() {
      isDragging = false;
    }

    function onMouseLeave() {
      if (!isDragging) {
        targetMouseX = 0;
        targetMouseY = 0;
      }
    }

    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("pointerdown", onPointerDown, { passive: true });
    window.addEventListener("pointerup", onPointerUp, { passive: true });
    window.addEventListener("pointercancel", onPointerUp, { passive: true });
    document.addEventListener("mouseleave", onMouseLeave, { passive: true });

    const clock = new THREE.Clock();
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let audioContext = null;
    let audioUnlocked = false;
    let initialHowlPlayed = false;
    let giggleStart = -Infinity;
    let nextGiggle = 12 + Math.random() * 10;
    let nextAmbientSound = 16 + Math.random() * 12;
    let previousFlight = 0;
    const batHowl = new Audio("/static/mixkit-lone-wolf-howling-1729.wav");
    const ambientHowl = new Audio("/static/mixkit-wolves-at-scary-forest-2485.wav");
    batHowl.volume = 0.22;
    ambientHowl.volume = 0.12;
    batHowl.preload = "auto";
    ambientHowl.preload = "auto";

    function unlockAudio() {
      if (prefersReducedMotion) return;
      audioUnlocked = true;
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass && !audioContext) audioContext = new AudioContextClass();
      if (audioContext?.state === "suspended") audioContext.resume();
      if (!initialHowlPlayed) {
        initialHowlPlayed = true;
        playSound(batHowl);
      }
    }

    function playSound(audio) {
      if (!audioUnlocked || prefersReducedMotion) return;
      audio.currentTime = 0;
      audio.play().catch(() => {});
    }

    function playGiggle() {
      if (!audioContext || audioContext.state !== "running") return;
      const now = audioContext.currentTime;
      const master = audioContext.createGain();
      master.gain.setValueAtTime(0.0001, now);
      master.gain.exponentialRampToValueAtTime(0.045, now + 0.04);
      master.gain.exponentialRampToValueAtTime(0.0001, now + 0.72);
      master.connect(audioContext.destination);
      [560, 720, 590, 760].forEach((frequency, index) => {
        const oscillator = audioContext.createOscillator();
        const gain = audioContext.createGain();
        const start = now + index * 0.14;
        oscillator.type = "sine";
        oscillator.frequency.setValueAtTime(frequency, start);
        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.exponentialRampToValueAtTime(0.7, start + 0.035);
        gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.17);
        oscillator.connect(gain);
        gain.connect(master);
        oscillator.start(start);
        oscillator.stop(start + 0.19);
      });
    }

    function triggerGiggle(time) {
      if (prefersReducedMotion) return;
      giggleStart = time;
      playGiggle();
    }

    function render() {
      const delta = Math.min(clock.getDelta(), 0.05);
      const time = clock.elapsedTime;
      if (mixer) mixer.update(delta);
      if (batMixer) batMixer.update(delta);
      if (bat) {
        const flight = (time % 18) / 18;
        if (flight < previousFlight) playSound(batHowl);
        previousFlight = flight;
        bat.position.x = -1.9 + flight * 3.8;
        bat.position.y = 2.15 - flight * 1.45 + Math.sin(flight * Math.PI * 2) * 0.16;
        bat.position.z = 0.35 + Math.sin(flight * Math.PI) * 0.12;
        bat.rotation.z = -0.12 + Math.sin(flight * Math.PI * 2) * 0.08;
        bat.rotation.y = Math.PI / 2;
      }
      if (!prefersReducedMotion && time >= nextAmbientSound) {
        playSound(ambientHowl);
        nextAmbientSound = time + 18 + Math.random() * 14;
      }

      // Smooth interpolation for lifelike, responsive inertia
      const lerpSpeed = 0.055;
      currentMouseX += (targetMouseX - currentMouseX) * lerpSpeed;
      currentMouseY += (targetMouseY - currentMouseY) * lerpSpeed;
      dragRotX += (targetDragRotX - dragRotX) * 0.08;
      dragRotY += (targetDragRotY - dragRotY) * 0.08;

      // Animate floating ember motes
      const posAttr = emberGeo.attributes.position;
      for (let i = 0; i < emberCount; i++) {
        let y = posAttr.getY(i) + emberSpeeds[i] * delta * 0.45;
        if (y > 2.8) y = -0.2;
        posAttr.setY(i, y);
      }
      posAttr.needsUpdate = true;

      // Seductive head & body rotation anchored at the alluring 3/4 base pose
      const yaw = baseYaw + dragRotY + (currentMouseX * 0.42);
      const pitch = basePitch + dragRotX + (currentMouseY * 0.16);
      const roll = baseRoll - (currentMouseX * 0.06);

      characterPivot.rotation.y = yaw;
      characterPivot.rotation.x = pitch;
      characterPivot.rotation.z = roll;

      // Parallax translation + gentle breathing float
      const idleFloat = Math.sin(time * 1.25) * 0.02;
      characterPivot.position.y = baseY + idleFloat - (currentMouseY * 0.04);
      characterPivot.position.x = currentMouseX * 0.09;
      characterPivot.position.z = -Math.abs(currentMouseX) * 0.04;

      if (!prefersReducedMotion) {
        if (time >= nextGiggle) {
          triggerGiggle(time);
          nextGiggle = time + 20 + Math.random() * 18;
        }
        const giggleAge = time - giggleStart;
        const giggleEnvelope = giggleAge >= 0 && giggleAge < 1.15 ? Math.exp(-giggleAge * 3.6) : 0;
        const giggleShake = Math.sin(giggleAge * 34) * giggleEnvelope * 0.022;
        const idleSway = Math.sin(time * 0.72) * 0.012;
        const breath = Math.sin(time * 1.55) * 0.006;
        modelHolder.rotation.z = idleSway + giggleShake;
        modelHolder.rotation.x = Math.sin(time * 0.58 + 0.8) * 0.005;
        modelHolder.position.y = Math.sin(time * 1.1 + 0.4) * 0.006 + Math.abs(Math.sin(giggleAge * 16)) * giggleEnvelope * 0.012;
        modelHolder.scale.x = 1 - breath * 0.35;
        modelHolder.scale.y = 1 + breath;
        modelHolder.scale.z = 1 - breath * 0.35;
      } else {
        modelHolder.rotation.set(0, 0, 0);
        modelHolder.position.y = 0;
        modelHolder.scale.set(1, 1, 1);
      }

      renderer.render(scene, camera);
      requestAnimationFrame(render);
    }
    render();

    new ResizeObserver(() => {
      const width = target.clientWidth, height = target.clientHeight;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    }).observe(target);
  }
  function escapeHtml(value) { return String(value || "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char])); }
  initCharacter(); checkStatus(); updatePresenter("IDLE", "Awaiting start");
});
