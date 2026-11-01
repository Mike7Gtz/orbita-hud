# Scripts aportados desde la configuración personal de Claude

Se conserva aquí el código de los scripts que Claude preparó para Onocru, sin el archivo privado `usage.json`, identificadores de organización, historial ni configuración de cuenta. El instalador de Órbita **no instala ni sustituye** estos scripts; la copia personal existente permanece intacta.

- `desktop-usage.sh`: adaptación del lector de `~/.config/Claude/plan-usage-history.json`. Ese archivo depende de la aplicación Desktop y no es un contrato público de Anthropic. El modo `--watch 60` recalcula el tiempo restante; la consulta real sigue dependiendo de las muestras de Desktop. `sampled_at` conserva la fecha de la última muestra, aunque se reescriba `updated_at`.
- `usage-statusline.sh`: alternativa sencilla recibida para Claude Code con `jq`. La integración `runner.py connect-claude` es más estricta con entradas repetidas y es la opción recomendada para Code. No mezclar dos escritores sobre el mismo archivo.

La sesión con porcentaje confirmado `0` y sin `resets_at` significa **sin iniciar**: no tiene un reloj de cinco horas corriendo. Una lectura ausente o vieja sigue siendo desconocida.

El reset de cinco horas de Desktop se **estima** a partir de muestras, no lo devuelve el servidor. El reset semanal de esta contribución solo se calcula si se declara `CLAUDE_WEEKLY_RESET` con el horario de la cuenta (por ejemplo `wednesday 22:00`); también se marca como aproximado. Sin esa opción no se inventa un horario. Para horas exactas usa `resets_at` de Claude Code cuando esté disponible.

Estos scripts no obtienen credenciales ni hacen peticiones a modelos. Cerrar Desktop puede detener las muestras. Mantener el lector abierto no equivale a obtener límites nuevos.
