# Órbita HUD

**Un reloj, el sonido de tu equipo y tus indicadores en órbita.** Un tema para Conky creado por **Onocru**, con reloj digital central, espectro de audio circular y panel lateral reversible.

![Vista de ejemplo: porcentajes ilustrativos, no lecturas en vivo](assets/preview-right.png)

Primera versión **0.1.0**, probada en Linux Mint 22.3 Cinnamon, sesión X11 y Conky 1.19.6. El panel es transparente: el fondo de esta captura es ilustrativo.

## Qué incluye

- Reloj de 24 horas con fecha y año en español; tres anillos de avance: horas, minutos y segundos.
- Halo de 96 bandas que reacciona al **sonido de salida** de la computadora: música, juegos, videos o cualquier aplicación. Sigue la salida predeterminada y no escucha el micrófono. En silencio se atenúa.
- GPU arriba: temperatura, carga global y VRAM utilizada. CPU abajo: temperatura, carga global y RAM general utilizada.
- Dos arcos por suscripción: ventana corta y semana, con el porcentaje usado junto a cada etiqueta. Sin barras horizontales.
- Dos módulos independientes en Conky Manager 2: `conkyrc-clock` y `conkyrc-panel`.
- Escala proporcional al monitor principal, conservando círculos redondos. El panel se puede colocar a izquierda o derecha.

## Instalación

[Descargar código e instalador en ZIP](https://github.com/Mike7Gtz/orbita-hud/archive/refs/heads/master.zip). Extrae el ZIP y ejecuta `./install.sh` desde su carpeta, o clona el repositorio con los comandos siguientes.

Dependencias en Mint/Ubuntu (paquetes de sus repositorios oficiales):

```bash
sudo apt update
sudo apt install conky-all python3 python3-numpy pulseaudio-utils x11-xserver-utils fonts-dejavu-core git
git clone https://github.com/Mike7Gtz/orbita-hud.git
cd orbita-hud
./install.sh
python3 ~/.conky/Orbita-HUD/runner.py start
```

El instalador no necesita sudo. Copia el tema a `~/.conky/Orbita-HUD`, preserva la configuración personal y respalda una instalación anterior del tema. No detiene otros Conkys. Requiere Python 3.11 o superior y Conky con soporte Lua/Cairo.

En Conky Manager 2 pulsa **Refresh** y activa los dos archivos. También funcionan por separado. No actives simultáneamente copias del mismo módulo. Para iniciar al entrar a Cinnamon:

```bash
./install.sh --autostart
```

El arranque automático es opcional. Si Conky Manager ya inicia estos módulos, usa solamente ese mecanismo. Para detener exclusivamente esta instalación:

```bash
python3 ~/.conky/Orbita-HUD/runner.py stop
```

## Ajustes

Edita `~/.config/orbita-hud/config.toml` y reinicia los módulos. `config.example.toml` contiene las opciones y sus comentarios.

```toml
[appearance]
side = "left"       # o "right"
monitor = "HDMI-0"  # vacío selecciona el principal
clock_scale = 0.82
top_margin = 18
bottom_margin = 18
fps = 25

[audio]
enabled = true
gain = 1.0
```

El ancho y el alto escalan juntos según XRandR; reproducir un video no cambia el tamaño. Tras cambiar resolución o monitor, reinicia el tema. La geometría está pensada para pantallas de escritorio de al menos 1280×720. Las letras permanecen legibles al reflejar el panel. La posición y el tamaño se gestionan con este archivo; las dimensiones de respaldo del editor de Conky Manager no sustituyen el ajuste automático.

## Límites de las suscripciones: alcance real

**ChatGPT / Codex:** el proveedor usa la sesión de tu CLI oficial `codex` y el método de solo lectura `account/rateLimits/read` del [App Server documentado por OpenAI](https://learn.chatgpt.com/docs/app-server). No envía mensajes a modelos ni consulta consumo facturado de la API. Lee las ventanas que devuelve el servicio y selecciona la cuota `codex`. La etiqueta secundaria **Cuota Codex** identifica ese alcance: **no mide los límites de mensajes de todos los modelos de chatgpt.com**. Requiere que ya tengas el CLI instalado e iniciado con tu suscripción. Si no está disponible, muestra `--`.

**Claude:** esta versión no incluye un conector automático de la cuenta de claude.ai. Muestra `--` hasta recibir datos vigentes mediante un archivo JSON o un proveedor local configurable. Es una integración pendiente; instalar el tema no habilita lectura automática de Claude. El contrato de datos está en [docs/providers.md](docs/providers.md).

Los arcos representan **porcentaje utilizado**, de 0 a 100. Una lectura ausente, vencida o con reinicio alcanzado se oculta: nunca se inventa un 0%. Las lecturas caducan por defecto a los 15 minutos. Los valores de las capturas son ejemplos y no se incluyen en los datos del tema.

## Sensores y privacidad

- NVIDIA: primera GPU informada por `nvidia-smi`. AMD: sensores DRM/hwmon cuando los expone el controlador. Otros controladores pueden devolver `--`. No se confunde un sensor NVMe con la CPU.
- CPU global: diferencia de contadores de `/proc/stat`. RAM: memoria total menos `MemAvailable`, incluyendo la memoria recuperable como disponible.
- Arcos térmicos: escala gráfica de 0–120 °C. Es una escala de visualización, no un umbral de seguridad del hardware.
- Procesamiento de audio local por FFT/NumPy, captura del monitor de salida con `parec`. **No se guardan grabaciones.**
- No se leen cookies ni archivos de tokens. Se conservan únicamente valores saneados en `$XDG_RUNTIME_DIR/orbita-hud` (o caché local si falta ese directorio). Nada se envía a un servidor de Órbita HUD.
- Un proceso de muestreo compartido evita lectores duplicados. Se cierra después de 60 segundos sin módulos activos. El panel se dibuja a 1 Hz; el reloj y su halo a 25 FPS por defecto.

## Desarrollo

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_lua.py
python3 scripts/preview.py assets/preview-right.png
python3 scripts/preview.py assets/preview-left.png --side left
python3 runner.py doctor
python3 scripts/package.py
```

La vista previa ejecuta **el mismo renderizador Lua/Cairo** del escritorio, con datos sintéticos marcados como ejemplo. No utiliza una imagen generada para simular que el tema está funcionando.

Licencia **GPL-3.0-or-later**. Autor: **Onocru** ([Mike7Gtz](https://github.com/Mike7Gtz)). Referencias, límites de reutilización y agradecimientos: [CREDITS.md](CREDITS.md).
