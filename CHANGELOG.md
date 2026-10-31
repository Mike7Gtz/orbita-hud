# Cambios

## 0.1.2

Corrección de [#2](https://github.com/Mike7Gtz/orbita-hud/issues/2): recuperar la composición entrelazada de la referencia, que 0.1.1 había convertido en semicírculos separados.

- Círculos grandes de VRAM y RAM que continúan detrás de los medidores de carga GPU y CPU. El aro térmico pasa por delante del conjunto central.
- Recorte por capas con fondo transparente, incluyendo las zonas donde coinciden varias máscaras. No se usan discos opacos para tapar trazos.
- Limpieza del lienzo lateral antes de cada repintado para evitar rastros de cuadros anteriores en las zonas recién transparentes.
- Silueta de los aros de cuota y etiquetas de 5 h/semanal en cian y azul con porcentajes blancos. El orden de lectura se conserva a la izquierda.
- Aro térmico con gradiente cian/azul/violeta/rojo en su parte visible. La intensidad de avance mantiene la lectura real y la escala de 0–120 °C.
- Se mantienen el reloj y el ajuste automático al área útil de 0.1.1. Vistas públicas regeneradas con el renderizador real y datos de ejemplo.
- Pruebas de superposición intencionada, zonas de texto y recorte real Cairo, además de las comprobaciones de sensores y geometría existentes.

## 0.1.1

Corrección de [#1](https://github.com/Mike7Gtz/orbita-hud/issues/1): los tacómetros se cruzaban y el panel no descontaba el menú de Cinnamon.

- Área útil por monitor consultada a Cinnamon; respaldo mediante EWMH. Se respetan los desplazamientos de monitores y las reservas del escritorio, sin usar el tamaño del escritorio virtual completo.
- Separación simétrica de los medidores VRAM/GPU y CPU/RAM. El medidor térmico permanece en el centro, con GPU arriba y CPU abajo. Los valores tienen una zona libre de marcas y ajustan el tamaño de letra si es necesario.
- Escala uniforme y compensación del borde de ventana de Conky. Se mantiene el aspecto de los círculos en ambos lados.
- Revisión del espacio disponible cada 3 segundos. Solo se reinicia el panel lateral activo cuando cambia su geometría; el reloj central conserva su configuración.
- El instalador cierra el muestreador anterior durante una actualización para cargar el nuevo código.
- Pruebas de reservas, varios monitores/resoluciones, simetría, separación entre arcos y espacio para porcentajes de tres cifras.

## 0.1.0

Primera versión: reloj y halo de audio, sensores CPU/GPU, panel reversible, lector de cuota de Codex y entrada configurable de lecturas Claude.
