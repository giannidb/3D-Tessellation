<img width="1200" height="600" alt="Img_hero_1200x600" src="https://github.com/user-attachments/assets/b112ebbb-6c44-47a9-85b2-020beb8bdb92" />

# 3D Tessellation v2.3 🎯

## L'Addon Definitivo Unificato

💡 **Come è nata l'idea?**
Osservando la struttura interna delle ossa — un tessuto spugnoso straordinariamente leggero e resistente — ho cercato di simularne la geometria, nota in ambito medico come trabecolatura ossea.

Le trabecole sono disposte in modo da ottimizzare la resistenza occupando il minor spazio possibile, seguendo le linee di forza meccanica.

Lavorando con Blender, non ho trovato strumenti nativi in grado di riprodurre fedelmente tale struttura. I pochi progetti esistenti usano Rhino con il plugin Grasshopper, che adotta un paradigma parametrico a nodi.

Ho replicato un approccio analogo in Blender 5 sfruttando il sistema Geometry Nodes. Il principale ostacolo: suddividere un volume 3D in celle di Voronoi o tetraedri di Delaunay. Gli strumenti nativi coprono solo la tassellatura 2D; l'unico addon esistente (Cell Fracture) mantiene le celle separate, per simulare fratture — non per generare strutture continue.

Per superare questi limiti, con il supporto dell'intelligenza artificiale, ho sviluppato uno script Python che esegue la tassellatura direttamente in Blender, a partire da una mesh manifold. Al codice ho affiancato un gruppo di nodi Geometry Nodes — Smooth SFD — che trasforma il grafo in una mesh continua e raccordata, molto simile alla trabecolatura ossea.

<img width="320" height="180" alt="mqdefault_6s" src="https://github.com/user-attachments/assets/00ee10ec-32e1-47c5-bc66-8a6e6b7152f0" />

Combina il meglio di tutte le versioni precedenti in un **unico addon completo**:

✅ **Delaunay 3D** (da v1.5.0)  
✅ **Voronoi Boolean 3D** — Cell Fracture-like (da v2.3)  
✅ **Lloyd Relaxation Weight-Aware** (migliorato)  
✅ **Geometry Cleanup Completo** (merge + dissolve)  
✅ **Weight Paint Adaptive Density** (perfezionato)  
⭐ **Smooth SFD Edge Smoothing** (da v2.1)

---

## 🎨 Smooth SFD

**Smooth SFD** è integrato direttamente nell'addon!

```
Cosa fa:
✨ Smussa automaticamente edge e vertex
✨ Migliora aspetto estetico tessellazione
✨ Geometry Nodes modifier incluso
✨ Un click per applicare!

Come usare:
1. Genera tessellazione
2. Click "Apply Smooth SFD"
3. Done! ✨
```

Vedi **SMOOTH_SFD_GUIDE.md** per dettagli completi!

---

## 🎯 Caratteristiche Principali

### 1. Due Algoritmi in Uno

#### Delaunay Tessellation
```
- Tetrahedra-based
- Ideale per FEM/simulazioni
- Struttura uniforme
- Veloce e affidabile
```

#### Voronoi Boolean Tessellation
```
- Cell Fracture-like boolean intersection
- Ogni cella: INTERSECT booleano con la mesh sorgente
- Conformanza perfetta alla superficie
- Richiede mesh watertight (manifold)
- Output: unica mesh unificata
```

### 2. Densità Adattiva con Weight Paint

```python
RED (peso 1.0) → Celle PICCOLE e FITTE
  - Molti punti generati
  - Raggio locale piccolo
  - Superficie molto suddivisa

BLUE (peso 0.0) → Celle GRANDI e RADE
  - Pochi punti
  - Raggio locale grande
  - Superficie minimale
```

### 3. Lloyd Relaxation Consapevole dei Pesi

```
PRIMA (Lloyd standard):
  Tutte le celle → uniformi (annulla i pesi)

ADESSO (Lloyd weight-aware):
  Celle peso alto → movimento ridotto → restano piccole
  Celle peso basso → movimento normale → restano grandi
```

### 4. Cleanup Geometria Professionale

