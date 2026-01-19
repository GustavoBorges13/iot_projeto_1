from flask import Flask, render_template, Response, request
import cv2
import requests
import subprocess
import os
import re
from datetime import datetime
import queue
import time
import threading
import json

app = Flask(__name__)

# Lista para guardar as filas de quem está conectado
listeners = []
listeners_lock = threading.Lock()

# Variáveis de contagem
connected_users = 0
users_lock = threading.Lock()


# : : ESTADO GLOBAL DO LED : :
# Guarda a última configuração para enviar a quem conectar
led_state = {
    'state': 'on',       # on / off
    'brightness': '50',  # 0 a 100
    'color': '#ffffff'   # Hex
}


# : : Configurações : :
ESP_IP = "http://esp8266.local"
LOG_FILE = os.path.join(os.path.dirname(__file__), "app_log.txt")

# : : Fila para Logs em Tempo Real : :
log_queue = queue.Queue()

def log_message(message):
    """Função de logging que envia para TODOS os clientes conectados."""
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_entry = f"[{timestamp}] > {message}"
    
    # 1. Salva no arquivo
    try:
        with open(LOG_FILE, "a", encoding='utf-8') as f:
            f.write(log_entry + "\n")
    except Exception:
        pass
        
    print(log_entry)

    # 2. Envia para todos os navegadores conectados (Broadcast)
    with listeners_lock:
        # Percorre a lista de usuarios conectados de trás pra frente
        for i in reversed(range(len(listeners))):
            try:
                # Coloca a mensagem na fila exclusiva daquele usuario
                listeners[i].put_nowait(log_entry)
            except queue.Full:
                # Se o usuario travou ou a fila encheu, remove ele
                del listeners[i]

def get_neofetch_parts():
    """
    Executa neofetch, limpa os códigos de terminal, e separa a saída em
    logo ASCII, linha de usuário, e dados do sistema.
    """
    ascii_logo, user_host_line, info_list = "ASCII Art não disponível.", "", []

    try:
        command = ["neofetch", "--ascii_distro", "Arch_Linux", "--config", "none"]
        result = subprocess.run(
            command, capture_output=True, text=True, check=True,
            timeout=5, encoding='utf-8'
        )
        
        ansi_escape_pattern = re.compile(r'\x1b\[[?0-9;]*[a-zA-Z]')
        clean_output = ansi_escape_pattern.sub('', result.stdout)

        separator = "------------------"
        
        if separator in clean_output:
            full_logo_part, info_part = clean_output.split(separator, 1)
            logo_lines = full_logo_part.split('\n')

            while logo_lines and not logo_lines[0].strip(): logo_lines.pop(0)
            while logo_lines and not logo_lines[-1].strip(): logo_lines.pop()

            if logo_lines and '@' in logo_lines[-1]:
                user_host_line = logo_lines.pop().strip()
            
            ascii_logo = "\n".join(logo_lines)
            
            valid_lines = [line for line in info_part.splitlines() if line.strip()]
            for line in valid_lines:
                if ':' in line:
                    parts = line.split(':', 1)
                    label = parts[0].strip()
                    value = parts[1].strip()
                    
                    # forcar o nome kitty
                    if label == "Terminal":
                        value = "kitty"
                    # ---------------------------

                    info_list.append({"label": label, "value": value})
        else:
            info_list.append({"label": "Erro", "value": "Formato de saída do Neofetch inesperado."})
            ascii_logo = clean_output

    except Exception as e:
        info_list.append({"label": "Erro", "value": "Não foi possível obter os dados do sistema."})
        info_list.append({"label": "Detalhe", "value": str(e)})

    return ascii_logo, user_host_line, info_list

# Usei openCV pra facilitar as coisas no linux ..........
def initialize_camera(max_indices_to_check=5):
    """
    Tenta encontrar e inicializar uma câmera de vídeo funcional.
    
    A função itera sobre os índices de dispositivo de vídeo (0, 1, 2, ...)
    e retorna o primeiro objeto VideoCapture que está aberto e consegue
    ler um quadro com sucesso.

    Args:
        max_indices_to_check (int): O número máximo de índices a serem testados.

    Returns:
        cv2.VideoCapture or None: O objeto da câmera se uma for encontrada,
                                    caso contrário, None.
    """
    log_message("Procurando por uma câmera ativa...")
    for index in range(max_indices_to_check):
        log_message(f"Tentando inicializar câmera no índice {index}...")
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            # Tenta ler um quadro para garantir que a câmera está realmente funcionando
            success, _ = cap.read()
            if success:
                log_message(f"SUCESSO: Câmera encontrada e funcionando no índice {index}!")
                return cap
            else:
                log_message(f"AVISO: Câmera no índice {index} abriu, mas não retornou um quadro.")
                cap.release()
    
    log_message("ERRO: Nenhuma câmera funcional foi encontrada nos índices testados.")
    return None

# Inicializa a variável como None (não liga a câmera ainda)
camera = None
outputFrame = None
lock = threading.Lock()
camera_thread = None

def start_camera_thread():
    """Inicia a thread que lê a câmera em background se ainda não existir."""
    global camera_thread
    if camera_thread is None:
        camera_thread = threading.Thread(target=capture_frames)
        camera_thread.daemon = True
        camera_thread.start()

