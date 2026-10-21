/**
 * PinPilot - Pipeline Engine Frontend
 */
document.addEventListener("DOMContentLoaded", () => {
  // Navigation Tabs
  const tabPipeline = document.getElementById("tab-pipeline");
  const tabMockup = document.getElementById("tab-mockup");
  const tabArchive = document.getElementById("tab-archive");

  const viewPipelineContainer = document.getElementById("view-pipeline-container");
  const viewMockupContainer = document.getElementById("view-mockup-container");
  const viewArchiveContainer = document.getElementById("view-archive-container");

  function switchTab(activeTab, activeView) {
    [tabPipeline, tabMockup, tabArchive].forEach(t => t.classList.remove("active"));
    [viewPipelineContainer, viewMockupContainer, viewArchiveContainer].forEach(v => v.style.display = "none");

    activeTab.classList.add("active");
    if (activeView === viewMockupContainer) {
      activeView.style.display = "grid";
    } else {
      activeView.style.display = "block";
    }
  }

  tabPipeline.addEventListener("click", () => switchTab(tabPipeline, viewPipelineContainer));
  tabMockup.addEventListener("click", () => switchTab(tabMockup, viewMockupContainer));
  tabArchive.addEventListener("click", () => {
    switchTab(tabArchive, viewArchiveContainer);
    loadArchive();
  });

  // Inputs
  const inputTitle = document.getElementById("input-title");
  const inputPrice = document.getElementById("input-price");
  const inputBoard = document.getElementById("input-board");
  const inputTags = document.getElementById("input-tags");
  const inputDesc = document.getElementById("input-desc");

  // Mockup Elements
  const mockPinTitle = document.getElementById("mock-pin-title");
  const mockPinDesc = document.getElementById("mock-pin-desc");
  const mockBoardTag = document.getElementById("mock-board-tag");
  const mockPinImg = document.getElementById("mock-pin-img");
  const mockPinEmpty = document.getElementById("mock-pin-empty");
  const mockPinLink = document.getElementById("mock-pin-link");

  const mockGumPrice = document.getElementById("mock-gum-price");
  const mockGumTitle = document.getElementById("mock-gum-title");
  const mockGumDesc = document.getElementById("mock-gum-desc");
  const mockGumCta = document.getElementById("mock-gum-cta");

  function updateMockups() {
    const titleVal = inputTitle.value.trim() || "Your High-Converting Product Title";
    const priceVal = inputPrice.value.trim() || "9.00";
    const formattedPrice = priceVal.startsWith("$") ? priceVal : "$" + priceVal;
    const boardVal = inputBoard.value.trim() || "Digital Downloads";
    const tagsVal = inputTags.value.trim();
    const descVal = inputDesc.value.trim() || "Your product description and trending hashtags will display here in the user's Pinterest feed.";

    const hashtags = tagsVal
      ? tagsVal.split(",").map(t => "#" + t.trim().replace(/\s+/g, "")).filter(t => t.length > 1).slice(0, 5).join(" ")
      : "";

    mockPinTitle.textContent = titleVal;
    mockPinDesc.textContent = hashtags ? `${descVal}\n\n${hashtags}` : descVal;
    mockBoardTag.textContent = `Board: ${boardVal}`;

    mockGumPrice.textContent = formattedPrice;
    mockGumTitle.textContent = titleVal;
    mockGumDesc.textContent = descVal;
    mockGumCta.textContent = `I want this! (${formattedPrice})`;
  }

  [inputTitle, inputPrice, inputBoard, inputTags, inputDesc].forEach(el => {
    el.addEventListener("input", updateMockups);
  });

  // File Dropzones
  const dropProduct = document.getElementById("drop-product");
  const inputFileProduct = document.getElementById("input-file-product");
  const productFilePreview = document.getElementById("product-file-preview");

  const dropImages = document.getElementById("drop-images");
  const inputFileImages = document.getElementById("input-file-images");
  const imagesThumbPreview = document.getElementById("images-thumb-preview");

  let selectedProductFile = null;
  let selectedImages = [];
  let currentVariations = [];

  dropProduct.addEventListener("click", () => inputFileProduct.click());
  dropProduct.addEventListener("dragover", (e) => { e.preventDefault(); dropProduct.classList.add("dragover"); });
  dropProduct.addEventListener("dragleave", () => dropProduct.classList.remove("dragover"));
  dropProduct.addEventListener("drop", (e) => {
    e.preventDefault();
    dropProduct.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) handleProduct(e.dataTransfer.files[0]);
  });
  inputFileProduct.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) handleProduct(e.target.files[0]);
  });

  function handleProduct(file) {
    selectedProductFile = file;
    const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
    productFilePreview.innerHTML = `
      <div class="file-tag">
        <span>📄 ${file.name} (${sizeMb} MB)</span>
        <span class="close-btn" id="btn-remove-product">&times;</span>
      </div>
    `;
    document.getElementById("btn-remove-product").addEventListener("click", (e) => {
      e.stopPropagation();
      selectedProductFile = null;
      inputFileProduct.value = "";
      productFilePreview.innerHTML = "";
    });
  }

  dropImages.addEventListener("click", () => inputFileImages.click());
  dropImages.addEventListener("dragover", (e) => { e.preventDefault(); dropImages.classList.add("dragover"); });
  dropImages.addEventListener("dragleave", () => dropImages.classList.remove("dragover"));
  dropImages.addEventListener("drop", (e) => {
    e.preventDefault();
    dropImages.classList.remove("dragover");
    if (e.dataTransfer.files) handleImages(Array.from(e.dataTransfer.files));
  });
  inputFileImages.addEventListener("change", (e) => {
    if (e.target.files) handleImages(Array.from(e.target.files));
  });

  function handleImages(files) {
    const valid = files.filter(f => f.type.startsWith("image/"));
    if (!valid.length) return;
    selectedImages = [...selectedImages, ...valid];
    renderThumbs();
  }

  function renderThumbs() {
    imagesThumbPreview.innerHTML = "";
    if (!selectedImages.length) {
      mockPinImg.style.display = "none";
      mockPinEmpty.style.display = "block";
      return;
    }
    selectedImages.forEach((imgFile, idx) => {
      const url = URL.createObjectURL(imgFile);
      const box = document.createElement("div");
      box.className = "thumb-item";
      box.innerHTML = `<img src="${url}" alt="thumb">`;
      imagesThumbPreview.appendChild(box);

      if (idx === 0) {
        mockPinImg.src = url;
        mockPinImg.style.display = "block";
        mockPinEmpty.style.display = "none";
      }
    });
  }

  // AI Hook Generator
  const btnAiGen = document.getElementById("btn-ai-gen");
  const aiChipsList = document.getElementById("ai-chips-list");

  btnAiGen.addEventListener("click", async () => {
    const title = inputTitle.value.trim() || "Monthly Budget Tracker";
    const tags = inputTags.value.trim();
    const price = inputPrice.value.trim() || "$9.00";

    btnAiGen.disabled = true;
    btnAiGen.textContent = "Generating...";

    try {
      const res = await fetch("/api/generate-variations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, tags, price })
      });
      let variations = [];
      if (res.ok) {
        const data = await res.json();
        variations = data.variations || [];
      } else {
        variations = [
          {
            pin_title: `✨ The Ultimate ${title} (Instant Download)`,
            pin_description: `Get organized with this ${title}! Aesthetic, clean, and fully customizable. Only ${price}. Tap to download now!`
          },
          {
            pin_title: `Save Hours with ${title} | Aesthetic & Minimal`,
            pin_description: `Stop starting from scratch. Transform your routine effortlessly with instant access on Gumroad!`
          },
          {
            pin_title: `Must-Have ${title} ✨ 2026 Edition`,
            pin_description: `Everything you need in one clean package. Designed for clarity and daily simplicity.`
          }
        ];
      }
      currentVariations = variations;
      aiChipsList.innerHTML = "";
      variations.forEach(v => {
        const chip = document.createElement("div");
        chip.className = "variation-chip";
        chip.innerHTML = `
          <div class="var-title">${v.pin_title}</div>
          <div class="var-desc">${v.pin_description}</div>
        `;
        chip.addEventListener("click", () => {
          inputTitle.value = v.pin_title;
          inputDesc.value = v.pin_description;
          updateMockups();
        });
        aiChipsList.appendChild(chip);
      });
    } catch (err) {
      console.warn("AI generation error:", err);
    } finally {
      btnAiGen.disabled = false;
      btnAiGen.textContent = "Generate 3 Viral Hooks";
    }
  });

  // Check Status
  async function checkStatus() {
    try {
      const res = await fetch("/api/status");
      if (!res.ok) return;
      const data = await res.json();

      const dotPin = document.getElementById("dot-pinterest");
      const textPin = document.getElementById("text-pinterest");
      if (data.pinterest_configured) {
        dotPin.className = "status-indicator indicator-green";
        textPin.textContent = "Pinterest: Connected";
      } else {
        dotPin.className = "status-indicator indicator-amber";
        textPin.textContent = "Pinterest: Ready (Simulated)";
      }

      const dotGum = document.getElementById("dot-gumroad");
      const textGum = document.getElementById("text-gumroad");
      if (data.gumroad_configured) {
        dotGum.className = "status-indicator indicator-green";
        textGum.textContent = "Gumroad: Connected";
      } else {
        dotGum.className = "status-indicator indicator-amber";
        textGum.textContent = "Gumroad: Ready (Direct Store)";
      }
    } catch (e) {
      console.error(e);
    }
  }

  // Load Archive
  const archiveList = document.getElementById("archive-list");
  async function loadArchive() {
    try {
      const res = await fetch("/api/products");
      if (!res.ok) return;
      const data = await res.json();
      const products = data.products || [];

      if (!products.length) {
        archiveList.innerHTML = `
          <div style="text-align: center; color: var(--text-dim); padding: 3rem 1rem;">
            No published products found in tracker. Run your first pipeline to publish!
          </div>
        `;
        return;
      }

      archiveList.innerHTML = products.map(p => `
        <div class="archive-card">
          <div>
            <div class="archive-title">${escapeHtml(p.name)}</div>
            <div class="archive-meta">
              <span>Published: ${new Date(p.published_at).toLocaleDateString()}</span> &bull; 
              <span>${p.pins ? p.pins.length : 0} Pins</span>
            </div>
          </div>
          <div class="archive-links">
            ${p.gumroad_url ? `<a href="${escapeHtml(p.gumroad_url)}" target="_blank" rel="noopener" class="archive-btn">🛍️ Gumroad Listing</a>` : ""}
            ${p.pins && p.pins[0] && p.pins[0].pin_url ? `<a href="${escapeHtml(p.pins[0].pin_url)}" target="_blank" rel="noopener" class="archive-btn">📌 Live Pin</a>` : ""}
          </div>
        </div>
      `).join("");
    } catch (e) {
      console.error(e);
    }
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/[&<>'"]/g, tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag));
  }

  // Form Submit Execution
  const pipelineForm = document.getElementById("pipeline-form");
  const btnSubmitPipeline = document.getElementById("btn-submit-pipeline");
  const executionLog = document.getElementById("execution-log");
  const execStatusBadge = document.getElementById("exec-status-badge");
  const execStepsContainer = document.getElementById("exec-steps-container");

  pipelineForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    if (!selectedProductFile) {
      alert("Please provide your digital product file in Box 1.");
      return;
    }
    if (!selectedImages.length) {
      alert("Please provide at least 1 Pinterest creative image in Box 1.");
      return;
    }

    const formData = new FormData();
    formData.append("product_file", selectedProductFile);
    selectedImages.forEach(img => formData.append("pin_images", img));
    formData.append("title", inputTitle.value.trim());
    formData.append("price", inputPrice.value.trim());
    formData.append("board_name", inputBoard.value.trim());
    formData.append("tags", inputTags.value.trim());
    formData.append("description", inputDesc.value.trim());
    formData.append("pin_variations", JSON.stringify(currentVariations));

    btnSubmitPipeline.disabled = true;
    executionLog.style.display = "block";
    execStatusBadge.textContent = "Running Pipeline...";
    execStepsContainer.innerHTML = `
      <div class="exec-step"><span class="spinner-icon"></span> <span>1. Ingesting files to ready-to-publish directory...</span></div>
    `;

    try {
      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      execStepsContainer.innerHTML = "";

      if (data.steps && data.steps.length) {
        data.steps.forEach(step => {
          const isSuccess = step.status === "success";
          const icon = isSuccess ? "✅" : (step.status === "skipped" ? "⚠️" : "❌");
          const stepClass = isSuccess ? "success" : (step.status === "skipped" ? "" : "failed");
          execStepsContainer.innerHTML += `
            <div class="exec-step ${stepClass}">
              <span>${icon}</span>
              <span><strong>${escapeHtml(step.step)}</strong>: ${escapeHtml(step.url || step.pin_url || step.reason || step.file || step.status)}</span>
            </div>
          `;
        });
      }

      if (data.errors && data.errors.length) {
        data.errors.forEach(err => {
          execStepsContainer.innerHTML += `
            <div class="exec-step failed">
              <span>❌</span>
              <span>${escapeHtml(err)}</span>
            </div>
          `;
        });
      }

      if (data.gumroad_url) {
        mockPinLink.textContent = `🔗 ${data.gumroad_url.replace("https://", "")}`;
      }

      execStatusBadge.textContent = res.ok ? "Completed Successfully" : "Completed with notices";
    } catch (err) {
      execStatusBadge.textContent = "Pipeline Error";
      execStepsContainer.innerHTML += `
        <div class="exec-step failed">
          <span>❌</span>
          <span>Upload network error: ${escapeHtml(err.message)}</span>
        </div>
      `;
    } finally {
      btnSubmitPipeline.disabled = false;
    }
  });

  // Init
  updateMockups();
  checkStatus();
});
