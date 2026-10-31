# Cambios

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
