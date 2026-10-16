# Photo to Part 1.0.0

Complemento para Blender 4.2 a 5.x. **De una foto a una pieza imprimible**: saca el contorno de una
pieza plana (juntas, tapas, soportes, plantillas, piezas rotas para copiar) con sus agujeros, a su
tamaño real, y la extruye al grosor que digas. Todo en modo Objeto.

## Cómo hacer la foto

- **Con hoja A4 (recomendado)**: pon la pieza encima de un folio A4 blanco y haz la foto desde arriba
  con la hoja entera a la vista. El complemento encuentra la hoja, corrige la perspectiva (aunque la
  foto esté algo torcida) y saca la escala sola: no hace falta regla.
- **Sin hoja (medida conocida)**: la pieza sobre un fondo liso que contraste, foto bien de frente, y
  escribes cuánto mide en su lado mayor.
- Mejor pieza oscura sobre fondo claro, luz pareja y sin sombras fuertes.

## Uso (Vista 3D → N → pestaña Photo to Part)

1. Elige la **Foto**, el modo (**Hoja A4 debajo** o **Medida conocida**) y el **Grosor**.
2. **Crear pieza**: sale la pieza (malla cerrada lista para imprimir) con la foto debajo para comparar.
   Los agujeros casi redondos salen como **círculos exactos** con el diámetro redondeado (5,96 → 6).
3. Si quieres retocar el contorno, el **perfil** queda oculto como curva: muévele puntos y pulsa
   **Rehacer desde el perfil** (también sirve para cambiar el grosor).

## Ajustes

Pieza (Auto / Oscura / Clara), Detalle (cuánto se simplifica el contorno), Agujeros redondos exactos
y Poner la foto debajo.

## Límites

- Piezas planas (un contorno extruido). Para relieves o piezas en 3D, el escáner.
- La precisión depende de la foto: con hoja A4 y foto de móvil, ±0,3 mm aprox. en piezas de 10 cm.
