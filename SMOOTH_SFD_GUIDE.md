# Smooth SFD - Edge Smoothing Integration

## 🎨 Novità: Smooth SFD Integrato!

L'addon ora include l'asset **Smooth SFD** di Geometry Nodes per smussare automaticamente gli edge e vertex della tassellazione 3D.

---

## 🌟 Cos'è Smooth SFD?

**Smooth SFD** è un node group di Geometry Nodes progettato per:
- ✅ Smussare gli spigoli della tassellazione
- ✅ Rendere i vertici più morbidi
- ✅ Migliorare l'aspetto estetico delle celle
- ✅ Mantenere la topologia generale

---

## 🚀 Come Usarlo

### Metodo 1: Dall'Addon (Raccomandato)

```
1. Genera tessellazione (Delaunay o Voronoi)
2. Con la mesh tessellata selezionata
3. Pannello Tessellation → Edge Smoothing
4. Click "Apply Smooth SFD"
5. ✨ Fatto! Il modifier è applicato
```

### Metodo 2: Manualmente

```
1. Seleziona mesh tessellata
2. Add Modifier → Geometry Nodes
3. Seleziona node group: "Smooth SFD"
4. Regola parametri
```

---

## ⚙️ Caratteristiche Tecniche

### Installazione Automatica
```python
# Al register() dell'addon:
ensure_smooth_sfd_loaded()

Cosa fa:
1. Cerca Smooth_SFD.blend nella directory addon
2. Appende il node group "Smooth SFD"
3. Rende disponibile per l'uso
```

### Asset Bundled
```
3D-Tessellation-2.3.2/
├── __init__.py
├── Smooth_SFD.blend  ← Asset incluso!
├── blender_manifest.toml
├── README.md
├── 3D-Tessellation-Documentation.md
├── SMOOTH_SFD_GUIDE.md
└── LICENSE
3D-Tessellation-2.3.2/wheels/
	├── scipy-1.15.3-cp313-cp313-macosx_10_13_x86_64.whl
	├── scipy-1.15.3-cp313-cp313-macosx_14_0_arm64.whl
	├── scipy-1.15.3-cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
	├── scipy-1.15.3-cp313-cp313-win_amd64.whl
	├── scipy-1.15.3-cp311-cp311-macosx_10_13_x86_64.whl
	├── scipy-1.15.3-cp311-cp311-macosx_14_0_arm64.whl
	├── scipy-1.15.3-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
	├── scipy-1.15.3-cp311-cp311-win_amd64.whl

```

### Applicazione Modifier
```python
# Click "Apply Smooth SFD" esegue:
1. Verifica che Smooth SFD sia caricato
2. Controlla se già applicato (evita duplicati)
3. Aggiunge modifier Geometry Nodes
4. Assegna node group "Smooth SFD"
```

---

## 🔧 Gestione Modifier

### Verificare Applicazione
```
Properties Panel → Modifiers
Dovresti vedere: "Smooth SFD" (Geometry Nodes)
```

### Regolare Parametri
```
Se il node group ha parametri esposti:
  - Espandi il modifier
  - Regola i valori
  - Vedi preview in real-time
```

### Rimuovere Smooth SFD
```
Modifier Stack:
  - Click X su "Smooth SFD"
  oppure
  - Disable eyeball icon (mantiene ma disabilita)
```

### Applicare Permanentemente
```
Modifier Stack → Smooth SFD:
  - Click freccia giù ▼
  - Apply
  
Attenzione: Azione irreversibile!
```

---

## 🙏 Crediti

- **Asset Smooth SFD**: Design originale utente
- **Integrazione Addon**: Ergo Cogito Design
- **Versione**: 2.3
- **Data**: Febbraio 2026

---

**File:** SMOOTH_SFD_GUIDE.md  
**Versione Addon:** 2.3  
**Feature:** Smooth SFD Integration  
**Status:** ✅ Production Ready

---

---

# Smooth SFD - Edge Smoothing Integration — English Version

## 🎨 What's New: Smooth SFD Integrated!

The addon now includes the **Smooth SFD** Geometry Nodes asset to automatically smooth the edges and vertices of the 3D tessellation.

---

## 🌟 What is Smooth SFD?

**Smooth SFD** is a Geometry Nodes node group designed to:
- ✅ Smooth the edges of the tessellation
- ✅ Soften the vertices
- ✅ Improve the visual appearance of the cells
- ✅ Preserve the overall topology

---

## 🚀 How to Use It

### Method 1: From the Addon (Recommended)

```
1. Generate tessellation (Delaunay or Voronoi)
2. With the tessellated mesh selected
3. Tessellation Panel → Edge Smoothing
4. Click "Apply Smooth SFD"
5. ✨ Done! The modifier is applied
```

### Method 2: Manually

```
1. Select tessellated mesh
2. Add Modifier → Geometry Nodes
3. Select node group: "Smooth SFD"
4. Adjust parameters
```

---

## ⚙️ Technical Details

### Automatic Installation
```python
# At addon register():
ensure_smooth_sfd_loaded()

What it does:
1. Looks for Smooth_SFD.blend in the addon directory
2. Appends the "Smooth SFD" node group
3. Makes it available for use
```

### Asset Bundled
```
3D-Tessellation-2.3.2/
├── __init__.py
├── Smooth_SFD.blend  ← Asset incluso!
├── blender_manifest.toml
├── README.md
├── 3D-Tessellation-Documentation.md
├── SMOOTH_SFD_GUIDE.md
└── LICENSE
3D-Tessellation-2.3.2/wheels/
	├── scipy-1.15.3-cp313-cp313-macosx_10_13_x86_64.whl
	├── scipy-1.15.3-cp313-cp313-macosx_14_0_arm64.whl
	├── scipy-1.15.3-cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
	├── scipy-1.15.3-cp313-cp313-win_amd64.whl
	├── scipy-1.15.3-cp311-cp311-macosx_10_13_x86_64.whl
	├── scipy-1.15.3-cp311-cp311-macosx_14_0_arm64.whl
	├── scipy-1.15.3-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
	├── scipy-1.15.3-cp311-cp311-win_amd64.whl
```

### Modifier Application
```python
# Clicking "Apply Smooth SFD" runs:
1. Verifies that Smooth SFD is loaded
2. Checks if already applied (avoids duplicates)
3. Adds Geometry Nodes modifier
4. Assigns "Smooth SFD" node group
```

---

## 🔧 Modifier Management

### Verify Application
```
Properties Panel → Modifiers
You should see: "Smooth SFD" (Geometry Nodes)
```

### Adjust Parameters
```
If the node group has exposed parameters:
  - Expand the modifier
  - Adjust the values
  - See real-time preview
```

### Remove Smooth SFD
```
Modifier Stack:
  - Click X on "Smooth SFD"
  or
  - Disable eyeball icon (keeps but disables)
```

### Apply Permanently
```
Modifier Stack → Smooth SFD:
  - Click down arrow ▼
  - Apply
  
Warning: Irreversible action!
```

---

## 🙏 Credits

- **Smooth SFD Asset**: Original user design
- **Addon Integration**: Ergo Cogito Design
- **Version**: 2.3
- **Date**: February 2026

---

**File:** SMOOTH_SFD_GUIDE.md  
**Addon Version:** 2.3  
**Feature:** Smooth SFD Integration  
**Status:** ✅ Production Ready
