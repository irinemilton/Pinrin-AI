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
    const opportunityCard = $("#opportunity-card");
    const ideas = run.artifacts?.opportunities?.ideas || [];
    const idea = ideas[0] || {};
    if (opportunityCard && idea.name) {
      opportunityCard.classList.remove("hidden");
      $("#opportunity-name").textContent = idea.name;
      $("#opportunity-promise").textContent = idea.promise || idea.problem || "Opportunity selected from current trend evidence.";
      $("#opportunity-audience").textContent = idea.audience ? `Audience: ${idea.audience}` : "Audience: not specified";
      const observations = (run.artifacts?.trends?.observations || []).slice(0, 5);
      $("#trend-evidence").innerHTML = observations.map((item) => `<span>${escapeHtml(item.keyword || "Trend signal")}</span>`).join("");
    } else if (opportunityCard) {
      opportunityCard.classList.add("hidden");
    }
    const gallery = $("#image-gallery");
    if (gallery) {
      const images = run.artifacts?.generated_images || [];
      gallery.innerHTML = images.map((_, index) => `<figure><img src="${apiUrl(`/api/agent/runs/${encodeURIComponent(run.id)}/images/${index}`)}" alt="Generated Pin ${index + 1}"><figcaption>Pin ${index + 1} <button class="quiet-button regenerate-image" data-index="${index}" ${status === "regenerating" ? "disabled" : ""}>Regenerate</button></figcaption></figure>`).join("");
      gallery.querySelectorAll(".regenerate-image").forEach((button) => button.addEventListener("click", () => regenerateImage(Number(button.dataset.index))));
    }
    $("#approval-headline").textContent = status === "awaiting_publish_approval" ? "The product is ready to publish." : "The system will pause for your approval.";
    $("#approval-copy").textContent = status === "awaiting_publish_approval" ? "Review the generated product and marketing queue in the server run record, then authorize external publication." : "The opportunity recommendation is waiting for your approval before product and marketing agents run.";
    if (status === "completed") { const publication = run.artifacts?.publication; $("#publication-result").innerHTML = publication ? `Verified product: ${publication.product_url ? `<a href="${escapeHtml(publication.product_url)}" target="_blank" rel="noopener">open URL</a>` : "no URL"}. Pins: ${publication.pins?.length || 0}.` : "Completed without a publication artifact."; loadRecords(); stopPolling(); }
    if (status === "blocked") { $("#run-retry").classList.remove("hidden"); stopPolling(); }
  }
  async function poll() { if (!state.runId) return; try { const response = await fetch(apiUrl(`/api/agent/runs/${encodeURIComponent(state.runId)}`)); if (!response.ok) throw new Error("Run not found"); renderRun(await response.json()); } catch (error) { $("#run-copy").textContent = error.message; } }
  function startPolling() { stopPolling(); state.timer = window.setInterval(poll, 1600); poll(); }
  function stopPolling() { if (state.timer) window.clearInterval(state.timer); state.timer = null; }
  let pendingRun = false;
  function requestRunCode() {
    pendingRun = true;
    $("#run-lock").classList.remove("hidden");
    $("#run-lock-error").textContent = "";
    $("#run-lock-code").value = "";
    $("#run-lock-code").focus();
  }
  function closeRunCode() { pendingRun = false; $("#run-lock").classList.add("hidden"); }
  async function startRun(runCode) {
    const button = $("#run-button");
    button.disabled = true;
    button.textContent = "Starting...";
    try {
      const response = await fetch(apiUrl("/api/agent/run"), { method: "POST", headers: { "x-pinpilot-run-code": runCode } });
      const run = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(run.detail || run.message || `Unable to start orchestrator (${response.status})`);
      if (!run.id) { $("#configuration-note").textContent = run.message || "An active campaign already exists."; return; }
      state.runId = run.id;
      renderRun(run);
      startPolling();
    } catch (error) {
      updatePresenter("BLOCKED", error.message);
    } finally {
      button.disabled = false;
      button.innerHTML = "Start campaign <span>↓</span>";
    }
  }
  $("#run-button").addEventListener("click", requestRunCode); $("#run-retry").addEventListener("click", requestRunCode); $("#new-run").addEventListener("click", requestRunCode);
  $("#run-lock-close").addEventListener("click", closeRunCode);
  $("#run-lock").addEventListener("click", (event) => { if (event.target.id === "run-lock") closeRunCode(); });
  $("#run-lock-form").addEventListener("submit", (event) => { event.preventDefault(); const code = $("#run-lock-code").value.trim(); if (!code) return; closeRunCode(); startRun(code); });
  $("#approve-opportunity").addEventListener("click", () => approve("approve-opportunity")); $("#approve-publish").addEventListener("click", () => approve("approve-publish"));
  async function approve(kind) {
    if (!state.runId) {
      $("#run-copy").textContent = "This run is not connected to the page. Start or reload the campaign.";
      return;
    }
    const button = $(`#${kind}`);
    const originalLabel = button.innerHTML;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.textContent = "Approving...";
    const endpoint = kind === "approve-opportunity" ? "approve-opportunity" : "approve-publish";
    try {
      const response = await fetch(apiUrl(`/api/agent/runs/${encodeURIComponent(state.runId)}/${endpoint}`), { method: "POST" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || payload.message || `Approval failed (${response.status})`);
      }
      if (!payload.id) {
        throw new Error("Approval returned no campaign run.");
      }
      renderRun(payload);
      startPolling();
    } catch (error) {
      $("#run-copy").textContent = error.message || "Approval failed. Please try again.";
    } finally {
      button.disabled = false;
      button.removeAttribute("aria-busy");
      button.innerHTML = originalLabel;
    }
  }
  async function regenerateImage(index) { if (!state.runId) return; try { const response = await fetch(apiUrl(`/api/agent/runs/${encodeURIComponent(state.runId)}/regenerate-image/${index}`), { method: "POST" }); if (!response.ok) throw new Error("Image regeneration failed"); renderRun(await response.json()); startPolling(); } catch (error) { $("#run-copy").textContent = error.message; } }
  $("#schedule-button").addEventListener("click", async () => { const endpoint = state.schedule ? "stop" : "start"; const response = await fetch(apiUrl(`/api/agent/schedule/${endpoint}`), { method: "POST" }); const result = await response.json(); state.schedule = Boolean(result.running); $("#schedule-button").textContent = state.schedule ? "Stop schedule" : "Start schedule"; });
  async function loadRecords() { try { const response = await fetch(apiUrl("/api/products")); const data = await response.json(); const products = data.products || []; $("#metric-products").textContent = products.length; $("#metric-pins").textContent = products.reduce((sum, item) => sum + (item.pins || []).filter((pin) => pin.status === "published").length, 0); } catch (_) {} }
  async function checkStatus() { try { const response = await fetch(apiUrl("/api/status")); const data = await response.json(); $("#connection-dot").style.background = data.status === "ok" ? "var(--green)" : "var(--amber)"; $("#connection-text").textContent = data.status === "ok" ? "SERVER CONNECTED" : "SERVER ATTENTION"; $("#configuration-note").textContent = data.agent?.campaign_mode === "trend_driven" ? `Trend-driven goal selection enabled. Hugging Face: ${data.agent.huggingface_configured ? "available" : "unavailable"}.` : `Configured goal ready. Hugging Face: ${data.agent.huggingface_configured ? "available" : "unavailable"}.`; state.schedule = Boolean(data.agent?.schedule?.running); $("#schedule-button").textContent = state.schedule ? "Stop schedule" : "Start schedule"; } catch (_) { $("#connection-text").textContent = apiBase ? "BACKEND OFFLINE" : "FRONTEND ONLY"; $("#configuration-note").textContent = apiBase ? "The backend is unavailable." : "Set PINRIN_API_BASE to connect the autonomous backend."; } }
  function initCharacter() {
    const target = $("#guide-canvas");
    if (!target || !window.THREE) return;
    const scene = new THREE.Scene();

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
    let spider = null;
    let spiderMixer = null;
    let spiderBones = [];
    let spiderLegs = [];
    const spiderPath = [
      { x: -2.8, y: 1.65 },
      { x: -2.25, y: 1.7 },
      { x: -1.55, y: 1.55 },
      { x: -0.85, y: 1.25 },
      { x: -0.25, y: 1.48 },
      { x: 0.22, y: 1.7 },
      { x: 0.55, y: 1.52 },
      { x: 0.62, y: 1.08 },
      { x: 0.5, y: 0.62 },
      { x: 0.72, y: 0.2 },
      { x: 1.2, y: 0.12 },
      { x: 1.75, y: 0.42 },
      { x: 2.35, y: 0.65 },
      { x: 2.8, y: 0.55 }
    ];
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

    // Load the woman as the main character.
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

      // The spider is a separate, top-facing crawler in front of the woman.
      new THREE.GLTFLoader().load(
        "/static/guide-model/spider/spider.glb",
        (loaded) => {
          const spiderMesh = loaded.scene;
          const bounds = new THREE.Box3().setFromObject(spiderMesh);
          const size = bounds.getSize(new THREE.Vector3());
          const center = bounds.getCenter(new THREE.Vector3());
          const scale = 0.95 / Math.max(size.x, size.y, size.z, 0.01);
          spiderMesh.scale.setScalar(scale);
          spiderMesh.position.set(-center.x * scale, -center.y * scale, -center.z * scale);
          spiderMesh.rotation.set(Math.PI / 2, 0, 0);
          spiderMesh.traverse((child) => {
            if (child.isBone) spiderBones.push({ bone: child, x: child.rotation.x, y: child.rotation.y, z: child.rotation.z });
            if (child.isMesh) child.frustumCulled = false;
          });
          const spine = spiderBones.find(({ bone }) => bone.name === "spine_02")?.bone;
          if (spine) {
            spiderLegs = spine.children
              .filter((child) => child.isBone && child.children.length)
              .map((root) => {
                const chain = [];
                let bone = root;
                while (bone?.isBone) {
                  chain.push({ bone, x: bone.rotation.x, y: bone.rotation.y, z: bone.rotation.z });
                  bone = bone.children.find((child) => child.isBone);
                }
                return chain;
              })
              .filter((chain) => chain.length >= 3);
          }
          spider = spiderMesh;
          scene.add(spider);
          if (loaded.animations?.length) {
            spiderMixer = new THREE.AnimationMixer(spiderMesh);
            loaded.animations.forEach((clip) => spiderMixer.clipAction(clip).play());
          }
        },
        undefined,
        (error) => console.warn("Spider GLB failed to load", error)
      );
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
    let nextImpactSound = 30;
    let impactPlayed = false;
    const batHowl = new Audio("/static/mixkit-lone-wolf-howling-1729.wav");
    const ambientHowl = new Audio("/static/mixkit-wolves-at-scary-forest-2485.wav");
    const horrorImpact = new Audio("/static/mixkit-horror-impact-773.wav");
    batHowl.volume = 0.22;
    ambientHowl.volume = 0.12;
    horrorImpact.volume = 0.18;
    batHowl.preload = "auto";
    ambientHowl.preload = "auto";
    horrorImpact.preload = "auto";

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
      if (!impactPlayed && clock.elapsedTime >= 30) {
        impactPlayed = true;
        playSound(horrorImpact);
        nextImpactSound = clock.elapsedTime + 30;
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
      if (spiderMixer) spiderMixer.update(delta);
      if (spider) {
        const crawl = (time % 24) / 24;
        const pathPosition = crawl * (spiderPath.length - 1);
        const pathIndex = Math.min(Math.floor(pathPosition), spiderPath.length - 2);
        const pathMix = pathPosition - pathIndex;
        const current = spiderPath[pathIndex];
        const next = spiderPath[pathIndex + 1];
        const x = current.x + (next.x - current.x) * pathMix;
        const y = current.y + (next.y - current.y) * pathMix;
        const dx = next.x - current.x;
        const dy = next.y - current.y;
        spider.position.x = x;
        spider.position.y = y;
        spider.position.z = 0.75;
        spider.rotation.z = Math.atan2(dy, dx);
      }
      if (spiderLegs.length && !prefersReducedMotion) {
        spiderLegs.forEach((leg, legIndex) => {
          const phase = time * 4.2 + legIndex * Math.PI;
          const step = Math.sin(phase);
          const side = legIndex % 2 ? 1 : -1;
          leg.forEach(({ bone, x, y, z }, jointIndex) => {
            const lift = Math.max(0, step) * side;
            bone.rotation.x = x + lift * (jointIndex === 1 ? 0.24 : 0.08);
            bone.rotation.y = y;
            bone.rotation.z = z + step * side * (jointIndex === 0 ? 0.2 : jointIndex === 1 ? -0.3 : 0.16);
          });
        });
      }
      if (!prefersReducedMotion && time >= nextAmbientSound) {
        playSound(ambientHowl);
        nextAmbientSound = time + 18 + Math.random() * 14;
      }
      if (!prefersReducedMotion && time >= nextImpactSound) {
        playSound(horrorImpact);
        impactPlayed = true;
        nextImpactSound = time + 30;
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
