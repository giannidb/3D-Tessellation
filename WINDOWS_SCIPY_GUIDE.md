# 🪟 Guida Installazione scipy su Windows

## Problema: Permessi Windows

Su Windows, quando Blender è installato in `C:\Program Files\`, l'installazione automatica di scipy può fallire con errore:

```
PermissionError: [WinError 5] Accesso negato
```

**Causa:** La directory `Program Files` richiede privilegi di amministratore.

---

## ✅ Soluzione: Installazione in Directory Utente

La **v2.1.1** dell'addon risolve questo problema installando scipy in una directory utente invece che in `Program Files`.

---

## 🚀 Metodo 1: Automatico (Raccomandato) ⭐

### Con v2.1.1

```
1. Installa addon v2.1.1 (o superiore)
2. Apri pannello Tessellation
3. Click "Install scipy"
4. Aspetta 2-5 minuti
5. Leggi console per conferma
6. Restart Blender
7. Done! ✓
```

L'addon ora usa `pip install scipy --user` che installa in:
```
%APPDATA%\Python\Python311\site-packages\
```

Questa directory è **sempre accessibile** senza permessi admin!

---

## 🔧 Metodo 2: Installazione Manuale (Se Automatico Fallisce)

### Opzione A: Command Prompt (Facile)

```cmd
1. Apri Command Prompt (cmd.exe)
   Non serve "Run as Administrator"!

2. Copia e incolla questo comando:

"C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m pip install scipy --user

3. Premi Enter

4. Aspetta download e installazione (2-5 minuti)

5. Dovresti vedere: "Successfully installed scipy-X.X.X"

6. Restart Blender

7. Check scipy nel pannello → dovrebbe dire "installed" ✓
```

### Opzione B: PowerShell

```powershell
# Apri PowerShell (non serve admin)
& "C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m pip install scipy --user
```

### Opzione C: Blender Python Console

```python
import subprocess
import sys

python_exe = sys.executable
subprocess.call([python_exe, "-m", "pip", "install", "scipy", "--user"])

# Restart Blender dopo questo!
```

---

## 🛠️ Metodo 3: Come Amministratore (Non Raccomandato)

⚠️ Solo se i metodi precedenti falliscono!

### Step 1: Chiudi Blender completamente

### Step 2: Apri Blender come Amministratore

```
Tasto destro su icona Blender
→ "Esegui come amministratore"
→ Click Sì quando richiesto
```

### Step 3: Installa scipy

```
Pannello Tessellation → Install scipy
Aspetta completamento
```

### Step 4: Restart Blender (Normale)

```
Chiudi Blender amministratore
Riapri normalmente
scipy sarà disponibile ✓
```

---

## 📊 Verifica Installazione

### Test 1: Check scipy Button

```
Pannello Tessellation → "Check scipy"

Se installato correttamente:
✓ scipy 1.XX.X is installed
```

### Test 2: Python Console

```python
import scipy
print(scipy.__version__)

# Dovrebbe stampare versione, es: 1.11.4
```

### Test 3: Percorso Installazione

```python
import scipy
print(scipy.__file__)

# Windows user install:
# C:\Users\[Nome]\AppData\Roaming\Python\Python311\site-packages\scipy\...

# Windows admin install:
# C:\Program Files\Blender Foundation\Blender 5.0\5.0\scripts\startup\scipy\...
```

---

## 🐛 Troubleshooting

### Errore: "No module named 'pip'"

**Soluzione:**

```cmd
"C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m ensurepip
"C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m pip install --upgrade pip
```

Poi riprova installazione scipy.

---

### Errore: "Microsoft Visual C++ required"

scipy richiede Visual C++ 14.0 o superiore.

**Soluzione:**

Scarica e installa:
```
Microsoft Visual C++ Redistributable
https://aka.ms/vs/17/release/vc_redist.x64.exe
```

Poi riprova installazione scipy.

---

### Errore: scipy installato ma non trovato

**Causa:** sys.path non include directory utente

**Soluzione:**

```python
# In Blender Python Console:
import sys
import site

user_site = site.getusersitepackages()
print(f"User site: {user_site}")

if user_site not in sys.path:
    sys.path.insert(0, user_site)
    print("Added to path")

# Ora prova:
import scipy
print("Success!")
```

---

### Installazione molto lenta

**Normale!** scipy è un package grande (~50 MB) con dependencies.

Tempi tipici:
- Download: 2-3 minuti
- Installazione: 2-3 minuti
- **Totale: 4-6 minuti**

Pazienza! 🕐

---

### Errore generico durante installazione

**Debug step-by-step:**

```cmd
REM 1. Verifica Python funziona
"C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" --version

REM 2. Verifica pip funziona
"C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m pip --version

REM 3. Aggiorna pip
"C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m pip install --upgrade pip --user

REM 4. Installa numpy prima (dependency scipy)
"C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m pip install numpy --user

REM 5. Installa scipy
"C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m pip install scipy --user
```

---

## 💡 Best Practices Windows

### 1. Non Installare Blender in Program Files

Se possibile, installa Blender in:
```
C:\Blender\
o
D:\Programs\Blender\
```

Questo evita tutti i problemi di permessi!

### 2. Usa Versione Portable

Scarica "Blender Portable":
```
- No installazione richiesta
- Nessun problema permessi
- scipy installa senza problemi
```

### 3. User Account Control (UAC)

Se hai problemi persistenti, temporaneamente disabilita UAC:
```
Control Panel → User Accounts
→ Change User Account Control settings
→ Slider in basso (Never notify)
→ Restart

