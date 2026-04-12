import subprocess
import time

def reset_bluetooth_communication():
    print("--- [BT-SYSTEM] Starting Final Silent Reset Sequence ---")
    
    def run_cmd(args):
        try:
            subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError:
            pass

    try:
        # 1. KILL the notification applet (The ultimate fix for pop-ups)
        print("[1/6] Killing Blueman notification applet...")
        run_cmd(["sudo", "pkill", "-f", "blueman-applet"])
        
        # 2. Terminate any stuck bluetoothctl
        print("[2/6] Cleaning up background processes...")
        run_cmd(["sudo", "pkill", "bluetoothctl"])
        
        # 3. System Service Restart
        print("[3/6] Restarting Bluetooth system service...")
        run_cmd(["sudo", "systemctl", "restart", "bluetooth"])
        time.sleep(2)
        
        # 4. Agent Setup (Run commands via pipe for stability)
        print("[4/6] Setting Ghost Agent (NoInputNoOutput)...")
        bt_setup = 'echo -e "power on\nagent NoInputNoOutput\ndefault-agent\nquit" | bluetoothctl'
        subprocess.run(bt_setup, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # 5. Restore Connectivity
        print("[5/6] Restoring visibility and pairable status...")
        run_cmd(["bluetoothctl", "discoverable", "on"])
        run_cmd(["bluetoothctl", "pairable", "on"])
        
        # 6. Optional: Restart the applet if you want it back later
        # (Usually better to leave it off during auto-communication)
        
        print("[6/6] [BT-SYSTEM] Bluetooth is now SILENT and READY ---")
        return True

    except Exception as e:
        print(f"--- [BT-SYSTEM] Critical Error: {e} ---")
        return False