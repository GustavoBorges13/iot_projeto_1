function sendCommand(params) {
    const query = new URLSearchParams(params).toString();
    // Envia o comando, mas NÃO muda a tela aqui.
    // Esperamos o servidor mandar o "STATE update" para mudar a tela.
    fetch(`/led_command?${query}`);
}

function updateColor(hex) {
    // Apenas envia o comando. A UI vai atualizar quando o servidor responder.
    const rgb = hexToRgb(hex);
    // Também manda o hex junto só pro servidor saber (opcional)
    sendCommand({...rgb});
}

function hexToRgb(hex) {
    // expressao regular
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16)
    } : null;
}

// : : FUNÇÃO QUE ATUALIZA A TELA (Sincronização) : :
function updateInterface(state) {
    // 1. Atualiza Botões ON/OFF
    const btnOn = document.getElementById('btn-on');
    const btnOff = document.getElementById('btn-off');

    if (state.state === 'on') {
        btnOn.classList.add('active-btn');
        btnOff.classList.remove('active-btn');
    } else {
        btnOn.classList.remove('active-btn');
        btnOff.classList.add('active-btn');
    }

    // 2. Atualiza Slider de Brilho
    const brightnessSlider = document.getElementById('brightness');
    const brightnessValue = document.getElementById('brightness-value');
    
    // Só atualiza se o usuário NÃO estiver arrastando agora (pra não travar o dedo)
    if (document.activeElement !== brightnessSlider) {
        brightnessSlider.value = state.brightness;
        brightnessValue.textContent = state.brightness;
    }

    // 3. Atualiza Cor (Color Picker)
    const colorPicker = document.getElementById('color');
    if (document.activeElement !== colorPicker) {
        colorPicker.value = state.color;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    
    const brightnessSlider = document.getElementById('brightness');
    const brightnessValue = document.getElementById('brightness-value');
    const colorPicker = document.getElementById('color');
    const userCountVal = document.getElementById('user-count-val');

    // Polling de Usuários
    function updateUserCount() {
        fetch('/user_count')
            .then(res => res.text())
            .then(count => userCountVal.textContent = count)
            .catch(e => console.error(e));
    }

    // Event Listeners (Enviam comandos)
    brightnessSlider.addEventListener('input', () => {
        brightnessValue.textContent = brightnessSlider.value;
    });
    brightnessSlider.addEventListener('change', () => {
        sendCommand({ brightness: brightnessSlider.value });
    });

    colorPicker.addEventListener('change', () => { // Change é melhor que input para evitar flood
        const rgb = hexToRgb(colorPicker.value);
        if (rgb) sendCommand(rgb);
    });

    // : : RECEBIMENTO DE LOGS E ESTADO (SSE) : :
    const logOutput = document.getElementById('log-output');
    const clearLogBtn = document.getElementById('clear-log-btn');
    const logSource = new EventSource("/stream_logs");

    logSource.onmessage = function(event) {
        const data = event.data;

        // VERIFICA SE É UMA ATUALIZAÇÃO DE ESTADO (JSON OCULTO)
        if (data.startsWith("STATE|")) {
            try {
                const jsonStr = data.split("|")[1];
                const state = JSON.parse(jsonStr);
                updateInterface(state); // Atualiza botões e sliders
            } catch (e) {
                console.error("Erro ao processar estado:", e);
            }
        } 
        // SE NÃO FOR ESTADO, É LOG NORMAL
        else {
            logOutput.innerHTML += data + '\n';
            logOutput.scrollTop = logOutput.scrollHeight;
        }
    };
    
    clearLogBtn.addEventListener('click', () => {
        fetch('/clear_log').then(() => logOutput.innerHTML = "Log limpo.\n");
    });

    updateUserCount();
    setInterval(updateUserCount, 2000);
});