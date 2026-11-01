# Lecturas de uso y reinicios

Se muestra porcentaje **utilizado** y tiempo restante hasta el reinicio informado por el proveedor. El tiempo usa segundos Unix. Un reinicio alcanzado oculta la lectura vencida; no se supone un 0% hasta recibirlo realmente. Una lectura vigente con **0% y sin reset activo** muestra **«Sin iniciar · 0%»**, tanto para Claude como para Codex. No se inicia una cuenta atrás de cinco horas hasta que el proveedor informe un reinicio.

## Claude Code: puente de línea de estado

La [documentación oficial](https://code.claude.com/docs/en/statusline#rate-limit-usage) describe `rate_limits.five_hour.used_percentage`, `seven_day.used_percentage` y `resets_at`. Aparecen en sesiones de suscripción compatibles después de una respuesta. Los datos llegan **por stdin**; no se busca un archivo interno de cuotas.

Después de instalar Órbita HUD:

```bash
python3 ~/.conky/Orbita-HUD/runner.py connect-claude
```

Crea `~/.claude/usage-statusline.sh` y añade `statusLine` a `~/.claude/settings.json`. Conserva las demás preferencias y guarda respaldo. Si encuentra otra línea de estado personalizada, la conserva para permitir una integración manual. No cambia permisos de herramientas ni autenticación.

El script delega a `runner.py claude-statusline`: recibe JSON, muestra un resumen en terminal y guarda únicamente porcentajes, reinicios, fecha y una huella de actualización en **`~/.claude/usage.json`**, con permisos 600. Descarta rutas de proyectos, identificadores de sesión y el resto del contexto.

No configura `refreshInterval`: repetir una entrada en memoria no equivale a consultar al servidor. Si coinciden cuotas, sesión y duración acumulada de llamadas API, conserva la fecha anterior. El visor lee el archivo cada segundo, muestra su antigüedad y marca la lectura como antigua tras `stale_seconds` (900 por defecto). La sesión vencida se oculta. El semanal se conserva como **«Última lectura»** hasta su reset conocido, manteniendo su fecha real; no se convierte en una consulta nueva.

**Requisito si no usas Claude Code:** instalar/abrir Claude Code e iniciar tu sesión de suscripción. El puente no obtiene datos de la web/app ni ejecuta peticiones a modelos por su cuenta. Hasta recibir una entrada real muestra `--`.

## Compatibilidad con el script compartido

También se acepta `~/.claude/usage.json` con este formato (números de ejemplo):

```json
{
  "five_hour": {"used_percentage": 42, "resets_at": 1793400000},
  "seven_day": {"used_percentage": 18, "resets_at": 1793800000},
  "updated_at": 1793389320
}
```

Modificar `updated_at` sin una respuesta nueva no demuestra una consulta nueva. El puente incluido evita ese refresco artificial.

Se conserva `~/.config/orbita-hud/claude-usage.json` como respaldo cuando no existe el archivo anterior. `usage.claude_file` selecciona una ruta explícita. Se aceptan `session`/`weekly`, `five_hour`/`seven_day`, `used_percent`, `utilization` y reinicios ISO 8601 con zona horaria.

## Proveedor local opcional

`usage.claude_command` es una lista de argumentos ejecutada sin shell. Debe devolver JSON con `observed_at`, `session` y `weekly` en menos de 12 segundos; se consulta con el intervalo configurado (180 s por defecto).

## Codex

Se usa el CLI oficial y `account/rateLimits/read`: inicialización, lectura y cierre del proceso auxiliar. No crea conversaciones. Solo conserva porcentajes, reinicios y fecha de lectura. La cuota mostrada es la de **Codex**, no los límites de todos los modelos de chatgpt.com. Si falla la consulta, la última lectura conserva su fecha y caduca.

## Claude Desktop y scripts personales

Se admite el archivo del lector preparado por Claude con `source: "claude-desktop"`, `five_hour` / `seven_day` y `sampled_at` (segundos Unix). Se da prioridad a **`sampled_at`** frente a `updated_at`: recalcular un temporizador cada minuto no cambia la antigüedad de la consulta. La fecha y la caducidad siguen siendo visibles. Si Desktop obtiene muestras cada 15 minutos, conviene usar `stale_seconds = 1800` para dar margen a ese intervalo; un muestreador detenido seguirá caducando.

Las versiones reutilizables de los scripts están en [contrib/claude](../contrib/claude/README.md); no se instalan sobre las personalizaciones del usuario. Los resets calculados desde el historial o un horario local son estimaciones, no datos exactos del servidor. No se incluye el JSON personal ni el identificador de organización en el repositorio.

## Consulta de Codex sin ventana visible

El muestreador consulta cada `interval_seconds`, independientemente del foco o estado de la ventana. Busca el ejecutable en PATH, `~/.local/bin/codex` y `/usr/lib/chatgpt/resources/codex` (aplicación Linux); `usage.codex_binary` permite otra ruta explícita. `runner.py doctor` muestra el ejecutable detectado. No se extraen tokens ni se abren conversaciones.

Se usa [account/rateLimits/read de la documentación oficial de OpenAI](https://learn.chatgpt.com/docs/app-server#6-rate-limits-chatgpt). No se deben confundir estos límites de Codex con todas las cuotas de modelos de la web de ChatGPT.

## Última lectura semanal

Desde 0.1.5 el límite de antigüedad distingue entre una consulta vigente y el último valor conocido. Un semanal antiguo se sigue mostrando si tiene porcentaje, fecha válida y reset futuro, y la muestra pertenece a esa misma ventana de siete días. Se muestra «Última lectura · hace …» y su cuenta regresiva original. Al reinicio se oculta hasta recibir la nueva lectura; no se traslada el porcentaje a otra semana. No se modifican los scripts del proveedor ni `usage.json`.
