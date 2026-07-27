const fileInput = document.getElementById("arquivo");
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

const PAGE_SIZE = 50;
const THEME_KEY = "theme";

let enderecosFiltrados = [];
let pagina = 1;

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

function showStatus(message, type = "info") {
    statusBox.textContent = message;
    statusBox.className = `status ${type}`;
    statusBox.classList.remove("hidden");
}

function hideStatus() {
    statusBox.classList.add("hidden");
}

function renderTabela() {
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
    paginaAtual.textContent = `Página ${pagina} de ${totalPaginas}`;
    contadorLista.textContent = `${enderecosFiltrados.length} endereço(s) exibido(s)`;
    btnAnterior.disabled = pagina <= 1;
    btnProximo.disabled = pagina >= totalPaginas;
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

fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    if (!file) {
        fileName.textContent = "Nenhum arquivo selecionado";
        btnProcessar.disabled = true;
        return;
    }

    fileName.textContent = file.name;
    btnProcessar.disabled = false;
    hideStatus();
    resultado.classList.add("hidden");
});

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
        if (!contentType.includes("application/json")) {
            throw new Error("Erro de autenticação. Atualize a página e tente novamente.");
        }

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.erro || "Erro ao processar a planilha.");
        }

        window.enderecosAtuais = data.enderecos || [];
        enderecosFiltrados = [...window.enderecosAtuais];
        pagina = 1;

        statArquivo.textContent = data.arquivo;
        statLinhas.textContent = data.total_linhas_planilha;
        statEnderecos.textContent = data.total_enderecos;

        buscaInput.value = "";
        renderTabela();
        resultado.classList.remove("hidden");
        hideStatus();
    } catch (error) {
        showStatus(error.message, "error");
        resultado.classList.add("hidden");
    } finally {
        btnProcessar.disabled = false;
    }
});

buscaInput.addEventListener("input", (event) => {
    aplicarBusca(event.target.value);
});

btnAnterior.addEventListener("click", () => {
    if (pagina > 1) {
        pagina -= 1;
        renderTabela();
    }
});

btnProximo.addEventListener("click", () => {
    const totalPaginas = Math.ceil(enderecosFiltrados.length / PAGE_SIZE);
    if (pagina < totalPaginas) {
        pagina += 1;
        renderTabela();
    }
});