```
1. Remove Duplicates
   - Merge vertices entro soglia
   - Threshold adattivo in base a dimensioni mesh

2. Dissolve Planar
   - Unisce facce complanari
   - Angolo regolabile (0-30°)
   - Preserva sharp edges
```

---

## 🚀 Quick Start

### Installazione
```
1. Download: 3D-Tessellation-v2_3.zip
2. Blender → Preferences → Add-ons → Install
3. Abilita addon ✓
4. Click "Install scipy"
5. Restart Blender
6. Done!
```

<img width="320" height="180" alt="mqdefault_6s" src="https://github.com/user-attachments/assets/b599e2cc-a372-43bc-80ab-1c451cf00b75" />

#### Use Weight Paint
```
Abilita densità adattiva basata su vertex group

Come usare:
  1. Weight Paint Mode
  2. Dipingi (rosso=denso, blu=rado)
  3. Object Mode
  4. Abilita checkbox
  5. Seleziona vertex group
```

### Cleanup

#### Merge Distance
```
Range: 0.0001-1.0
Default: 0.0001

Cosa fa:
  Unisce vertici più vicini di questa distanza
  Threshold ADATTIVO in base a dimensioni mesh

Note:
  - Auto-scala per mesh grandi/piccole
  - Mesh < 10cm: threshold × 0.1
  - Mesh > 100m: threshold × 10
```

#### Dissolve Planar
```
Default: True

Cosa fa:
  Unisce facce complanari
  Riduce polygon count mantenendo forma

Angle: 0.1-30° (default 5°)
  - Più basso = solo facce perfettamente piatte
  - Più alto = più aggressive merge
```

---

## 🐛 Troubleshooting

### "scipy not installed"
```
Fix:
  1. Click "Install scipy"
  2. Aspetta 1-2 minuti
  3. Restart Blender COMPLETAMENTE
  4. Check scipy → dovrebbe dire "installed"
```

### "Troppo lento"
```
Fix immediato:
  1. Riduci Volume Samples a 200
  2. Riduci Surface Density a 0.5 (Voronoi)
  3. Disabilita Lloyd (Voronoi)
  4. Mantieni Cleanup

Fix avanzato:
  1. Semplifica mesh originale prima
  2. Riduci zone con weight alto
  3. Usa Delaunay invece di Voronoi
```

## 📄 Licenza

GPL-3.0 or later

**Versione:** 2.3.0 FINAL  
**Data:** 16 Febbraio 2026  
**Autore:** Ergo Cogito Design  
**Status:** Production Ready 🎯

---

# 3D Tessellation v2.3 🎯 — English Version

## The Ultimate Unified Addon

💡 **How did the idea come about?**
By observing the internal structure of bones — an extraordinarily light and strong spongy tissue — I sought to simulate its geometry, known in medicine as trabecular bone.

Trabeculae are arranged to optimize resistance while occupying the least possible space, following the lines of mechanical force.

Working with Blender, I found no native tools capable of faithfully reproducing such a structure. The few existing projects use Rhino with the Grasshopper plugin, which adopts a node-based parametric paradigm.

I replicated a similar approach in Blender 5 by leveraging the Geometry Nodes system. The main obstacle: subdividing a 3D volume into Voronoi cells or Delaunay tetrahedra. Native tools only cover 2D tessellation; the only existing addon (Cell Fracture) keeps cells separate to simulate fractures — not to generate continuous structures.

To overcome these limitations, with the support of artificial intelligence, I developed a Python script that performs tessellation directly in Blender, starting from a manifold mesh. Alongside the code, I built a Geometry Nodes group — Smooth SFD — that transforms the graph into a smooth, continuous mesh closely resembling trabecular bone.

<img width="320" height="180" alt="mqdefault_6s" src="https://github.com/user-attachments/assets/00ee10ec-32e1-47c5-bc66-8a6e6b7152f0" />

Combines the best of all previous versions into a **single, complete addon**:

