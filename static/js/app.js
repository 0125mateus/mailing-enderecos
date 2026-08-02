document.addEventListener("DOMContentLoaded", () => {
    const fileInput = document.getElementById("arquivo");
    const uploadArea = document.getElementById("upload-area");
    const fileName = document.getElementById("file-name");
    const btnProcessar = document.getElementById("btn-processar");
    const btnProcessarLabel = document.getElementById("btn-processar-label");
    const fileQueueEl = document.getElementById("file-queue");
    const btnQueueProximo = document.getElementById("btn-queue-proximo");
    const statusBox = document.getElementById("status");
    const resultado = document.getElementById("resultado");
    const listaEnderecos = document.getElementById("lista-enderecos");
    const buscaInput = document.getElementById("busca");
    const contadorLista = document.getElementById("contador-lista");
    const btnAnterior = document.getElementById("btn-anterior");
    const btnProximo = document.getElementById("btn-proximo");
    const paginaAtual = document.getElementById("pagina-atual");
    const statArquivo = document.getElementById("stat-arquivo");
    const statLinhas = document.getElementById("stat-linhas");
    const statEnderecos = document.getElementById("stat-enderecos");
    const statViacep = document.getElementById("stat-viacep");
    const btnTema = document.getElementById("btn-tema");
    const btnGuia = document.getElementById("btn-guia");
    const btnAbrirMaps = document.getElementById("btn-abrir-maps");
    const btnMapsCancelar = document.getElementById("btn-maps-cancelar");
    const btnMapsContinuar = document.getElementById("btn-maps-continuar");
    const btnMapsExportar = document.getElementById("btn-maps-exportar");
    const mapsProgress = document.getElementById("maps-progress");
    const mapsProgressLabel = document.getElementById("maps-progress-label");
    const mapsProgressCount = document.getElementById("maps-progress-count");
    const mapsProgressFill = document.getElementById("maps-progress-fill");
    const mapsProgressAddress = document.getElementById("maps-progress-address");
    const mapsProgressBar = mapsProgress?.querySelector(".maps-progress-bar");

    if (!fileInput || !btnProcessar || !statusBox || !resultado) {
        console.error("Elementos essenciais da página não foram encontrados.");
        return;
    }

    function formatFetchError(error) {
        const message = error?.message || "";
        if (error instanceof TypeError || /failed to fetch|networkerror|load failed/i.test(message)) {
            return (
                "Servidor local não está respondendo. " +
                "No terminal, execute: python manage.py runserver — depois recarregue a página."
            );
        }
        return message || "Erro de comunicação com o servidor.";
    }

    const PAGE_SIZE = 50;
    const THEME_KEY = "theme";
    const MAPS_POLL_INTERVAL_MS = 1500;
    const QUEUE_ADVANCE_DELAY_MS = 6000;
    const mapsAutomationEnabled = document.body.dataset.mapsAutomation === "true";
    const googleMapsUrl = document.body.dataset.googleMapsUrl || "";

    let enderecosFiltrados = [];
    let pagina = 1;
    let mapsJobId = null;
    let mapsPollTimer = null;

    const QUEUE_STATUS_LABELS = {
        pending: "Aguardando",
        reading: "Lendo...",
        maps: "No mapa...",
        done: "Concluído",
        error: "Erro",
        paused: "Pausado",
        skipped: "Sem endereços",
    };

    let fileQueueState = {
        active: false,
        paused: false,
        items: [],
        currentIndex: -1,
        waitingForMaps: false,
        advanceTimer: null,
    };

    function getSelectedFiles() {
        return Array.from(fileInput.files || []);
    }

    function isAllowedSpreadsheet(file) {
        const name = file.name.toLowerCase();
        return name.endsWith(".xlsx") || name.endsWith(".xls") || name.endsWith(".csv");
    }

    function canRemoveQueueItem(index) {
        const item = fileQueueState.items[index];
        if (!item || item.status !== "pending") {
            return false;
        }

        if (fileQueueState.active) {
            return index > fileQueueState.currentIndex;
        }

        return true;
    }

    function syncFileInputFromQueue() {
        if (!fileInput) {
            return;
        }

        const dataTransfer = new DataTransfer();
        fileQueueState.items.forEach((item) => dataTransfer.items.add(item.file));
        fileInput.files = dataTransfer.files;
    }

    function updateFileSelectionSummary() {
        const count = fileQueueState.items.length;
        if (!count) {
            fileName.textContent = "Nenhum arquivo selecionado";
            btnProcessar.disabled = true;
            return;
        }

        if (count === 1) {
            fileName.textContent = fileQueueState.items[0].file.name;
        } else {
            fileName.textContent = `${count} arquivos selecionados`;
        }

        if (!fileQueueState.active) {
            btnProcessar.disabled = false;
        }
    }

    function removeQueueItem(index) {
        if (!canRemoveQueueItem(index)) {
            return;
        }

        fileQueueState.items.splice(index, 1);
        syncFileInputFromQueue();
        renderFileQueue();
        updateFileSelectionSummary();
        updateProcessButtonLabel();
    }

    function renderFileQueue() {
        if (!fileQueueEl) {
            return;
        }

        const items = fileQueueState.items;
        if (!items.length) {
            hideElement(fileQueueEl);
            fileQueueEl.innerHTML = "";
            return;
        }

        showElement(fileQueueEl);
        fileQueueEl.innerHTML = items
            .map((item, index) => {
                const activeClass =
                    fileQueueState.active && index === fileQueueState.currentIndex
                        ? " is-active"
                        : "";
                const removeButton = canRemoveQueueItem(index)
                    ? `<button type="button" class="file-queue-remove" data-queue-index="${index}" aria-label="Remover ${item.file.name}" title="Remover da fila">×</button>`
                    : "";
                return `
                    <li class="file-queue-item is-${item.status}${activeClass}">
                        <span class="file-queue-name">${item.file.name}</span>
                        <div class="file-queue-actions">
                            <span class="file-queue-status">${QUEUE_STATUS_LABELS[item.status] || item.status}</span>
                            ${removeButton}
                        </div>
                    </li>
                `;
            })
            .join("");
    }

    function updateProcessButtonLabel() {
        if (!btnProcessarLabel) {
            return;
        }

        if (fileQueueState.active) {
            btnProcessarLabel.textContent = `Fila em andamento (${fileQueueState.currentIndex + 1}/${fileQueueState.items.length})`;
            return;
        }

        const files = getSelectedFiles();
        if (files.length > 1) {
            btnProcessarLabel.textContent = `Processar fila (${files.length} arquivos)`;
            return;
        }

        btnProcessarLabel.textContent = "Processar planilha";
    }

    function setQueueControlsLocked(locked) {
        btnProcessar.disabled = locked || getSelectedFiles().length === 0;
        if (fileInput) {
            fileInput.disabled = locked;
        }
    }

    function hideQueueContinueButton() {
        if (!btnQueueProximo) {
            return;
        }
        hideElement(btnQueueProximo);
        btnQueueProximo.disabled = true;
    }

    function showQueueContinueButton() {
        if (!btnQueueProximo) {
            return;
        }
        showElement(btnQueueProximo);
        btnQueueProximo.disabled = false;
    }

    function clearQueueAdvanceTimer() {
        if (fileQueueState.advanceTimer) {
            clearInterval(fileQueueState.advanceTimer);
            fileQueueState.advanceTimer = null;
        }
    }

    async function uploadSpreadsheetFile(file) {
        const formData = new FormData();
        formData.append("arquivo", file);

        const response = await fetch("/api/upload/", {
            method: "POST",
            headers: {
                "X-CSRFToken": getCsrfToken(),
            },
            credentials: "same-origin",
            body: formData,
        });

        const contentType = response.headers.get("content-type") || "";
        let data = null;

        if (contentType.includes("application/json")) {
            data = await response.json();
        } else {
            const text = await response.text();
            throw new Error(
                text.includes("CSRF")
                    ? "Erro de segurança (CSRF). Atualize a página e tente novamente."
                    : "Resposta inválida do servidor ao processar a planilha."
            );
        }

        if (!response.ok) {
            throw new Error(data.erro || "Erro ao processar a planilha.");
        }

        return data;
    }

    function applySpreadsheetResult(data) {
        window.enderecosAtuais = data.enderecos || [];
        window.ultimosResultados = null;
        enderecosFiltrados = [...window.enderecosAtuais];
        pagina = 1;

        if (statArquivo) statArquivo.textContent = data.arquivo;
        if (statLinhas) statLinhas.textContent = data.total_linhas_planilha;
        if (statEnderecos) statEnderecos.textContent = data.total_enderecos;
        if (statViacep) statViacep.textContent = data.enderecos_completados_viacep ?? 0;

        if (buscaInput) buscaInput.value = "";
        renderTabela();
        showElement(resultado);
        resetMapsAutomationUi();
        guide.notify("processed");
    }

    function scheduleQueueAdvance(prefix = "") {
        clearQueueAdvanceTimer();

        const hasNext = fileQueueState.currentIndex < fileQueueState.items.length - 1;
        if (!hasNext) {
            finishFileQueue();
            return;
        }

        let remaining = Math.ceil(QUEUE_ADVANCE_DELAY_MS / 1000);
        showStatus(`${prefix}Próximo arquivo em ${remaining}s...`, "info");

        fileQueueState.advanceTimer = setInterval(() => {
            remaining -= 1;
            if (remaining <= 0) {
                clearQueueAdvanceTimer();
                advanceFileQueue();
                return;
            }
            showStatus(`${prefix}Próximo arquivo em ${remaining}s...`, "info");
        }, 1000);
    }

    function advanceFileQueue() {
        const nextIndex = fileQueueState.currentIndex + 1;
        if (nextIndex >= fileQueueState.items.length) {
            finishFileQueue();
            return;
        }
        processQueueItem(nextIndex);
    }

    function finishFileQueue() {
        clearQueueAdvanceTimer();

        const total = fileQueueState.items.length;
        const done = fileQueueState.items.filter((item) =>
            ["done", "skipped"].includes(item.status)
        ).length;

        fileQueueState.active = false;
        fileQueueState.waitingForMaps = false;
        fileQueueState.paused = false;
        setQueueControlsLocked(false);
        hideQueueContinueButton();
        updateProcessButtonLabel();
        renderFileQueue();

        if (total > 1) {
            showStatus(`Fila concluída: ${done} de ${total} arquivo(s) processado(s).`, "success");
        }
    }

    function handleQueueMapsFinished(job) {
        if (!fileQueueState.active || !fileQueueState.waitingForMaps) {
            return;
        }

        fileQueueState.waitingForMaps = false;
        const item = fileQueueState.items[fileQueueState.currentIndex];
        if (!item) {
            return;
        }

        if (job.status === "completed") {
            item.status = "done";
            renderFileQueue();
            scheduleQueueAdvance(`${item.file.name} concluído. `);
            return;
        }

        item.status = "paused";
        fileQueueState.paused = true;
        renderFileQueue();
        setQueueControlsLocked(false);
        showQueueContinueButton();

        if (job.status === "cancelled") {
            showStatus(
                `Fila pausada: automação cancelada em ${item.file.name}. Baixe o Excel se quiser e clique em "Próximo arquivo da fila".`,
                "info"
            );
            return;
        }

        showStatus(
            `Fila pausada em ${item.file.name}. Clique em "Próximo arquivo da fila" para continuar.`,
            "info"
        );
    }

    async function processQueueItem(index) {
        const item = fileQueueState.items[index];
        if (!item) {
            finishFileQueue();
            return;
        }

        fileQueueState.currentIndex = index;
        fileQueueState.paused = false;
        hideQueueContinueButton();
        item.status = "reading";
        renderFileQueue();
        updateProcessButtonLabel();
        setQueueControlsLocked(true);

        showStatus(
            `Fila ${index + 1}/${fileQueueState.items.length}: lendo ${item.file.name}...`,
            "info"
        );

        try {
            const data = await uploadSpreadsheetFile(item.file);
            applySpreadsheetResult(data);

            const completados = data.enderecos_completados_viacep ?? 0;
            if (completados > 0) {
                showStatus(
                    `${completados} endereço(s) completado(s) via ViaCEP em ${item.file.name}.`,
                    "success"
                );
            }

            if (mapsAutomationEnabled && window.enderecosAtuais.length > 0) {
                item.status = "maps";
                renderFileQueue();
                fileQueueState.waitingForMaps = true;
                showStatus(
                    `Fila ${index + 1}/${fileQueueState.items.length}: abrindo mapa para ${item.file.name}...`,
                    "info"
                );
                const mapsStarted = await iniciarMapsAutomation();
                if (!mapsStarted) {
                    fileQueueState.waitingForMaps = false;
                    item.status = "paused";
                    fileQueueState.paused = true;
                    renderFileQueue();
                    setQueueControlsLocked(false);
                    showQueueContinueButton();
                }
                return;
            }

            item.status = window.enderecosAtuais.length > 0 ? "done" : "skipped";
            renderFileQueue();
            scheduleQueueAdvance(
                window.enderecosAtuais.length > 0 ? "Planilha processada. " : "Sem endereços neste arquivo. "
            );
        } catch (error) {
            item.status = "error";
            item.error = formatFetchError(error);
            fileQueueState.paused = true;
            renderFileQueue();
            setQueueControlsLocked(false);
            showStatus(`Erro em ${item.file.name}: ${formatFetchError(error)}`, "error");
            showQueueContinueButton();
        }
    }

    function startFileQueue() {
        const files = getSelectedFiles().filter(isAllowedSpreadsheet);
        if (!files.length) {
            showStatus("Selecione ao menos uma planilha válida.", "error");
            return;
        }

        fileQueueState = {
            active: true,
            paused: false,
            items: files.map((file) => ({ file, status: "pending" })),
            currentIndex: -1,
            waitingForMaps: false,
            advanceTimer: null,
        };

        renderFileQueue();
        updateProcessButtonLabel();
        processQueueItem(0);
    }

    async function processSingleSpreadsheet(file) {
        btnProcessar.disabled = true;
        showStatus("Lendo planilha, aguarde...");

        try {
            const data = await uploadSpreadsheetFile(file);
            applySpreadsheetResult(data);

            const completados = data.enderecos_completados_viacep ?? 0;
            if (completados > 0) {
                showStatus(
                    `${completados} endereço(s) completado(s) com cidade/UF via ViaCEP (CEP).`,
                    "success"
                );
            } else {
                hideStatus();
            }
        } catch (error) {
            showStatus(formatFetchError(error), "error");
            hideElement(resultado);
        } finally {
            btnProcessar.disabled = getSelectedFiles().length === 0;
        }
    }

    function getTheme() {
        return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
    }

    function setTheme(theme) {
        document.documentElement.setAttribute("data-theme", theme);
        localStorage.setItem(THEME_KEY, theme);
        if (btnTema) {
            btnTema.setAttribute(
                "aria-label",
                theme === "dark" ? "Ativar tema claro" : "Ativar tema escuro"
            );
        }
    }

    if (btnTema) {
        btnTema.setAttribute(
            "aria-label",
            getTheme() === "dark" ? "Ativar tema claro" : "Ativar tema escuro"
        );
        btnTema.addEventListener("click", () => {
            setTheme(getTheme() === "dark" ? "light" : "dark");
        });
    }

    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) {
            return parts.pop().split(";").shift();
        }
        return "";
    }

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content) {
            return meta.content;
        }
        return getCookie("csrftoken");
    }

    function showElement(element) {
        if (!element) {
            return;
        }
        element.classList.remove("hidden");
        element.removeAttribute("hidden");
    }

    function hideElement(element) {
        if (!element) {
            return;
        }
        element.classList.add("hidden");
        element.setAttribute("hidden", "");
    }

    function showStatus(message, type = "info") {
        statusBox.textContent = message;
        statusBox.className = `status ${type}`;
        showElement(statusBox);
    }

    function hideStatus() {
        hideElement(statusBox);
    }

    function resetMapsAutomationUi(options = {}) {
        const preserveExport = Boolean(options.preserveExport);
        if (mapsPollTimer) {
            clearInterval(mapsPollTimer);
            mapsPollTimer = null;
        }
        mapsJobId = null;
        if (btnAbrirMaps) {
            btnAbrirMaps.disabled = false;
        }
        if (btnMapsCancelar) {
            hideElement(btnMapsCancelar);
            btnMapsCancelar.disabled = true;
        }
        if (btnMapsContinuar) {
            hideElement(btnMapsContinuar);
            btnMapsContinuar.disabled = true;
        }
        if (btnMapsExportar && !preserveExport) {
            hideElement(btnMapsExportar);
            btnMapsExportar.disabled = true;
        }
        if (mapsProgress) {
            hideElement(mapsProgress);
        }
    }

    const GUIDE_STORAGE_KEY = "nio-guide-v1-done";

    const guide = {
        active: false,
        reviewMode: false,
        currentId: "upload",
        tooltip: null,
        highlighted: null,
        reviewSnapshot: null,

        getSteps() {
            const steps = [
                {
                    id: "upload",
                    getTarget: () => uploadArea,
                    title: "Selecione a planilha",
                    body: "Arraste ou clique aqui para escolher um ou vários arquivos (.xlsx, .xls, .csv). Use Ctrl+clique para selecionar vários.",
                    isAvailable: () => Boolean(uploadArea),
                },
                {
                    id: "process",
                    getTarget: () => btnProcessar,
                    title: "Processe os endereços",
                    body: "O sistema lê a planilha, monta o endereço para o Google e completa bairro/cidade/UF via CEP quando possível.",
                    isAvailable: () => Boolean(fileInput.files?.length),
                },
                {
                    id: "maps",
                    getTarget: () => btnAbrirMaps,
                    title: mapsAutomationEnabled
                        ? "Pesquise no Google My Maps"
                        : "Abra o Google My Maps",
                    body: mapsAutomationEnabled
                        ? "O Chrome abrirá o mapa NIO. Faça login no Google se pedido e aguarde o mapa carregar."
                        : "Abre o mapa em nova aba. A automação completa roda no ambiente local.",
                    isAvailable: () =>
                        window.enderecosAtuais?.length > 0 &&
                        resultado &&
                        !resultado.classList.contains("hidden"),
                },
            ];

            if (mapsAutomationEnabled) {
                steps.push({
                    id: "continuar",
                    getTarget: () => btnMapsContinuar,
                    title: "Continue a pesquisa",
                    body: "Edite camadas no mapa se precisar. Quando estiver pronto, clique aqui para o sistema buscar cada endereço da planilha.",
                    isAvailable: () =>
                        btnMapsContinuar &&
                        !btnMapsContinuar.classList.contains("hidden") &&
                        !btnMapsContinuar.disabled,
                });
                steps.push({
                    id: "export",
                    getTarget: () => btnMapsExportar,
                    title: "Baixe o Excel",
                    body: "Exporta os endereços dentro da mancha verde NIO. Também funciona com resultado parcial se você cancelar no meio.",
                    isAvailable: () =>
                        btnMapsExportar &&
                        !btnMapsExportar.classList.contains("hidden") &&
                        !btnMapsExportar.disabled,
                });
            }

            return steps;
        },

        findStep(stepId) {
            return this.getSteps().find((step) => step.id === stepId) || null;
        },

        saveReviewSnapshot() {
            this.reviewSnapshot = {
                resultadoHidden: Boolean(resultado?.classList.contains("hidden")),
                mapsProgressHidden: Boolean(mapsProgress?.classList.contains("hidden")),
                continuarHidden: Boolean(btnMapsContinuar?.classList.contains("hidden")),
                continuarDisabled: Boolean(btnMapsContinuar?.disabled),
                exportHidden: Boolean(btnMapsExportar?.classList.contains("hidden")),
                exportDisabled: Boolean(btnMapsExportar?.disabled),
            };
        },

        restoreReviewSnapshot() {
            if (!this.reviewSnapshot) {
                this.reviewMode = false;
                return;
            }

            const snapshot = this.reviewSnapshot;

            if (resultado) {
                if (snapshot.resultadoHidden) {
                    hideElement(resultado);
                } else {
                    showElement(resultado);
                }
            }

            if (mapsProgress) {
                if (snapshot.mapsProgressHidden) {
                    hideElement(mapsProgress);
                } else {
                    showElement(mapsProgress);
                }
            }

            if (btnMapsContinuar) {
                if (snapshot.continuarHidden) {
                    hideElement(btnMapsContinuar);
                } else {
                    showElement(btnMapsContinuar);
                }
                btnMapsContinuar.disabled = snapshot.continuarDisabled;
            }

            if (btnMapsExportar) {
                if (snapshot.exportHidden) {
                    hideElement(btnMapsExportar);
                } else {
                    showElement(btnMapsExportar);
                }
                btnMapsExportar.disabled = snapshot.exportDisabled;
            }

            this.reviewSnapshot = null;
            this.reviewMode = false;
        },

        prepareReviewStep(stepId) {
            if (!this.reviewMode) {
                return;
            }

            if (["maps", "continuar", "export"].includes(stepId) && resultado) {
                showElement(resultado);
            }

            if (stepId === "continuar") {
                if (mapsProgress) {
                    showElement(mapsProgress);
                }
                if (btnMapsContinuar) {
                    showElement(btnMapsContinuar);
                    btnMapsContinuar.disabled = false;
                }
            }

            if (stepId === "export" && btnMapsExportar) {
                showElement(btnMapsExportar);
                btnMapsExportar.disabled = false;
            }
        },

        ensureUi() {
            if (this.tooltip) {
                return;
            }

            this.tooltip = document.createElement("aside");
            this.tooltip.className = "guide-tooltip hidden";
            this.tooltip.setAttribute("role", "dialog");
            this.tooltip.setAttribute("aria-live", "polite");
            this.tooltip.setAttribute("hidden", "");

            document.body.appendChild(this.tooltip);
        },

        clearHighlight() {
            if (this.highlighted) {
                this.highlighted.classList.remove("guide-highlight");
                this.highlighted = null;
            }
        },

        hide() {
            this.active = false;
            this.clearHighlight();
            if (this.tooltip) {
                hideElement(this.tooltip);
            }
            this.restoreReviewSnapshot();
        },

        finish(persist = true) {
            if (persist) {
                localStorage.setItem(GUIDE_STORAGE_KEY, "1");
            }
            this.hide();
        },

        renderTooltip(step, stepIndex, totalSteps) {
            const isLast = stepIndex >= totalSteps - 1;
            this.tooltip.innerHTML = `
                <span class="guide-tooltip-step">Passo ${stepIndex + 1} de ${totalSteps}</span>
                <h3 class="guide-tooltip-title">${step.title}</h3>
                <p class="guide-tooltip-body">${step.body}</p>
                <div class="guide-tooltip-actions">
                    <div class="guide-tooltip-dots">
                        ${Array.from({ length: totalSteps }, (_, index) => {
                            let dotClass = "guide-tooltip-dot";
                            if (index === stepIndex) dotClass += " is-active";
                            else if (index < stepIndex) dotClass += " is-done";
                            return `<span class="${dotClass}"></span>`;
                        }).join("")}
                    </div>
                    <div>
                        <button type="button" class="guide-btn-skip" data-guide-action="skip">Pular tour</button>
                        <button type="button" class="guide-btn-next" data-guide-action="next">
                            ${isLast ? "Entendi" : "Próximo"}
                        </button>
                    </div>
                </div>
            `;

            this.tooltip.querySelector('[data-guide-action="skip"]')?.addEventListener("click", () => {
                this.finish(true);
            });
            this.tooltip.querySelector('[data-guide-action="next"]')?.addEventListener("click", () => {
                if (isLast) {
                    this.finish(true);
                    return;
                }
                this.next();
            });
        },

        positionTooltip(target) {
            if (!this.tooltip || !target) {
                return;
            }

            const rect = target.getBoundingClientRect();
            const margin = 14;
            this.tooltip.style.visibility = "hidden";
            showElement(this.tooltip);

            let top = rect.bottom + margin;
            let left = rect.left;

            if (top + this.tooltip.offsetHeight > window.innerHeight - 16) {
                top = Math.max(16, rect.top - this.tooltip.offsetHeight - margin);
            }

            left = Math.min(
                Math.max(16, left),
                window.innerWidth - this.tooltip.offsetWidth - 16
            );

            this.tooltip.style.top = `${top}px`;
            this.tooltip.style.left = `${left}px`;
            this.tooltip.style.visibility = "visible";
        },

        showStep(stepId) {
            const steps = this.getSteps();
            const step = this.findStep(stepId);
            if (!step || (!this.reviewMode && !step.isAvailable())) {
                return false;
            }

            const target = step.getTarget();
            if (!target) {
                return false;
            }

            this.ensureUi();
            this.active = true;
            this.currentId = stepId;
            this.clearHighlight();
            this.prepareReviewStep(stepId);

            target.scrollIntoView({ behavior: "smooth", block: "center" });
            target.classList.add("guide-highlight");
            this.highlighted = target;

            const stepIndex = steps.findIndex((item) => item.id === stepId);
            this.renderTooltip(step, stepIndex, steps.length);
            this.positionTooltip(target);
            return true;
        },

        start(stepId = "upload") {
            this.reviewMode = false;
            this.reviewSnapshot = null;

            const steps = this.getSteps();
            const preferred = this.findStep(stepId);
            const firstAvailable =
                (preferred && preferred.isAvailable() && preferred) ||
                steps.find((step) => step.isAvailable()) ||
                steps[0];

            if (!firstAvailable) {
                return;
            }

            this.showStep(firstAvailable.id);
        },

        startReview(stepId = "upload") {
            this.reviewMode = true;
            this.saveReviewSnapshot();
            this.active = true;
            this.showStep(stepId);
        },

        next() {
            const steps = this.getSteps();
            const currentIndex = steps.findIndex((step) => step.id === this.currentId);

            if (this.reviewMode) {
                const nextStep = steps[currentIndex + 1];
                if (nextStep) {
                    this.showStep(nextStep.id);
                    return;
                }
                this.finish(false);
                return;
            }

            for (let index = currentIndex + 1; index < steps.length; index += 1) {
                const candidate = steps[index];
                if (candidate.isAvailable()) {
                    this.showStep(candidate.id);
                    return;
                }
            }
            this.finish(true);
        },

        notify(event) {
            if (this.reviewMode) {
                return;
            }

            if (!this.active && event !== "export-ready") {
                return;
            }

            if (event === "file-selected" && this.currentId === "upload") {
                this.showStep("process");
                return;
            }

            if (event === "processed") {
                this.showStep("maps");
                return;
            }

            if (event === "maps-paused") {
                this.showStep("continuar");
                return;
            }

            if (event === "maps-running" && this.currentId === "continuar") {
                this.hide();
                return;
            }

            if (event === "export-ready") {
                if (!localStorage.getItem(GUIDE_STORAGE_KEY)) {
                    this.active = true;
                    this.showStep("export");
                }
            }
        },
    };

    window.addEventListener(
        "resize",
        () => {
            if (guide.active && guide.highlighted) {
                guide.positionTooltip(guide.highlighted);
            }
        },
        { passive: true }
    );

    if (btnGuia) {
        btnGuia.addEventListener("click", () => {
            guide.startReview("upload");
        });
    }

    if (!localStorage.getItem(GUIDE_STORAGE_KEY)) {
        window.setTimeout(() => guide.start("upload"), 900);
    }

    function updateMapsProgress(job) {
        if (!mapsProgress || !job) {
            return;
        }

        showElement(mapsProgress);
        const total = job.total || 0;
        const current = job.current || 0;
        const percent = total > 0 ? Math.round((current / total) * 100) : 0;

        mapsProgressCount.textContent = `${current} / ${total}`;
        mapsProgressFill.style.width = `${percent}%`;
        if (mapsProgressBar) {
            mapsProgressBar.setAttribute("aria-valuenow", String(percent));
            mapsProgressBar.setAttribute("aria-valuemax", "100");
        }

        if (job.current_address) {
            mapsProgressAddress.textContent = job.current_address;
        }

        if (job.status === "pending") {
            mapsProgressLabel.textContent = "Iniciando Playwright e abrindo o mapa...";
            if (btnMapsContinuar) {
                hideElement(btnMapsContinuar);
                btnMapsContinuar.disabled = true;
            }
        } else if (job.status === "paused") {
            mapsProgressLabel.textContent =
                job.message || "Mapa pronto. Edite o mapa e clique em Continuar pesquisa.";
            if (btnMapsContinuar) {
                showElement(btnMapsContinuar);
                btnMapsContinuar.disabled = false;
            }
            if (btnMapsCancelar) {
                showElement(btnMapsCancelar);
                btnMapsCancelar.disabled = false;
            }
            guide.notify("maps-paused");
        } else if (job.status === "running") {
            if (btnMapsContinuar) {
                hideElement(btnMapsContinuar);
                btnMapsContinuar.disabled = true;
            }
            guide.notify("maps-running");
            if (job.message) {
                mapsProgressLabel.textContent = job.message;
            } else if (job.current === 0) {
                mapsProgressLabel.textContent = "Aguardando legenda do mapa...";
            } else {
                mapsProgressLabel.textContent = "Pesquisando endereços no Google My Maps...";
            }
        } else if (job.status === "completed") {
            mapsProgressLabel.textContent = job.message || "Pesquisa concluída.";
        } else if (job.status === "cancelled") {
            mapsProgressLabel.textContent = job.message || "Automação cancelada.";
        } else if (job.status === "failed") {
            mapsProgressLabel.textContent = job.message || "Falha na automação.";
        }
    }

    async function pollMapsJobStatus() {
        if (!mapsJobId) {
            return;
        }

        try {
            const response = await fetch(`/api/maps/automation/${mapsJobId}/`, {
                credentials: "same-origin",
            });

            const contentType = response.headers.get("content-type") || "";
            if (!contentType.includes("application/json")) {
                return;
            }

            const job = await response.json();

            if (!response.ok) {
                if ([404, 500, 502, 503].includes(response.status)) {
                    return;
                }
                throw new Error(job.erro || "Não foi possível consultar o progresso.");
            }

            updateMapsProgress(job);

            if (job.status === "paused") {
                showStatus(
                    "Mapa aberto. Edite se precisar e clique em Continuar pesquisa para buscar os endereços da planilha.",
                    "info"
                );
            } else if (job.status === "running" && job.result?.resultados?.length) {
                mergeAutomationResults(job.result);
            }

            if (["completed", "failed", "cancelled"].includes(job.status)) {
                finalizeAutomationJob(job);
                resetMapsAutomationUi({ preserveExport: Boolean(job.result?.resultados?.length) });
                if (fileQueueState.active && fileQueueState.waitingForMaps) {
                    handleQueueMapsFinished(job);
                }
            }
        } catch (error) {
            console.warn("Falha temporária ao consultar progresso da automação:", error);
        }
    }

    function sleep(ms) {
        return new Promise((resolve) => {
            window.setTimeout(resolve, ms);
        });
    }

    async function settlePreviousMapsJob() {
        if (mapsPollTimer) {
            clearInterval(mapsPollTimer);
            mapsPollTimer = null;
        }

        const previousJobId = mapsJobId;
        if (!previousJobId) {
            await sleep(1500);
            return;
        }

        try {
            await fetch(`/api/maps/automation/${previousJobId}/cancelar/`, {
                method: "POST",
                headers: {
                    "X-CSRFToken": getCsrfToken(),
                },
                credentials: "same-origin",
            });
        } catch (error) {
            // Ignora falha ao cancelar job anterior; o backend tenta resolver conflito.
        }

        for (let attempt = 0; attempt < 20; attempt += 1) {
            try {
                const response = await fetch(`/api/maps/automation/${previousJobId}/`, {
                    credentials: "same-origin",
                });
                const job = await response.json();
                if (
                    response.ok &&
                    ["completed", "failed", "cancelled"].includes(job.status)
                ) {
                    break;
                }
            } catch (error) {
                break;
            }
            await sleep(1000);
        }

        mapsJobId = null;
        await sleep(1500);
    }

    async function iniciarMapsAutomationAttempt() {
        resetMapsAutomationUi();
        if (btnAbrirMaps) {
            btnAbrirMaps.disabled = true;
        }
        if (btnMapsCancelar) {
            showElement(btnMapsCancelar);
            btnMapsCancelar.disabled = false;
        }
        showElement(mapsProgress);
        updateMapsProgress({
            status: "pending",
            total: window.enderecosAtuais.length,
            current: 0,
            current_address: "",
        });
        showStatus("Abrindo Chrome para login no Google e My Maps...", "info");

        const response = await fetch("/api/maps/automation/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCsrfToken(),
            },
            credentials: "same-origin",
            body: JSON.stringify({
                enderecos: window.enderecosAtuais,
                resultados_anteriores: window.ultimosResultados?.resultados || [],
            }),
        });

        const data = await response.json();
        if (!response.ok) {
            return {
                ok: false,
                conflict: response.status === 409,
                message: data.erro || "Não foi possível iniciar a automação.",
            };
        }

        mapsJobId = data.id;
        updateMapsProgress(data);
        hideStatus();
        mapsPollTimer = setInterval(pollMapsJobStatus, MAPS_POLL_INTERVAL_MS);
        pollMapsJobStatus();
        return { ok: true };
    }

    async function iniciarMapsAutomation() {
        if (!window.enderecosAtuais || window.enderecosAtuais.length === 0) {
            showStatus("Processe uma planilha antes de pesquisar no mapa.", "error");
            return false;
        }

        if (fileQueueState.active) {
            await settlePreviousMapsJob();
        }

        const maxAttempts = fileQueueState.active ? 10 : 1;

        for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
            try {
                const result = await iniciarMapsAutomationAttempt();
                if (result.ok) {
                    return true;
                }

                if (!result.conflict || !fileQueueState.active || attempt === maxAttempts) {
                    resetMapsAutomationUi();
                    showStatus(result.message, "error");
                    return false;
                }

                showStatus(
                    `Aguardando automação anterior encerrar... (${attempt}/${maxAttempts})`,
                    "info"
                );
                await sleep(3000);
            } catch (error) {
                resetMapsAutomationUi();
                showStatus(formatFetchError(error), "error");
                return false;
            }
        }

        return false;
    }

    async function handleAbrirMaps() {
        if (mapsAutomationEnabled) {
            await iniciarMapsAutomation();
            return;
        }

        if (googleMapsUrl) {
            window.open(googleMapsUrl, "_blank", "noopener,noreferrer");
        }
        showStatus(
            "Mapa aberto em nova aba. A automação Playwright roda apenas no ambiente local.",
            "info"
        );
    }

    async function cancelarMapsAutomation() {
        if (!mapsJobId) {
            return;
        }

        btnMapsCancelar.disabled = true;

        try {
            await fetch(`/api/maps/automation/${mapsJobId}/cancelar/`, {
                method: "POST",
                headers: {
                    "X-CSRFToken": getCsrfToken(),
                },
                credentials: "same-origin",
            });
            showStatus("Cancelamento solicitado...", "info");
        } catch (error) {
            showStatus(formatFetchError(error), "error");
            btnMapsCancelar.disabled = false;
        }
    }

    async function continuarMapsAutomation() {
        if (!mapsJobId) {
            return;
        }

        if (btnMapsContinuar) {
            btnMapsContinuar.disabled = true;
        }

        try {
            const response = await fetch(`/api/maps/automation/${mapsJobId}/continuar/`, {
                method: "POST",
                headers: {
                    "X-CSRFToken": getCsrfToken(),
                },
                credentials: "same-origin",
            });
            const job = await response.json();
            if (!response.ok) {
                throw new Error(job.erro || "Não foi possível retomar a automação.");
            }
            updateMapsProgress(job);
            showStatus("Retomando pesquisa de endereços...", "info");
            hideStatus();
        } catch (error) {
            showStatus(formatFetchError(error), "error");
            if (btnMapsContinuar) {
                btnMapsContinuar.disabled = false;
            }
        }
    }

    function showExportButton(jobId, result) {
        if (!btnMapsExportar || !result?.resultados?.length) {
            return;
        }
        showElement(btnMapsExportar);
        btnMapsExportar.disabled = false;
        btnMapsExportar.dataset.jobId = jobId;
        guide.notify("export-ready");
    }

    function finalizeAutomationJob(job) {
        if (!job) {
            return;
        }

        const finishedJobId = job.id || mapsJobId;
        if (job.result?.resultados?.length) {
            window.ultimosResultados = job.result;
            mergeAutomationResults(job.result);
            renderTabela();
            showExportButton(finishedJobId, job.result);
        }

        const processados = job.result?.resultados?.length || 0;
        const naMancha = (job.result?.resultados || []).filter(
            (item) => item.viabilidade === "Dentro da mancha" && item.status === "ok"
        ).length;

        if (job.status === "completed") {
            showStatus(
                job.message ||
                    (naMancha > 0
                        ? `${naMancha} endereço(s) na mancha verde de ${processados} processado(s).`
                        : `Nenhum endereço na mancha verde. ${processados} endereço(s) exibidos na tabela.`),
                "info"
            );
            return;
        }

        if (job.status === "cancelled") {
            showStatus(
                processados > 0
                    ? `Automação cancelada. ${processados} endereço(s) preservado(s). Você pode baixar o Excel parcial ou pesquisar de novo para continuar.`
                    : job.message || "Automação cancelada.",
                processados > 0 ? "info" : "info"
            );
            return;
        }

        if (job.status === "failed") {
            showStatus(
                processados > 0
                    ? `${job.message || "Automação interrompida."} ${processados} endereço(s) preservado(s).`
                    : job.message || "Erro ao pesquisar endereços no mapa.",
                processados > 0 ? "info" : "error"
            );
        }
    }

    function mergeAutomationResults(result) {
        if (!result || !Array.isArray(result.resultados) || !window.enderecosAtuais) {
            return;
        }

        const byLinha = new Map();
        const byEndereco = new Map();
        for (const item of result.resultados) {
            if (item.linha !== undefined && item.linha !== null) {
                byLinha.set(String(item.linha), item);
            }
            if (item.endereco) {
                byEndereco.set(item.endereco, item);
            }
        }

        window.enderecosAtuais = window.enderecosAtuais.map((item) => {
            const match =
                byLinha.get(String(item.linha)) ||
                byEndereco.get(item.endereco) ||
                null;
            if (!match) {
                return {
                    ...item,
                    camada_nio: item.camada_nio || "",
                    viabilidade: item.viabilidade || "",
                    distancia_km: item.distancia_km ?? "",
                };
            }
            return {
                ...item,
                camada_nio: match.camada_nio || "",
                viabilidade: match.viabilidade || "",
                distancia_km: match.distancia_km ?? "",
                destacado: Boolean(match.destacado),
                status_maps: match.status || "",
            };
        });
        enderecosFiltrados = [...window.enderecosAtuais];
        enderecosFiltrados.sort((a, b) => {
            const priority = (item) => {
                if (item.viabilidade === "Dentro da mancha") return 0;
                if (item.viabilidade === "Próximo da mancha") return 1;
                return 2;
            };
            const byPriority = priority(a) - priority(b);
            if (byPriority !== 0) {
                return byPriority;
            }
            const distA = Number(a.distancia_km);
            const distB = Number(b.distancia_km);
            if (Number.isFinite(distA) && Number.isFinite(distB)) {
                return distA - distB;
            }
            return 0;
        });
        pagina = 1;
        renderTabela();
    }

    function renderTabela() {
        if (!listaEnderecos) {
            return;
        }

        const inicio = (pagina - 1) * PAGE_SIZE;
        const fim = inicio + PAGE_SIZE;
        const paginaItens = enderecosFiltrados.slice(inicio, fim);

        listaEnderecos.innerHTML = paginaItens
            .map((item, index) => {
                let rowClass = "";
                if (item.viabilidade === "Dentro da mancha") {
                    rowClass = "row-viavel-dentro";
                } else if (item.viabilidade === "Próximo da mancha") {
                    rowClass = "row-viavel-proximo";
                }
                const distancia =
                    item.distancia_km === 0 || item.distancia_km
                        ? item.distancia_km
                        : "—";
                return `
                    <tr class="${rowClass}">
                        <td>${inicio + index + 1}</td>
                        <td>${item.linha}</td>
                        <td>${item.endereco}</td>
                        <td>${item.viabilidade || "—"}</td>
                        <td>${item.camada_nio || "—"}</td>
                        <td>${distancia}</td>
                    </tr>
                `;
            })
            .join("");

        const totalPaginas = Math.max(1, Math.ceil(enderecosFiltrados.length / PAGE_SIZE));
        if (paginaAtual) {
            paginaAtual.textContent = `Página ${pagina} de ${totalPaginas}`;
        }
        if (contadorLista) {
            contadorLista.textContent = `${enderecosFiltrados.length} endereço(s) exibido(s)`;
        }
        if (btnAnterior) {
            btnAnterior.disabled = pagina <= 1;
        }
        if (btnProximo) {
            btnProximo.disabled = pagina >= totalPaginas;
        }
    }

    function aplicarBusca(termo) {
        const normalizado = termo.trim().toLowerCase();

        if (!normalizado) {
            enderecosFiltrados = [...window.enderecosAtuais];
        } else {
            enderecosFiltrados = window.enderecosAtuais.filter(
                (item) =>
                    item.endereco.toLowerCase().includes(normalizado) ||
                    String(item.camada_nio || "").toLowerCase().includes(normalizado) ||
                    String(item.viabilidade || "").toLowerCase().includes(normalizado)
            );
        }

        pagina = 1;
        renderTabela();
    }

    function handleFileSelected() {
        if (fileQueueState.active) {
            return;
        }

        const files = getSelectedFiles().filter(isAllowedSpreadsheet);
        if (!files.length) {
            fileQueueState.items = [];
            renderFileQueue();
            updateFileSelectionSummary();
            updateProcessButtonLabel();
            return;
        }

        fileQueueState.items = files.map((file) => ({ file, status: "pending" }));
        renderFileQueue();
        updateFileSelectionSummary();
        updateProcessButtonLabel();
        hideStatus();
        hideElement(resultado);
        resetMapsAutomationUi();
        guide.notify("file-selected");
    }

    fileInput.addEventListener("change", handleFileSelected);

    if (fileQueueEl) {
        fileQueueEl.addEventListener("click", (event) => {
            const button = event.target.closest(".file-queue-remove");
            if (!button) {
                return;
            }

            event.preventDefault();
            event.stopPropagation();

            const index = Number(button.dataset.queueIndex);
            if (Number.isNaN(index)) {
                return;
            }

            removeQueueItem(index);
        });
    }

    if (uploadArea) {
        uploadArea.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                fileInput.click();
            }
        });

        ["dragenter", "dragover"].forEach((eventName) => {
            uploadArea.addEventListener(eventName, (event) => {
                event.preventDefault();
                uploadArea.classList.add("upload-area-drag");
            });
        });

        ["dragleave", "drop"].forEach((eventName) => {
            uploadArea.addEventListener(eventName, (event) => {
                event.preventDefault();
                uploadArea.classList.remove("upload-area-drag");
            });
        });

        uploadArea.addEventListener("drop", (event) => {
            if (fileQueueState.active) {
                return;
            }

            const dropped = Array.from(event.dataTransfer?.files || []).filter(isAllowedSpreadsheet);
            if (!dropped.length) {
                return;
            }

            const dataTransfer = new DataTransfer();
            dropped.forEach((file) => dataTransfer.items.add(file));
            fileInput.files = dataTransfer.files;
            handleFileSelected();
        });
    }

    btnProcessar.addEventListener("click", async () => {
        const files = getSelectedFiles().filter(isAllowedSpreadsheet);
        if (!files.length) {
            showStatus("Selecione uma planilha antes de continuar.", "error");
            return;
        }

        if (files.length > 1) {
            startFileQueue();
            return;
        }

        await processSingleSpreadsheet(files[0]);
    });

    if (btnQueueProximo) {
        btnQueueProximo.addEventListener("click", async () => {
            const item = fileQueueState.items[fileQueueState.currentIndex];
            if (item && ["paused", "error"].includes(item.status)) {
                item.status = "done";
                renderFileQueue();
            }

            hideQueueContinueButton();
            fileQueueState.paused = false;
            fileQueueState.waitingForMaps = false;
            setQueueControlsLocked(true);
            await settlePreviousMapsJob();
            advanceFileQueue();
        });
    }

    if (buscaInput) {
        buscaInput.addEventListener("input", (event) => {
            aplicarBusca(event.target.value);
        });
    }

    if (btnAnterior) {
        btnAnterior.addEventListener("click", () => {
            if (pagina > 1) {
                pagina -= 1;
                renderTabela();
            }
        });
    }

    if (btnProximo) {
        btnProximo.addEventListener("click", () => {
            const totalPaginas = Math.ceil(enderecosFiltrados.length / PAGE_SIZE);
            if (pagina < totalPaginas) {
                pagina += 1;
                renderTabela();
            }
        });
    }

    if (btnAbrirMaps) {
        btnAbrirMaps.addEventListener("click", handleAbrirMaps);
    }

    if (btnMapsCancelar) {
        btnMapsCancelar.addEventListener("click", cancelarMapsAutomation);
    }

    if (btnMapsContinuar) {
        btnMapsContinuar.addEventListener("click", continuarMapsAutomation);
    }

    async function exportarMapsResultado() {
        const jobId = btnMapsExportar?.dataset.jobId;
        if (!jobId) {
            showStatus("Nenhum resultado disponível para exportação.", "error");
            return;
        }

        try {
            const response = await fetch(`/api/maps/automation/${jobId}/exportar/`, {
                credentials: "same-origin",
            });
            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                throw new Error(data.erro || "Não foi possível exportar a planilha.");
            }

            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = `resultado-nio-${jobId.slice(0, 8)}.xlsx`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
            showStatus("Planilha com camadas NIO baixada com sucesso.", "info");
        } catch (error) {
            showStatus(error.message, "error");
        }
    }

    if (btnMapsExportar) {
        btnMapsExportar.addEventListener("click", exportarMapsResultado);
    }
});
