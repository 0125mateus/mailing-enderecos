document.addEventListener("DOMContentLoaded", () => {
    const fileInput = document.getElementById("arquivo");
    const uploadArea = document.getElementById("upload-area");
    const fileName = document.getElementById("file-name");
    const btnProcessar = document.getElementById("btn-processar");
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
    const btnTema = document.getElementById("btn-tema");
    const btnAbrirMaps = document.getElementById("btn-abrir-maps");
    const btnMapsCancelar = document.getElementById("btn-maps-cancelar");
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

    const PAGE_SIZE = 50;
    const THEME_KEY = "theme";
    const MAPS_POLL_INTERVAL_MS = 1500;
    const mapsAutomationEnabled = document.body.dataset.mapsAutomation === "true";
    const googleMapsUrl = document.body.dataset.googleMapsUrl || "";

    let enderecosFiltrados = [];
    let pagina = 1;
    let mapsJobId = null;
    let mapsPollTimer = null;

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

    function resetMapsAutomationUi() {
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
        if (mapsProgress) {
            hideElement(mapsProgress);
        }
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
        } else if (job.status === "running") {
            mapsProgressLabel.textContent = "Pesquisando endereços no Google My Maps...";
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
            const job = await response.json();

            if (!response.ok) {
                throw new Error(job.erro || "Não foi possível consultar o progresso.");
            }

            updateMapsProgress(job);

            if (["completed", "failed", "cancelled"].includes(job.status)) {
                resetMapsAutomationUi();
                if (job.status === "completed") {
                    showStatus(job.message || "Todos os endereços foram pesquisados no mapa.", "info");
                } else if (job.status === "failed") {
                    showStatus(job.message || "Erro ao pesquisar endereços no mapa.", "error");
                } else {
                    showStatus(job.message || "Automação cancelada.", "info");
                }
            }
        } catch (error) {
            resetMapsAutomationUi();
            showStatus(error.message, "error");
        }
    }

    async function iniciarMapsAutomation() {
        if (!window.enderecosAtuais || window.enderecosAtuais.length === 0) {
            showStatus("Processe uma planilha antes de pesquisar no mapa.", "error");
            return;
        }

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
        showStatus("Abrindo Google My Maps com Playwright...", "info");

        try {
            const response = await fetch("/api/maps/automation/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCsrfToken(),
                },
                credentials: "same-origin",
                body: JSON.stringify({ enderecos: window.enderecosAtuais }),
            });

            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.erro || "Não foi possível iniciar a automação.");
            }

            mapsJobId = data.id;
            updateMapsProgress(data);
            hideStatus();
            mapsPollTimer = setInterval(pollMapsJobStatus, MAPS_POLL_INTERVAL_MS);
            pollMapsJobStatus();
        } catch (error) {
            resetMapsAutomationUi();
            showStatus(error.message, "error");
        }
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
            showStatus(error.message, "error");
            btnMapsCancelar.disabled = false;
        }
    }

    function renderTabela() {
        if (!listaEnderecos) {
            return;
        }

        const inicio = (pagina - 1) * PAGE_SIZE;
        const fim = inicio + PAGE_SIZE;
        const paginaItens = enderecosFiltrados.slice(inicio, fim);

        listaEnderecos.innerHTML = paginaItens
            .map(
                (item, index) => `
                    <tr>
                        <td>${inicio + index + 1}</td>
                        <td>${item.linha}</td>
                        <td>${item.endereco}</td>
                    </tr>
                `
            )
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
            enderecosFiltrados = window.enderecosAtuais.filter((item) =>
                item.endereco.toLowerCase().includes(normalizado)
            );
        }

        pagina = 1;
        renderTabela();
    }

    function handleFileSelected() {
        const file = fileInput.files[0];
        if (!file) {
            fileName.textContent = "Nenhum arquivo selecionado";
            btnProcessar.disabled = true;
            return;
        }

        fileName.textContent = file.name;
        btnProcessar.disabled = false;
        hideStatus();
        hideElement(resultado);
        resetMapsAutomationUi();
    }

    fileInput.addEventListener("change", handleFileSelected);

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
            const file = event.dataTransfer?.files?.[0];
            if (!file) {
                return;
            }
            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(file);
            fileInput.files = dataTransfer.files;
            handleFileSelected();
        });
    }

    btnProcessar.addEventListener("click", async () => {
        const file = fileInput.files[0];
        if (!file) {
            showStatus("Selecione uma planilha antes de continuar.", "error");
            return;
        }

        const formData = new FormData();
        formData.append("arquivo", file);

        btnProcessar.disabled = true;
        showStatus("Lendo planilha, aguarde...");

        try {
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

            window.enderecosAtuais = data.enderecos || [];
            enderecosFiltrados = [...window.enderecosAtuais];
            pagina = 1;

            if (statArquivo) statArquivo.textContent = data.arquivo;
            if (statLinhas) statLinhas.textContent = data.total_linhas_planilha;
            if (statEnderecos) statEnderecos.textContent = data.total_enderecos;

            if (buscaInput) buscaInput.value = "";
            renderTabela();
            showElement(resultado);
            resetMapsAutomationUi();
            hideStatus();
        } catch (error) {
            showStatus(error.message, "error");
            hideElement(resultado);
        } finally {
            btnProcessar.disabled = false;
        }
    });

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
});