def capture_frames():
    """Função Produtora: Lê a câmera e atualiza o frame global."""
    global outputFrame, lock
    
    # Inicializa a câmera (Tenta índices 0 a 2)
    camera = None
    for i in range(3):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            camera = cap
            break
            
    if not camera:
        print("ERRO: Nenhuma câmera encontrada na thread de captura.")
        return

    while True:
        success, frame = camera.read()
        if success:
            # Pega o lock para escrever na variável global com segurança
            with lock:
                outputFrame = frame.copy()
        else:
            time.sleep(0.1) # Breve pausa se falhar leitura

def gen_frames():
    """Função Consumidora: Envia o frame global para o cliente."""
    global outputFrame, lock

    # Garante que a thread de captura esteja rodando
    start_camera_thread()

    while True:
        with lock:
            if outputFrame is None:
                continue
            
            # Codifica o frame atual (que a outra thread atualizou)
            (flag, encodedImage) = cv2.imencode(".jpg", outputFrame, [int(cv2.IMWRITE_JPEG_QUALITY), 30])
            
            if not flag:
                continue

        # O yield acontece FORA do lock para não travar os outros usuários
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + bytearray(encodedImage) + b'\r\n')
        
        # Controla o FPS de envio para não saturar o Cloudflare
        time.sleep(0.05) # ~20 FPS

def broadcast_state():
    """Envia o estado atual (JSON) para todos os clientes conectados."""
    global led_state
    # Cria uma string especial começando com "STATE|" para o JS identificar
    state_msg = "STATE|" + json.dumps(led_state)
    
    with listeners_lock:
        for i in reversed(range(len(listeners))):
            try:
                listeners[i].put_nowait(state_msg)
            except queue.Full:
                del listeners[i]

# : : ROTAS PRINCIPAIS : :
@app.route('/')
def index():
    ascii_logo, user_host, system_info = get_neofetch_parts()
    
    # avisa os OUTROS que você entrou
    log_message("Novo acesso detectado na página principal.")
    
    return render_template('index.html',
                           ascii_logo=ascii_logo,
                           user_host=user_host,
                           system_info=system_info)

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/led_command')
def led_command():
    global led_state
    args = request.args.to_dict()
    
    if not args: 
        return "Nenhum comando fornecido.", 400

    # Atualiza o dicionário global baseado no que chegou
    if 'state' in args:
        led_state['state'] = args['state']
        log_message(f"Comando: LED {'LIGADO' if args['state']=='on' else 'DESLIGADO'}.")
    
    if 'brightness' in args:
        led_state['brightness'] = args['brightness']
        # Se nao quiser logar o brilho para nao poluir o log comente a linha abaixo...
        log_message(f"Comando: Brilho {args['brightness']}%.")

    # Se vier cor RGB separada, converte para HEX para salvar no estado
    if 'r' in args and 'g' in args and 'b' in args:
        # Converte RGB pra Hex para o input color do HTML entender
        r, g, b = int(args['r']), int(args['g']), int(args['b'])
        led_state['color'] = f"#{r:02x}{g:02x}{b:02x}"
        log_message(f"Comando: Cor alterada para {led_state['color']}.")

    # 1. Envia comando para o ESP8266
    try: 
        requests.get(f"{ESP_IP}/", params=args, timeout=0.5)
    except: 
        pass 
    
    # 2. Avisa todos os navegadores para atualizarem seus botões
    broadcast_state()

    return "OK", 200

@app.route('/stream_logs')
def stream_logs():
    def event_stream():
        global connected_users
        my_queue = queue.Queue(maxsize=10)
        
        with listeners_lock:
            listeners.append(my_queue)
        with users_lock:
            connected_users += 1
            
        # : : Envia o estado atual imediatamente ao conectar : :
        try:
            # Envia mensagem de boas vindas
            timestamp = datetime.now().strftime('%H:%M:%S')
            my_queue.put_nowait(f"[{timestamp}] > Conectado. Sincronizando...")
            # Envia o estado dos botões
            my_queue.put_nowait("STATE|" + json.dumps(led_state))
        except:
            pass
        # -----------------------------------------------------------
        
        try:
            while True:
                try:
                    message = my_queue.get(timeout=20.0)
                    yield f"data: {message}\n\n"
                except queue.Empty:
                    yield ": keep-alive\n\n"
        except GeneratorExit:
            pass
        finally:
            with listeners_lock:
                if my_queue in listeners: listeners.remove(my_queue)
            with users_lock:
                connected_users -= 1

    return Response(event_stream(), mimetype="text/event-stream")

@app.route('/user_count')
def get_user_count():
    global connected_users
    return str(connected_users)

@app.route('/get_full_log')
def get_full_log():
    try:
        with open(LOG_FILE, "r", encoding='utf-8') as f: return Response(f.read(), mimetype="text/plain")
    except FileNotFoundError: return Response("Arquivo de log ainda não foi criado.", mimetype="text/plain")

@app.route('/clear_log')
def clear_log():
    with open(LOG_FILE, "w") as f: f.write("")
    log_message("Log foi limpo pelo usuário.")
    return "Log limpo!", 200

@app.route('/teste')
def rota_de_teste():
    return "<h1>Funciona!</h1>"

# : : INICIALIZAÇÃO DA APLICAÇÃO : :
if __name__ == '__main__':
    # debug=True ativa o "Hot Reload" (reinicia ao salvar arquivos)
    app.run(host='0.0.0.0', port=8080, debug=True)