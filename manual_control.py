import sys
from pynput import keyboard
from torcs_client import Client  # Assicurati che il percorso di importazione sia corretto in base alla tua struttura

# --- VARIABILI DI STATO ---
keys_pressed = {'w': False, 'a': False, 's': False, 'd': False}
state = {
    'gear': 1,
    'auto_gear': True,
    'steer': 0.0
}

def on_press(key):
    try:
        k = key.char.lower()
        if k in keys_pressed:
            keys_pressed[k] = True
        elif k == 'e':
            state['gear'] = min(6, state['gear'] + 1)
            state['auto_gear'] = False  # Disattiva l'automatico se usi il manuale
        elif k == 'q':
            state['gear'] = max(-1, state['gear'] - 1)
            state['auto_gear'] = False
        elif k == 'g':
            state['auto_gear'] = not state['auto_gear']
            print(f"Cambio automatico: {'ON' if state['auto_gear'] else 'OFF'}")
        elif k == 'r':
            state['gear'] = -1
            state['auto_gear'] = False
    except AttributeError:
        # Gestione delle frecce direzionali
        if key == keyboard.Key.up: keys_pressed['w'] = True
        elif key == keyboard.Key.down: keys_pressed['s'] = True
        elif key == keyboard.Key.left: keys_pressed['a'] = True
        elif key == keyboard.Key.right: keys_pressed['d'] = True

def on_release(key):
    try:
        k = key.char.lower()
        if k in keys_pressed:
            keys_pressed[k] = False
    except AttributeError:
        if key == keyboard.Key.up: keys_pressed['w'] = False
        elif key == keyboard.Key.down: keys_pressed['s'] = False
        elif key == keyboard.Key.left: keys_pressed['a'] = False
        elif key == keyboard.Key.right: keys_pressed['d'] = False

def auto_gearbox(S, current_gear):
    """Semplice logica per il cambio automatico basata sugli RPM"""
    rpm = S.get('rpm', 0)
    gear = current_gear
    
    if gear < 1:
        gear = 1
        
    if rpm > 7500 and gear < 6:
        gear += 1
    elif rpm < 3000 and gear > 1:
        gear -= 1
        
    return gear

def main():
    print("=== CONTROLLER MANUALE TORCS ===")
    print("Accelerare: W / Freccia Su")
    print("Frenare:    S / Freccia Giù")
    print("Sterzare:   A-D / Frecce Sinistra-Destra")
    print("Marce:      E (Aumenta) / Q (Scala) - Disattiva l'automatico")
    print("Auto-Gear:  G (Attiva/Disattiva)")
    print("Retro:      R")
    print("Premi Ctrl+C nel terminale per uscire.")

    # Avvia l'ascolto della tastiera in background
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    # Inizializza il client sulla porta specificata (default 3001)
    port = 3001
    if "--port" in sys.argv:
        port_index = sys.argv.index("--port")
        port = int(sys.argv[port_index + 1])
        
    C = Client(port=port)
    
    try:
        while True:
            if not C.get_servers_input():
                break
            
            S = C.S.d  # Stato dei sensori dell'auto
            
            # 1. ACCELERATORE E FRENO
            C.R.d['accel'] = 1.0 if keys_pressed['w'] else 0.0
            C.R.d['brake'] = 1.0 if keys_pressed['s'] else 0.0
            
            # 2. STERZO (con smorzamento/smoothing per renderlo guidabile con tastiera)
            target_steer = 0.0
            if keys_pressed['a']: target_steer += 1.0  # Sinistra
            if keys_pressed['d']: target_steer -= 1.0  # Destra
            
            # Interpola dolcemente verso il target (0.15 è il fattore di reattività)
            state['steer'] += (target_steer - state['steer']) * 0.15
            C.R.d['steer'] = state['steer']
            
            # 3. GESTIONE CAMBIO
            if state['auto_gear']:
                state['gear'] = auto_gearbox(S, state['gear'])
            C.R.d['gear'] = state['gear']
            
            # Invia l'azione al server TORCS
            C.respond_to_server()
            
    except KeyboardInterrupt:
        print("\nChiusura in corso...")
    finally:
        C.shutdown()
        listener.stop()

if __name__ == "__main__":
    main()

#python .\src\manual_control.py --port 3001   in PowerShell
#pip install pynput