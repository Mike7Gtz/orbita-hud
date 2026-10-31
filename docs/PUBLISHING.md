# Distribución

1. Ejecutar las pruebas y regenerar las vistas derecha e izquierda.
2. `python3 scripts/package.py` genera un ZIP instalable y su SHA-256. El ZIP contiene fuentes, licencia, documentación e instalador; no contiene estados de uso, registros, credenciales ni referencias descargadas para consulta.
3. Publicar una versión GitHub que coincida con `src/orbita_hud/__init__.py` (actualmente `v0.1.2`). GitHub genera automáticamente ZIP y tar.gz de las fuentes con su instalador; si se adjunta el ZIP del empaquetador, incluir también su SHA-256. Describir expresamente que Claude necesita un proveedor y que el lector ChatGPT mide la cuota de Codex.
4. En [Gnome-look, categoría Conky](https://www.gnome-look.org/browse?cat=124), crear la ficha con la captura real de `assets/preview-right.png`, autor Onocru, GPL-3.0-or-later, versión y enlace al repositorio. No usar solo el concepto generado como prueba de funcionamiento.
5. Conservar los créditos de CREDITS.md y no adjuntar los archivos de temas ajenos ni el video de referencia.

Descripción propuesta:

> Órbita HUD combina un reloj digital central, un espectro circular del audio de salida y sensores CPU/GPU en un panel reversible. Para Linux Mint Cinnamon/X11 y Conky con Lua/Cairo. Incluye lector de cuotas de suscripción de Codex y entrada configurable de lecturas Claude. Autor: Onocru. GPL-3.0-or-later.

No incluye un archivo `.cmtp.7z`: el formato publicado es ZIP con instalador por usuario. Después de instalarlo, Conky Manager 2 puede descubrir y activar los dos módulos.