✅ **Delaunay 3D** (since v1.5.0)  
✅ **Voronoi Boolean 3D** — Cell Fracture-like (since v2.3)  
✅ **Lloyd Relaxation Weight-Aware** (improved)  
✅ **Full Geometry Cleanup** (merge + dissolve)  
✅ **Weight Paint Adaptive Density** (refined)  
⭐ **Smooth SFD Edge Smoothing** (since v2.1)

---

## 🎨 Smooth SFD

**Smooth SFD** is integrated directly into the addon!

```
What it does:
✨ Automatically smooths edges and vertices
✨ Improves the visual appearance of the tessellation
✨ Geometry Nodes modifier included
✨ One click to apply!

How to use:
1. Generate tessellation
2. Click "Apply Smooth SFD"
3. Done! ✨
```

See **SMOOTH_SFD_GUIDE.md** for full details!

---

## 🎯 Main Features

### 1. Two Algorithms in One

#### Delaunay Tessellation
```
- Tetrahedra-based
- Ideal for FEM/simulations
- Uniform structure
- Fast and reliable
```

#### Voronoi Boolean Tessellation
```
- Cell Fracture-like boolean intersection
- Each cell: boolean INTERSECT with the source mesh
- Perfect surface conformance
- Requires watertight (manifold) mesh
- Output: single unified mesh
```

### 2. Adaptive Density with Weight Paint

```python
RED (weight 1.0) → SMALL and DENSE cells
  - Many points generated
  - Small local radius
  - Highly subdivided surface

BLUE (weight 0.0) → LARGE and SPARSE cells
  - Few points
  - Large local radius
  - Minimal surface
```

### 3. Weight-Aware Lloyd Relaxation

```
BEFORE (standard Lloyd):
  All cells → uniform (cancels out weights)

NOW (weight-aware Lloyd):
  High-weight cells → reduced movement → remain small
  Low-weight cells → normal movement → remain large
```

### 4. Professional Geometry Cleanup

```
1. Remove Duplicates
   - Merge vertices within threshold
   - Adaptive threshold based on mesh size

2. Dissolve Planar
   - Merges coplanar faces
   - Adjustable angle (0–30°)
   - Preserves sharp edges
```

---

## 🚀 Quick Start

### Installation
```
1. Download: 3D-Tessellation-v2_3.zip.zip
2. Blender → Preferences → Add-ons → Install
3. Enable addon ✓
4. Click "Install scipy"
5. Restart Blender
6. Done!
```

<img width="320" height="180" alt="mqdefault_6s" src="https://github.com/user-attachments/assets/b599e2cc-a372-43bc-80ab-1c451cf00b75" />

#### Use Weight Paint
```
Enable adaptive density based on vertex group

How to use:
  1. Weight Paint Mode
  2. Paint (red=dense, blue=sparse)
  3. Object Mode
  4. Enable checkbox
  5. Select vertex group
```

### Cleanup

#### Merge Distance
```
Range: 0.0001–1.0
Default: 0.0001

What it does:
  Merges vertices closer than this distance
  ADAPTIVE threshold based on mesh size

Notes:
  - Auto-scales for large/small meshes
  - Mesh < 10cm: threshold × 0.1
  - Mesh > 100m: threshold × 10
```

#### Dissolve Planar
```
Default: True

What it does:
  Merges coplanar faces
  Reduces polygon count while preserving shape

Angle: 0.1–30° (default 5°)
  - Lower = only perfectly flat faces
  - Higher = more aggressive merging
```

---

## 🐛 Troubleshooting

### "scipy not installed"
```
Fix:
  1. Click "Install scipy"
  2. Wait 1–2 minutes
  3. Restart Blender COMPLETELY
  4. Check scipy → should say "installed"
```

### "Too slow"
```
Immediate fix:
  1. Reduce Volume Samples to 200
  2. Reduce Surface Density to 0.5 (Voronoi)
  3. Disable Lloyd (Voronoi)
  4. Keep Cleanup

Advanced fix:
  1. Simplify the original mesh first
  2. Reduce high-weight areas
  3. Use Delaunay instead of Voronoi
```

## 📄 License

GPL-3.0 or later

**Version:** 2.3.0 FINAL  
**Date:** February 16, 2026  
**Author:** Ergo Cogito Design  
**Status:** Production Ready 🎯
