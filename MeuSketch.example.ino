#include <ESP8266WiFi.h>
#include <ESP8266mDNS.h>

// : : Configurações de Rede : :
const char* ssid = "SSID_NAME";
const char* password = "PASSWORD";

WiFiServer server(80);

// : : Pinos do LED RGB : :
const int redPin = D4;
const int greenPin = D3;
const int bluePin = D2;

// : : Variáveis de Estado do LED : :
int currentR = 255;
int currentG = 0;
int currentB = 0;
int brightness = 100;
bool ledState = true;

// O ESP8266 usa um PWM de 10 bits por padrão (0-1023)
const int PWM_RANGE = 1023; 

void updateLEDs() {
  Serial.println(">>> Atualizando LEDs...");
  if (!ledState) {
    analogWrite(redPin, 0);
    analogWrite(greenPin, 0);
    analogWrite(bluePin, 0);
    Serial.println("LEDs Desligados.");
    return;
  }
  
  // Calcula o valor final aplicando o brilho
  long finalR = map(currentR * brightness, 0, 255 * 100, 0, PWM_RANGE);
  long finalG = map(currentG * brightness, 0, 255 * 100, 0, PWM_RANGE);
  long finalB = map(currentB * brightness, 0, 255 * 100, 0, PWM_RANGE);

  analogWrite(redPin, finalR);
  analogWrite(greenPin, finalG);
  analogWrite(bluePin, finalB);
  
  Serial.printf("Valores Finais (com brilho): R=%ld, G=%ld, B=%ld\n", finalR, finalG, finalB);
}

void setup() {
  Serial.begin(115200); // mais precisao
  Serial.println("\n\nIniciando...");

  // Configura a faixa do PWM para 1023 para maior resolução
  analogWriteRange(PWM_RANGE);
  pinMode(redPin, OUTPUT);
  pinMode(greenPin, OUTPUT);
  pinMode(bluePin, OUTPUT);
  
  Serial.print("Conectando a "); Serial.println(ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi conectado!");
  Serial.print("Endereço IP do ESP: ");
  Serial.println(WiFi.localIP());
  Serial.print("Endereço MAC do ESP: ");
  Serial.println(WiFi.macAddress());
  
  server.begin();
  if (!MDNS.begin("esp8266")) {
    Serial.println("Erro ao iniciar o mDNS!");
    return;
  }
  Serial.println("mDNS responder iniciado. Acesse em http://esp8266.local");
  MDNS.addService("http", "tcp", 80);

  updateLEDs(); // Aplica o estado inicial do LED
}


// : : FUNÇÃO AUXILIAR PARA PARSEAMENTO : :
// Esta função procura por um parâmetro (como "r" ou "brightness") na string da requisição
// e retorna seu valor.
String getParameterValue(String req, String paramName) {
  int paramStartIndex = req.indexOf(paramName + "=");
  if (paramStartIndex < 0) {
    return ""; // Parâmetro não encontrado
  }
  paramStartIndex += paramName.length() + 1; // Pula o nome do parâmetro e o sinal "="
  
  int paramEndIndex = req.indexOf("&", paramStartIndex);
  if (paramEndIndex < 0) {
    // Se não houver "&", o parâmetro vai até o espaço antes de "HTTP/1.1"
    paramEndIndex = req.indexOf(" ", paramStartIndex);
  }
  
  if (paramEndIndex < 0) {
    return ""; // Fim da string não encontrado
  }
  
  return req.substring(paramStartIndex, paramEndIndex);
}


void loop() {
  MDNS.update();
  WiFiClient client = server.available();
  if (!client) {
    return;
  }

  Serial.println("\n--- Novo Cliente Conectado ---");

  // Espera até que o cliente envie dados
  while (!client.available()) {
    delay(1);
  }

  String requestLine = client.readStringUntil('\r');
  client.flush();

  Serial.print("Recebi a linha de requisição: ");
  Serial.println(requestLine);

  bool needsUpdate = false;

  // Extrai os parâmetros de forma robusta
  String r_val = getParameterValue(requestLine, "r");
  String g_val = getParameterValue(requestLine, "g");
  String b_val = getParameterValue(requestLine, "b");
  String brightness_val = getParameterValue(requestLine, "brightness");
  String state_val = getParameterValue(requestLine, "state");

  // Verifica se o comando de cor foi enviado
  if (r_val != "" && g_val != "" && b_val != "") {
    currentR = r_val.toInt();
    currentG = g_val.toInt();
    currentB = b_val.toInt();
    Serial.printf("Comando de Cor Recebido: R=%d, G=%d, B=%d\n", currentR, currentG, currentB);
    needsUpdate = true;
  }
  
  // Verifica se o comando de brilho foi enviado
  if (brightness_val != "") {
    brightness = brightness_val.toInt();
    Serial.printf("Comando de Brilho Recebido: %d%%\n", brightness);
    needsUpdate = true;
  }

  // Verifica se o comando de estado foi enviado
  if (state_val != "") {
    if (state_val == "on") {
      ledState = true;
      Serial.println("Comando de Estado Recebido: LIGAR");
    } else if (state_val == "off") {
      ledState = false;
      Serial.println("Comando de Estado Recebido: DESLIGAR");
    }
    needsUpdate = true;
  }
  
  if (needsUpdate) {
    updateLEDs();
  }

  // : : Resposta HTTP : :
  client.println("HTTP/1.1 200 OK");
  client.println("Access-Control-Allow-Origin: *");
  client.println("Content-Type: text/plain");
  client.println("Connection: close");
  client.println();
  client.println("Comando recebido pelo ESP8266.");
  
  delay(1);
  client.stop();
  Serial.println("--- Cliente Desconectado ---");
}