(Ricorda di riattivarlo dopo!)
```

---

**File:** WINDOWS_SCIPY_GUIDE.md  
**Versione Addon:** 2.3+  
**Target:** Windows 10/11  
**Status:** ✅ Tested & Working

---

---

# 🪟 scipy Installation Guide for Windows — English Version

## Problem: Windows Permissions

On Windows, when Blender is installed in `C:\Program Files\`, the automatic scipy installation may fail with the error:

```
PermissionError: [WinError 5] Access denied
```

**Cause:** The `Program Files` directory requires administrator privileges.

---

## ✅ Solution: Install in User Directory

**v2.1.1** of the addon resolves this issue by installing scipy in a user directory instead of `Program Files`.

---

## 🚀 Method 1: Automatic (Recommended) ⭐

### With v2.1.1

```
1. Install addon v2.1.1 (or higher)
2. Open Tessellation panel
3. Click "Install scipy"
4. Wait 2–5 minutes
5. Read console for confirmation
6. Restart Blender
7. Done! ✓
```

The addon now uses `pip install scipy --user`, which installs to:
```
%APPDATA%\Python\Python311\site-packages\
```

This directory is **always accessible** without admin permissions!

---

## 🔧 Method 2: Manual Installation (If Automatic Fails)

### Option A: Command Prompt (Easy)

```cmd
1. Open Command Prompt (cmd.exe)
   No need to "Run as Administrator"!

2. Copy and paste this command:

"C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m pip install scipy --user

3. Press Enter

4. Wait for download and installation (2–5 minutes)

5. You should see: "Successfully installed scipy-X.X.X"

6. Restart Blender

7. Check scipy in the panel → should say "installed" ✓
```

### Option B: PowerShell

```powershell
# Open PowerShell (no admin needed)
& "C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m pip install scipy --user
```

### Option C: Blender Python Console

```python
import subprocess
import sys

python_exe = sys.executable
subprocess.call([python_exe, "-m", "pip", "install", "scipy", "--user"])

# Restart Blender after this!
```

---

## 🛠️ Method 3: As Administrator (Not Recommended)

⚠️ Only if the previous methods fail!

### Step 1: Close Blender completely

### Step 2: Open Blender as Administrator

```
Right-click on Blender icon
→ "Run as administrator"
→ Click Yes when prompted
```

### Step 3: Install scipy

```
Tessellation Panel → Install scipy
Wait for completion
```

### Step 4: Restart Blender (Normal)

```
Close administrator Blender
Reopen normally
scipy will be available ✓
```

---

## 📊 Verify Installation

### Test 1: Check scipy Button

```
Tessellation Panel → "Check scipy"

If installed correctly:
✓ scipy 1.XX.X is installed
```

### Test 2: Python Console

```python
import scipy
print(scipy.__version__)

# Should print version, e.g.: 1.11.4
```

### Test 3: Installation Path

```python
import scipy
print(scipy.__file__)

# Windows user install:
# C:\Users\[Name]\AppData\Roaming\Python\Python311\site-packages\scipy\...

# Windows admin install:
# C:\Program Files\Blender Foundation\Blender 5.0\5.0\scripts\startup\scipy\...
```

---

## 🐛 Troubleshooting

### Error: "No module named 'pip'"

**Solution:**

```cmd
"C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m ensurepip
"C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m pip install --upgrade pip
```

Then retry the scipy installation.

---

### Error: "Microsoft Visual C++ required"

scipy requires Visual C++ 14.0 or higher.

**Solution:**

Download and install:
```
Microsoft Visual C++ Redistributable
https://aka.ms/vs/17/release/vc_redist.x64.exe
```

Then retry the scipy installation.

---

### Error: scipy installed but not found

**Cause:** sys.path does not include the user directory

**Solution:**

```python
# In Blender Python Console:
import sys
import site

user_site = site.getusersitepackages()
print(f"User site: {user_site}")

if user_site not in sys.path:
    sys.path.insert(0, user_site)
    print("Added to path")

# Now try:
import scipy
print("Success!")
```

---

### Installation very slow

**Normal!** scipy is a large package (~50 MB) with dependencies.

Typical times:
- Download: 2–3 minutes
- Installation: 2–3 minutes
- **Total: 4–6 minutes**

Be patient! 🕐

---

### Generic error during installation

**Debug step-by-step:**

```cmd
REM 1. Verify Python works
"C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" --version

REM 2. Verify pip works
"C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m pip --version

REM 3. Update pip
"C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m pip install --upgrade pip --user

REM 4. Install numpy first (scipy dependency)
"C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m pip install numpy --user

REM 5. Install scipy
"C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m pip install scipy --user
```

---

## 💡 Windows Best Practices

### 1. Don't Install Blender in Program Files

If possible, install Blender in:
```
C:\Blender\
or
D:\Programs\Blender\
```

This avoids all permission issues!

### 2. Use the Portable Version

Download "Blender Portable":
```
- No installation required
- No permission issues
- scipy installs without problems
```

### 3. User Account Control (UAC)

If you have persistent issues, temporarily disable UAC:
```
Control Panel → User Accounts
→ Change User Account Control settings
→ Slider to bottom (Never notify)
→ Restart

(Remember to re-enable it afterwards!)
```

---

**File:** WINDOWS_SCIPY_GUIDE.md  
**Addon Version:** 2.3+  
**Target:** Windows 10/11  
**Status:** ✅ Tested & Working
