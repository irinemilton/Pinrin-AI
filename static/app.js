/**
 * PinPilot Web App - Frontend Studio Engine
 */
document.addEventListener("DOMContentLoaded", () => {
  // Elements
  const inputTitle = document.getElementById("input-title");
  const inputPrice = document.getElementById("input-price");
  const inputBoard = document.getElementById("input-board");
  const inputTags = document.getElementById("input-tags");
  const inputDesc = document.getElementById("input-desc");

  const previewPinTitle = document.getElementById("preview-pin-title");
  const previewPinDesc = document.getElementById("preview-pin-desc");
  const previewBoardBadge = document.getElementById("preview-board-badge");
  const previewPinImg = document.getElementById("preview-pin-img");
  const previewPinEmpty = document.getElementById("preview-pin-empty");
  const previewPinLinkText = document.getElementById("preview-pin-link-text");

  const previewGumroadPrice = document.getElementById("preview-gumroad-price");
  const previewGumroadTitle = document.getElementById("preview-gumroad-title");
  const previewGumroadDesc = document.getElementById("preview-gumroad-desc");
  const previewGumroadCta = document.getElementById("preview-gumroad-cta");

  const tabBtnPinterest = document.getElementById("tab-btn-pinterest");
  const tabBtnGumroad = document.getElementById("tab-btn-gumroad");
  const previewPinterestCard = document.getElementById("preview-pinterest-card");
  const previewGumroadCard = document.getElementById("preview-gumroad-card");

  const productDropzone = document.getElementById("product-dropzone");
  const productFileInput = document.getElementById("product-file-input");
  const productFileDisplay = document.getElementById("product-file-display");

  const imagesDropzone = document.getElementById("images-dropzone");
  const imagesFileInput = document.getElementById("images-file-input");
  const imagesThumbDisplay = document.getElementById("images-thumb-display");

  const btnGenerateAi = document.getElementById("btn-generate-ai");
  const aiVariationsContainer = document.getElementById("ai-variations-container");

  const uploadForm = document.getElementById("upload-form");
  const btnPublish = document.getElementById("btn-publish");
  const progressContainer = document.getElementById("progress-container");
  const progressStepsList = document.getElementById("progress-steps-list");
  const pipelineOverallStatus = document.getElementById("pipeline-overall-status");
  const productsGrid = document.getElementById("products-grid");

  let selectedProductFile = null;
  let selectedPinImages = [];
  let currentVariations = [];

  // --- Live Mockup Updates ---
  function updateMockups() {
    const titleVal = inputTitle.value.trim() || "Your High-Converting Product Title";
    const priceVal = inputPrice.value.trim() || "9.00";
    const formattedPrice = priceVal.startsWith("$") ? priceVal : "$" + priceVal;
    const boardVal = inputBoard.value.trim() || "Digital Downloads";
    const tagsVal = inputTags.value.trim();
    const descVal = inputDesc.value.trim() || "Your product description and trending hashtags will display here in the user's Pinterest feed.";

    // Hashtags
    const hashtags = tagsVal
      ? tagsVal.split(",").map(t => "#" + t.trim().replace(/\s+/g, "")).filter(t => t.length > 1).slice(0, 5).join(" ")
      : "";

    // Pinterest Mockup
    previewPinTitle.textContent = titleVal;
    previewPinDesc.textContent = hashtags ? `${descVal}\n\n${hashtags}` : descVal;
    previewBoardBadge.textContent = `Board: ${boardVal}`;

    // Gumroad Mockup
    previewGumroadPrice.textContent = formattedPrice;
    previewGumroadTitle.textContent = titleVal;
    previewGumroadDesc.textContent = descVal;
    previewGumroadCta.textContent = `I want this! (${formattedPrice})`;
  }

  [inputTitle, inputPrice, inputBoard, inputTags, inputDesc].forEach(el => {
    el.addEventListener("input", updateMockups);
  });

  // --- Preview Tab Switcher ---
  tabBtnPinterest.addEventListener("click", () => {
    tabBtnPinterest.classList.add("active");
    tabBtnGumroad.classList.remove("active");
    previewPinterestCard.style.display = "block";
    previewGumroadCard.style.display = "none";
  });

  tabBtnGumroad.addEventListener("click", () => {
    tabBtnGumroad.classList.add("active");
    tabBtnPinterest.classList.remove("active");
    previewPinterestCard.style.display = "none";
    previewGumroadCard.style.display = "block";
  });

  // --- Product File Upload & Drag & Drop ---
  productDropzone.addEventListener("click", () => productFileInput.click());

  productDropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    productDropzone.classList.add("dragover");
  });

  productDropzone.addEventListener("dragleave", () => {
    productDropzone.classList.remove("dragover");
  });

  productDropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    productDropzone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleProductFile(e.dataTransfer.files[0]);
    }
  });

  productFileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      handleProductFile(e.target.files[0]);
    }
  });

  function handleProductFile(file) {
    selectedProductFile = file;
    const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
    productFileDisplay.innerHTML = `
      <div class="file-pill">
        <span>📄 ${file.name} (${sizeMb} MB)</span>
        <span class="remove-file" id="btn-remove-product-file">&times;</span>
      </div>
    `;

    document.getElementById("btn-remove-product-file").addEventListener("click", (e) => {
      e.stopPropagation();
      selectedProductFile = null;
      productFileInput.value = "";
      productFileDisplay.innerHTML = "";
    });
  }

  // --- Pin Images Drag & Drop ---
  imagesDropzone.addEventListener("click", () => imagesFileInput.click());

  imagesDropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    imagesDropzone.classList.add("dragover");
  });

  imagesDropzone.addEventListener("dragleave", () => {
    imagesDropzone.classList.remove("dragover");
  });

  imagesDropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    imagesDropzone.classList.remove("dragover");
    if (e.dataTransfer.files) {
      handleImageFiles(Array.from(e.dataTransfer.files));
    }
  });

  imagesFileInput.addEventListener("change", (e) => {
    if (e.target.files) {
      handleImageFiles(Array.from(e.target.files));
    }
  });

  function handleImageFiles(files) {
    const validImages = files.filter(f => f.type.startsWith("image/"));
    if (!validImages.length) return;

    selectedPinImages = [...selectedPinImages, ...validImages];
    renderImageThumbs();
  }

  function renderImageThumbs() {
    imagesThumbDisplay.innerHTML = "";
    if (selectedPinImages.length === 0) {
      previewPinImg.style.display = "none";
      previewPinEmpty.style.display = "block";
      return;
    }

    selectedPinImages.forEach((imgFile, idx) => {
      const url = URL.createObjectURL(imgFile);
      const thumb = document.createElement("div");
      thumb.className = "image-thumb-box";
      thumb.innerHTML = `<img src="${url}" alt="Thumbnail ${idx+1}">`;
      imagesThumbDisplay.appendChild(thumb);

      // Set the first image as the mockup image
      if (idx === 0) {
        previewPinImg.src = url;
        previewPinImg.style.display = "block";
        previewPinEmpty.style.display = "none";
      }
    });
  }

  // --- AI Variations Generator ---
  btnGenerateAi.addEventListener("click", async () => {
    const title = inputTitle.value.trim() || "Monthly Budget Tracker";
    const tags = inputTags.value.trim();
    const price = inputPrice.value.trim() || "$9.00";

    btnGenerateAi.disabled = true;
    btnGenerateAi.textContent = "Generating...";

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
        // Fallback local variations
        variations = [
          {
            pin_title: `✨ The Ultimate ${title} (Instant Download)`,
            pin_description: `Get organized with this ${title}! Intuitive, aesthetic, and fully customizable. Only ${price}. Tap to download now!`
          },
          {
            pin_title: `Stop Wasting Hours! Aesthetic ${title}`,
            pin_description: `Designed to save you time and bring total clarity. Instant access on Gumroad. Download today!`
          },
          {
            pin_title: `Must-Have ${title} ✨ 2026 Edition`,
            pin_description: `The best-selling digital tool you've been looking for. Clean, minimalist, and built to transform your daily routine.`
          }
        ];
      }

      currentVariations = variations;
      aiVariationsContainer.innerHTML = "";
      variations.forEach(v => {
        const chip = document.createElement("div");
        chip.className = "variation-chip";
        chip.innerHTML = `
          <div class="variation-title">${v.pin_title}</div>
          <div class="variation-desc">${v.pin_description}</div>
        `;
        chip.addEventListener("click", () => {
          inputTitle.value = v.pin_title;
          inputDesc.value = v.pin_description;
          updateMockups();
        });
        aiVariationsContainer.appendChild(chip);
      });
    } catch (err) {
      console.warn("Using fallback variations:", err);
    } finally {
      btnGenerateAi.disabled = false;
      btnGenerateAi.textContent = "Generate 3 Viral Hooks";
    }
  });

  // --- Fetch System Status ---
  async function checkSystemStatus() {
    try {
      const res = await fetch("/api/status");
      if (!res.ok) return;
      const data = await res.json();

      const pinDot = document.getElementById("pinterest-status-dot");
      const pinText = document.getElementById("pinterest-status-text");
      if (data.pinterest_configured) {
        pinDot.className = "status-dot dot-green";
        pinText.textContent = "Pinterest: Connected (v5 API)";
      } else {
        pinDot.className = "status-dot dot-amber";
        pinText.textContent = "Pinterest: Needs Token (.env)";
      }

      const gumDot = document.getElementById("gumroad-status-dot");
      const gumText = document.getElementById("gumroad-status-text");
      if (data.gumroad_configured) {
        gumDot.className = "status-dot dot-green";
        gumText.textContent = "Gumroad: Connected (API v2)";
      } else {
        gumDot.className = "status-dot dot-amber";
        gumText.textContent = "Gumroad: Ready (Direct Store)";
      }
    } catch (err) {
      console.error("Status check failed:", err);
    }
  }

  // --- Fetch Published Products Archive ---
  async function loadProductsArchive() {
    try {
      const res = await fetch("/api/products");
      if (!res.ok) return;
      const data = await res.json();
      const products = data.products || [];

      if (!products.length) {
        productsGrid.innerHTML = `
          <div style="grid-column: 1 / -1; text-align: center; color: var(--text-dim); padding: 3rem 1rem;">
            No products published yet. Upload your first product above to launch your automated pipeline!
          </div>
        `;
        return;
      }

      productsGrid.innerHTML = products.map(p => `
        <div class="product-card">
          <div class="product-card-title">${escapeHtml(p.name)}</div>
          <div class="product-card-meta">
            <span>📅 ${new Date(p.published_at).toLocaleDateString()}</span> &bull; 
            <span>📌 ${p.pins ? p.pins.length : 0} Pins Published</span>
          </div>
          <div class="product-card-actions">
            ${p.gumroad_url ? `<a href="${escapeHtml(p.gumroad_url)}" target="_blank" rel="noopener" class="action-link link-gumroad">🛍️ View on Gumroad</a>` : ""}
            ${p.pins && p.pins[0] && p.pins[0].pin_url ? `<a href="${escapeHtml(p.pins[0].pin_url)}" target="_blank" rel="noopener" class="action-link link-pinterest">📌 Live Pin</a>` : ""}
          </div>
        </div>
      `).join("");
    } catch (err) {
      console.error("Failed to load products archive:", err);
    }
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/[&<>'"]/g, 
      tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
  }

  // --- Upload & Publishing Pipeline Submission ---
  uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    if (!selectedProductFile) {
      alert("Please upload your digital product file (e.g. .zip, .pdf, .xlsx).");
      return;
    }
    if (!selectedPinImages.length) {
      alert("Please add at least one Pinterest creative image.");
      return;
    }

    const formData = new FormData();
    formData.append("product_file", selectedProductFile);
    selectedPinImages.forEach(img => {
      formData.append("pin_images", img);
    });
    formData.append("title", inputTitle.value.trim());
    formData.append("price", inputPrice.value.trim());
    formData.append("board_name", inputBoard.value.trim());
    formData.append("tags", inputTags.value.trim());
    formData.append("description", inputDesc.value.trim());
    formData.append("pin_variations", JSON.stringify(currentVariations));

    // Show Progress
    progressContainer.style.display = "block";
    progressStepsList.innerHTML = `
      <div class="progress-step"><span class="spinner"></span> <span>Ingesting product and creative assets...</span></div>
    `;
    pipelineOverallStatus.textContent = "Running Pipeline...";
    btnPublish.disabled = true;

    try {
      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      progressStepsList.innerHTML = "";

      if (data.steps && data.steps.length) {
        data.steps.forEach(step => {
          const isSuccess = step.status === "success";
          const icon = isSuccess ? "✅" : (step.status === "skipped" ? "⚠️" : "❌");
          const stepClass = isSuccess ? "success" : (step.status === "skipped" ? "" : "failed");
          progressStepsList.innerHTML += `
            <div class="progress-step ${stepClass}">
              <span>${icon}</span>
              <span><strong>${escapeHtml(step.step)}</strong>: ${escapeHtml(step.url || step.pin_url || step.reason || step.file || step.status)}</span>
            </div>
          `;
        });
      }

      if (data.errors && data.errors.length) {
        data.errors.forEach(err => {
          progressStepsList.innerHTML += `
            <div class="progress-step failed">
              <span>❌</span>
              <span>${escapeHtml(err)}</span>
            </div>
          `;
        });
      }

      if (data.gumroad_url) {
        previewPinLinkText.textContent = data.gumroad_url.replace("https://", "");
      }

      pipelineOverallStatus.textContent = res.ok ? "Completed Successfully!" : "Completed with notices";
      loadProductsArchive();
    } catch (err) {
      pipelineOverallStatus.textContent = "Pipeline Failed";
      progressStepsList.innerHTML += `
        <div class="progress-step failed">
          <span>❌</span>
          <span>Upload network error: ${escapeHtml(err.message)}</span>
        </div>
      `;
    } finally {
      btnPublish.disabled = false;
    }
  });

  // Initial runs
  updateMockups();
  checkSystemStatus();
  loadProductsArchive();
});
